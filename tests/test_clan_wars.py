"""Timed territory auctions, roster authority, real fights and periodic cap tax."""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select
from tests.test_game import app, H
from fastapi.testclient import TestClient
from models import SessionLocal, Player, Clan, Territory, TerritoryTax, TerritoryWar, WarFighter
from clan_wars import (phase, bid, roster, war_action, refresh_world, zombie_tax,
                       collect_tax, appoint, war_date_for_bid, WAR_TIMEZONE, ZONE)


def at(year,month,day,hour,minute=0):
    return datetime(year,month,day,hour,minute,tzinfo=ZONE).astimezone(timezone.utc)


def setup(db, offset=0):
    clans = []
    for index,name in [(96001+offset,'Соколы'+str(offset)),(96002+offset,'Вороны'+str(offset))]:
        p=Player(id=index,name=name,hero_class='soldier',level=12,stamina=500,caps=500,
                 stats={'strength':5,'agility':2,'endurance':2,'accuracy':2,'regen':0,'luck':0},skills=[])
        db.add(p)
        db.flush()
        c=Clan(name=name,leader_id=p.id,treasury=5000)
        db.add(c);db.flush();p.clan_id=c.id;clans.append((p,c))
    for index,c in [(96003+offset,clans[0][1]),(96004+offset,clans[1][1])]:
        p=Player(id=index,name='Боец '+str(index),hero_class='medic',level=10,caps=350,
                 stats={'strength':0,'agility':0,'endurance':2,'accuracy':2,'regen':0,'luck':0},skills=[],clan_id=c.id)
        db.add(p)
    return clans


def test_schedule_and_bidding_refunds_and_empty_land():
    assert phase(at(2026,10,12,12))=='bidding'
    assert phase(at(2026,10,13,11))=='formation'
    assert phase(at(2026,10,13,15,30))=='waiting'
    assert phase(at(2026,10,13,16,4))=='battle'
    assert phase(at(2026,10,13,16,31))=='finished'
    assert war_date_for_bid(at(2026,10,12,12))=='2026-10-13'
    with TestClient(app):
        with SessionLocal.begin() as db:
            (pa,ca),(pb,cb)=setup(db)
            wa=bid(db,pa,'bridge',400,at(2026,10,12,12))
            assert ca.treasury==4600
            assert wa.bid==400
            wb=bid(db,pb,'bridge',600,at(2026,10,12,13))
            assert wb.id==wa.id
            assert ca.treasury==5000 and cb.treasury==4400
            bid(db,pb,'bridge',800,at(2026,10,12,14))
            assert cb.treasury==4200
            try:bid(db,pa,'bridge',800,at(2026,10,12,15));assert False
            except ValueError: pass
        with SessionLocal.begin() as db:
            refresh_world(db,at(2026,10,13,0,1))
            t=db.get(Territory,'bridge'); w=db.scalar(select(TerritoryWar).where(TerritoryWar.territory_id=='bridge'))
            assert t.clan_id==w.attacker_clan_id
            assert w.status=='resolved'
            assert w.bid==800
            assert db.get(Clan,t.clan_id).treasury==4200


def test_war_roster_roles_and_30min_live_battle():
    with TestClient(app):
        with SessionLocal.begin() as db:
            (pa,ca),(pb,cb)=setup(db,100)
            db.get(Territory,'depot').clan_id=ca.id
            w=bid(db,pb,'depot',300,at(2026,10,12,12))
            try: roster(db,pa,w.id,pa.id,True,at(2026,10,12,14));assert False
            except ValueError:pass
        with SessionLocal.begin() as db:
            refresh_world(db,at(2026,10,13,10,5))
            w=db.scalar(select(TerritoryWar).where(TerritoryWar.territory_id=='depot'))
            assert w.status=='formation'
            pa=db.get(Player,96101);pb=db.get(Player,96102);member=db.get(Player,96103)
            try: roster(db,member,w.id,member.id,True,at(2026,10,13,11));assert False
            except ValueError:pass
            appoint(db,pa,member.id)
            db.flush()
            roster(db,member,w.id,pa.id,True,at(2026,10,13,11))
            roster(db,member,w.id,member.id,True,at(2026,10,13,11))
            roster(db,pb,w.id,pb.id,True,at(2026,10,13,11))
            roster(db,pb,w.id,96104,True,at(2026,10,13,11))
            try: roster(db,pb,w.id,96101,True,at(2026,10,13,11));assert False
            except ValueError:pass
        with SessionLocal.begin() as db:
            refresh_world(db,at(2026,10,13,16,1))
            w=db.scalar(select(TerritoryWar).where(TerritoryWar.territory_id=='depot'))
            assert w.round==2
            assert w.status in ('battle','resolved')
            if w.status=='battle':
                player=db.get(Player,96101)
                output=war_action(db,player,w.id,'guard',at(2026,10,13,16,1))
                assert 'Защитная' in output
                try:war_action(db,player,w.id,'attack',at(2026,10,13,16,1));assert False
                except ValueError:pass
        with SessionLocal.begin() as db:
            refresh_world(db,at(2026,10,13,16,31))
            w=db.scalar(select(TerritoryWar).where(TerritoryWar.territory_id=='depot'))
            assert w.status=='resolved'
            assert w.winner_clan_id in (w.attacker_clan_id,w.defender_clan_id)
            assert db.get(Territory,'depot').clan_id==w.winner_clan_id
            before=w.winner_clan_id
            refresh_world(db,at(2026,10,13,18))
            assert w.winner_clan_id==before


def test_one_percent_tax_and_five_hour_transfer():
    with TestClient(app):
        with SessionLocal.begin() as db:
            (pa,ca),(pb,cb)=setup(db,200)
            pa.location='forest'
            db.get(Territory,'bridge').clan_id=ca.id
            record=db.get(TerritoryTax,'bridge')
            record.last_collection=at(2026,10,12,12)
            assert zombie_tax(db,pa,50)==0
            assert zombie_tax(db,pa,50)==1
            assert zombie_tax(db,pa,120)==1
            assert record.remainder==20 and record.pending==2
            assert collect_tax(db,'bridge',at=at(2026,10,12,16))==0
            assert collect_tax(db,'bridge',at=at(2026,10,12,17))==2
            assert ca.treasury==5002
            assert record.pending==0 and record.collected==2
            assert collect_tax(db,'bridge',at=at(2026,10,12,17))==0
            assert ca.treasury==5002