"""Concurrent economy checks against a disposable PostgreSQL database only.

Run from the project root with ZOMBO_TEST_DATABASE=1, DEMO_MODE=1 and a
temporary DATABASE_URL. The CI job supplies its own PostgreSQL service.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.engine.url import make_url

assert os.getenv('ZOMBO_TEST_DATABASE') == '1', 'Explicit disposable DB marker required'
assert os.getenv('DATABASE_URL', '').startswith('postgresql'), 'PostgreSQL required'
assert make_url(os.environ['DATABASE_URL']).database.endswith(('_ci', '_test')), 'Disposable DB name required'
assert os.getenv('DEMO_MODE') == '1' and not os.getenv('BOT_TOKEN'), 'Demo auth only'

from app import app
from game import give_item, item_count
from gear import GearItem, create_gear
from gear_market import GearSale
from models import Base, Clan, MarketLot, Player, SessionLocal, Territory, TerritoryWar, engine, now
from raids import RaidRun, RaidMember
from expeditions import ExpeditionRun, ExpeditionMember
from clan_wars import ZONE, bid, settle_war
from clan_missions import (ClanSeasonScore, ClanSeasonContribution,
                           ClanSeasonRewardClaim)
import clan_missions


@event.listens_for(engine, 'connect')
def bounded_locks(connection, _record):
    with connection.cursor() as cursor:
        cursor.execute("SET lock_timeout = '12s'")
        cursor.execute("SET statement_timeout = '20s'")


Base.metadata.create_all(bind=engine)


def auth(player_id):
    return {'Authorization': f'demo:{player_id}'}


def create_player(api, player_id):
    response = api.post('/api/class', headers=auth(player_id), json={'key': 'soldier'})
    assert response.status_code == 200, (player_id, response.text)


def concurrent_post(api, path, actors, body_for):
    barrier = Barrier(len(actors))

    def send(player_id):
        barrier.wait(timeout=10)
        return api.post(path, headers=auth(player_id), json=body_for(player_id))

    with ThreadPoolExecutor(max_workers=len(actors)) as pool:
        return list(pool.map(send, actors))


with TestClient(app) as api:
    seller_id = 9928000101
    buyers = [9928000102, 9928000103, 9928000104, 9928000105, 9928000106]
    for pid in [seller_id, *buyers]:
        create_player(api, pid)
    with SessionLocal.begin() as db:
        seller = db.get(Player, seller_id)
        seller.caps = 0
        for pid in buyers:
            db.get(Player, pid).caps = 100
        gear = create_gear(db, seller_id, 'rifle')
        gear_id = gear.id
    listed = api.post('/api/gear-market/list', headers=auth(seller_id),
                      json={'gear_id': gear_id, 'price': 100})
    assert listed.status_code == 200, listed.text
    sale_id = listed.json()['sale_id']
    results = concurrent_post(api, '/api/gear-market/buy', buyers,
                              lambda _pid: {'id': sale_id})
    assert sorted(r.status_code for r in results) == [200, 400, 400, 400, 400], (
        [(r.status_code, r.text) for r in results])
    with SessionLocal.begin() as db:
        sale = db.get(GearSale, sale_id)
        assert sale.status == 'sold' and sale.buyer_id in buyers
        assert db.get(GearItem, gear_id).player_id == sale.buyer_id
        assert db.get(Player, seller_id).caps == 95
        assert sum(db.get(Player, pid).caps for pid in buyers) == 400
        assert all(db.get(Player, pid).caps >= 0 for pid in buyers)
    print('PostgreSQL: five simultaneous buyers, one sale and one payment: PASS')

    # Reciprocal trades used to lock owners in opposite order. Each trade
    # must finish without a database deadlock or duplicated inventory.
    a, b = 9928000201, 9928000202
    for pid in (a, b):
        create_player(api, pid)
    with SessionLocal.begin() as db:
        give_item(db, a, 'wood', 2)
        give_item(db, b, 'metal', 2)
        db.flush()
        initial_wood = sum(item_count(db, pid, 'wood') for pid in (a, b))
        initial_metal = sum(item_count(db, pid, 'metal') for pid in (a, b))
    for pid, offer, want in ((a, 'wood', 'metal'), (b, 'metal', 'wood')):
        response = api.post('/api/market/create', headers=auth(pid),
                            json={'offer': offer, 'qty': 1, 'want': want, 'want_qty': 1})
        assert response.status_code == 200, response.text
    with SessionLocal.begin() as db:
        lots = {lot.seller_id: lot.id for lot in db.scalars(
            select(MarketLot).where(MarketLot.seller_id.in_([a, b]),
                                    MarketLot.active.is_(True)))}
    results = concurrent_post(api, '/api/market/buy', [a, b],
                              lambda pid: {'id': lots[b if pid == a else a]})
    assert all(r.status_code == 200 for r in results), (
        [(r.status_code, r.text) for r in results])
    with SessionLocal.begin() as db:
        assert not any(db.get(MarketLot, lot_id).active for lot_id in lots.values())
        assert sum(item_count(db, pid, 'wood') for pid in (a, b)) == initial_wood
        assert sum(item_count(db, pid, 'metal') for pid in (a, b)) == initial_metal
        assert all(item_count(db, pid, key) >= 0 for pid in (a, b) for key in ('wood', 'metal'))
    print('PostgreSQL: reciprocal barter, preserved inventory, no deadlock: PASS')

    # Three contributors race to claim the same completed raid twice each.
    raiders = [9928000301, 9928000302, 9928000303]
    for pid in raiders:
        create_player(api, pid)
    with SessionLocal.begin() as db:
        raid = RaidRun(creator_id=raiders[0], scenario='outpost', status='cleared',
                       stage=2, expires_at=now()+timedelta(hours=1), log=[])
        db.add(raid); db.flush()
        raid_id = raid.id
        for pid in raiders:
            db.add(RaidMember(run_id=raid_id, player_id=pid, hp=100, max_hp=100,
                              actions=1, contribution=0))
        caps_before = {pid: db.get(Player, pid).caps for pid in raiders}
    results = concurrent_post(api, '/api/raids/claim', raiders * 2,
                              lambda _pid: {'id': raid_id})
    assert sorted(r.status_code for r in results) == [200, 200, 200, 400, 400, 400], (
        [(r.status_code, r.text) for r in results])
    with SessionLocal.begin() as db:
        for pid in raiders:
            assert db.get(Player, pid).caps == caps_before[pid] + 85
            assert db.scalar(select(RaidMember).where(RaidMember.run_id==raid_id,
                RaidMember.player_id==pid)).rewarded
    print('PostgreSQL: three players, six raid reward claims, exactly three payouts: PASS')

    crew = [9928000401, 9928000402, 9928000403]
    for pid in crew:
        create_player(api, pid)
    with SessionLocal.begin() as db:
        for pid in crew:
            db.get(Player, pid).level = 5
        run = ExpeditionRun(creator_id=crew[0], scenario='relay', status='cleared',
                            lobby_expires_at=now()-timedelta(hours=13),
                            started_at=now()-timedelta(hours=12),
                            finishes_at=now()-timedelta(minutes=1),
                            will_succeed=True, success_chance=90)
        db.add(run); db.flush()
        run_id = run.id
        for pid in crew:
            db.add(ExpeditionMember(run_id=run_id, player_id=pid, role='guard'))
        caps_before = {pid: db.get(Player, pid).caps for pid in crew}
    results = concurrent_post(api, '/api/expeditions/claim', crew * 2,
                              lambda _pid: {'id': run_id})
    assert sorted(r.status_code for r in results) == [200, 200, 200, 400, 400, 400], (
        [(r.status_code, r.text) for r in results])
    with SessionLocal.begin() as db:
        for pid in crew:
            assert db.get(Player, pid).caps == caps_before[pid] + 180
            assert db.scalar(select(ExpeditionMember).where(ExpeditionMember.run_id==run_id,
                ExpeditionMember.player_id==pid)).rewarded
            assert db.scalar(select(GearItem).where(GearItem.player_id==pid,
                GearItem.source=='expedition')) is not None
    print('PostgreSQL: three players, six expedition reward claims, exactly three payouts: PASS')

    # Simultaneous bids for the same territory must reserve only the winning
    # amount. Three workers then try to finish the same war.
    leaders = [9928000501, 9928000502, 9928000503]
    with SessionLocal.begin() as db:
        clan_ids = []
        for pid in leaders:
            db.add(Player(id=pid, name=f'CI Leader {pid}', hero_class='soldier',
                          level=12, caps=500, stats={'strength':0,'agility':0,
                          'endurance':0,'accuracy':0,'regen':0,'luck':0}, skills=[]))
            db.flush()
            clan = Clan(name=f'CI War {pid}', leader_id=pid, treasury=5000)
            db.add(clan)
            db.flush()
            db.get(Player, pid).clan_id = clan.id
            clan_ids.append(clan.id)
        db.get(Territory, 'bridge').clan_id = clan_ids[2]
    bidding_at = datetime(2026, 10, 12, 12, tzinfo=ZONE).astimezone(timezone.utc)
    barrier = Barrier(2)

    def place_bid(pid, amount):
        barrier.wait(timeout=10)
        try:
            with SessionLocal.begin() as db:
                return bid(db, db.get(Player, pid), 'bridge', amount, at=bidding_at).bid
        except ValueError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda pair: place_bid(*pair),
                                 [(leaders[0], 400), (leaders[1], 600)]))
    assert 600 in outcomes, outcomes
    with SessionLocal.begin() as db:
        war = db.scalar(select(TerritoryWar).where(
            TerritoryWar.territory_id == 'bridge', TerritoryWar.war_date == '2026-10-13'))
        assert war and war.bid == 600 and war.attacker_clan_id == clan_ids[1]
        assert db.get(Clan, clan_ids[0]).treasury == 5000
        assert db.get(Clan, clan_ids[1]).treasury == 4400
        war_id = war.id
    finished_at = datetime(2026, 10, 13, 16, 31, tzinfo=ZONE).astimezone(timezone.utc)
    barrier = Barrier(3)

    def finish_war(_):
        barrier.wait(timeout=10)
        with SessionLocal.begin() as db:
            war = db.scalar(select(TerritoryWar).where(TerritoryWar.id == war_id).with_for_update())
            settle_war(db, war, at=finished_at)
            return war.status, war.winner_clan_id

    with ThreadPoolExecutor(max_workers=3) as pool:
        settled = list(pool.map(finish_war, range(3)))
    assert settled == [('resolved', clan_ids[2])] * 3, settled
    with SessionLocal.begin() as db:
        assert db.get(Territory, 'bridge').clan_id == clan_ids[2]
        assert db.get(Clan, clan_ids[1]).treasury == 4400
    print('PostgreSQL: concurrent bids, refunded loser and idempotent war settlement: PASS')

    # Three eligible clan members submit the same season reward twice each.
    season_players = [9928000601, 9928000602, 9928000603]
    for pid in season_players:
        create_player(api, pid)
    with SessionLocal.begin() as db:
        clan = Clan(name='CI Season Rewards', leader_id=season_players[0], treasury=0)
        db.add(clan); db.flush()
        season_clan_id = clan.id
        before = {}
        for pid in season_players:
            player = db.get(Player, pid)
            player.clan_id = season_clan_id
            before[pid] = player.caps
            db.add(ClanSeasonContribution(season='2030-03', clan_id=season_clan_id,
                                          player_id=pid, amount=10))
        db.add(ClanSeasonScore(season='2030-03', clan_id=season_clan_id,
                               points=120, completed=1))
    fixed_now = datetime(2030, 4, 1, 1, 5, tzinfo=timezone.utc)
    original_now = clan_missions.now
    clan_missions.now = lambda: fixed_now
    try:
        results = concurrent_post(api, '/api/clan-missions/season-claim',
                                  season_players * 2, lambda _pid: None)
    finally:
        clan_missions.now = original_now
    assert sorted(r.status_code for r in results) == [200, 200, 200, 400, 400, 400], (
        [(r.status_code, r.text) for r in results])
    with SessionLocal.begin() as db:
        for pid in season_players:
            assert db.get(Player, pid).caps == before[pid] + 120
            assert db.get(ClanSeasonRewardClaim, ('2030-03', pid)).caps == 120
    print('PostgreSQL: three clan members, six season reward claims, exactly three payouts: PASS')
