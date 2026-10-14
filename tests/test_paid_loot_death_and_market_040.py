"""ZOMBO 0.40: paid boxes must survive death; barter only lists tradable stock."""
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func,select

from tests.test_game import app
from game import death_penalty, give_item, item_count
from models import Player, SessionLocal, MarketLot, ItemStack, now


def auth(pid):
    return {'Authorization': f'demo:{pid}'}


def create_hero(api,pid):
    result=api.post('/api/class',headers=auth(pid),json={'key':'soldier'})
    assert result.status_code==200,result.text


def supply_player(pid,insured=False):
    with SessionLocal.begin() as db:
        p=db.get(Player,pid)
        p.caps=1000
        p.xp=200
        if insured:
            p.stats={**(p.stats or {}),
                '_insurance_until':(now()+timedelta(days=1)).isoformat()}
        give_item(db,pid,'chest_legendary',2)
        give_item(db,pid,'field_case',3)
        give_item(db,pid,'shadow_case',1)
        give_item(db,pid,'metal',6)
        give_item(db,pid,'wood',10)


def ordinary_total(db,pid):
    from premium_chests import CHESTS
    from armory_content import CASES
    protected=set(CASES)|set(CHESTS)
    rows=db.scalars(select(ItemStack).where(
        ItemStack.player_id==pid,ItemStack.equipped.is_(False),
        ItemStack.item_key.notin_(protected))).all()
    return sum(stack.quantity for stack in rows)


def test_paid_unopened_cases_and_chests_survive_normal_pve_death():
    pid=99400001
    with TestClient(app) as api:
        create_hero(api,pid)
        supply_player(pid)
        with SessionLocal.begin() as db:
            p=db.get(Player,pid)
            before=ordinary_total(db,pid)
            lost=death_penalty(db,p)
            assert lost['items']==before//2
            assert lost['caps']==200
            assert lost['xp']==60
        with SessionLocal() as db:
            assert item_count(db,pid,'chest_legendary')==2
            assert item_count(db,pid,'field_case')==3
            assert item_count(db,pid,'shadow_case')==1
            assert ordinary_total(db,pid)==before-lost['items']
            assert db.get(Player,pid).caps==800
            assert db.get(Player,pid).xp==140


def test_paid_containers_are_protected_with_insurance_too():
    pid=99400002
    with TestClient(app) as api:
        create_hero(api,pid)
        supply_player(pid,insured=True)
        with SessionLocal.begin() as db:
            before=ordinary_total(db,pid)
            result=death_penalty(db,db.get(Player,pid))
            assert result['insured'] and result['items']==int(before*.10)
            assert result['caps']==50 and result['xp']==20
        with SessionLocal() as db:
            assert item_count(db,pid,'chest_legendary')==2
            assert item_count(db,pid,'field_case')==3
            assert item_count(db,pid,'shadow_case')==1
            assert ordinary_total(db,pid)==before-result['items']


def test_barter_rejects_impossible_unique_gear_trade_but_keeps_valid_supplies():
    pid=99400003
    with TestClient(app) as api:
        create_hero(api,pid)
        with SessionLocal() as db:
            wood=item_count(db,pid,'wood')
            assert wood>0
            old=db.scalar(select(func.count()).select_from(MarketLot).where(MarketLot.seller_id==pid))
        for offer,want in [('wood','shadow_apex'),('shadow_apex','metal'),
                           ('wood','chest_common'),('field_case','metal')]:
            res=api.post('/api/market/create',headers=auth(pid),
                         json={'offer':offer,'qty':1,'want':want,'want_qty':1})
            assert res.status_code==400,(offer,want,res.text)
        with SessionLocal() as db:
            assert item_count(db,pid,'wood')==wood
            assert db.scalar(select(func.count()).select_from(MarketLot).where(MarketLot.seller_id==pid))==old
        good=api.post('/api/market/create',headers=auth(pid),
                      json={'offer':'wood','qty':1,'want':'metal','want_qty':1})
        assert good.status_code==200,good.text


def test_barter_modal_is_not_populated_with_nonexistent_paid_stacks():
    src=(Path(__file__).resolve().parents[1]/'static'/'app.js').read_text(encoding='utf-8')
    assert "if(action==='market-create')" in src
    assert "const owned=(me.inventory||[]).filter" in src
    assert "item.qty>0&&" in src
    assert "meta.type!=='case'&&meta.type!=='chest'" in src
    assert "['knife','vest','pistol','rifle'].includes(key)" in src
    assert "if(!owned.length)" in src
    assert "уникальные пушки не торгуются" in src.lower()
    assert "Object.entries(cfg.items).filter(([key,item])=>allowed(key,item))" in src
