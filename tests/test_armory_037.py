"""ZOMBO 0.37: atomic equipped gear repair and player-facing UI guarantees."""
from pathlib import Path

from fastapi.testclient import TestClient

from tests.test_game import app
from gear import create_gear, equip_gear, wear_equipped, durability_of, repair_cost
from game import give_item, item_count
from models import Player, SessionLocal


def auth(pid):
    return {'Authorization':f'demo:{pid}'}


def make_hero(client,pid):
    response=client.post('/api/class',headers=auth(pid),json={'key':'soldier'})
    assert response.status_code==200,response.text


def prepare_two_metal_items(pid,metal=30,caps=10000):
    """Both items need the same currency/material to test total-cost checks."""
    with SessionLocal.begin() as db:
        p=db.get(Player,pid)
        p.caps=caps
        give_item(db,pid,'metal',metal)
        rifle=create_gear(db,pid,'rifle','rare')
        armor=create_gear(db,pid,'riot_armor','rare')
        db.flush()
        equip_gear(db,pid,rifle.id)
        db.flush()
        equip_gear(db,pid,armor.id)
        db.flush()
        wear_equipped(db,pid,'weapon',55)
        wear_equipped(db,pid,'armor',65)
        db.flush()
        assert durability_of(rifle)==45 and durability_of(armor)==35
        a,b=repair_cost(rifle),repair_cost(armor)
        assert a['material']==b['material']=='metal'
        return (rifle.id,armor.id),a['caps']+b['caps'],a['qty']+b['qty']


def test_repair_equipped_items_in_one_transaction_with_aggregated_cost():
    pid=99337001
    with TestClient(app) as api:
        make_hero(api,pid)
        ids,coins,metal=prepare_two_metal_items(pid,metal=30)
        with SessionLocal() as db:
            assert item_count(db,pid,'metal')==30
        repaired=api.post('/api/gear/repair-all',headers=auth(pid))
        assert repaired.status_code==200,repaired.text
        data=repaired.json()
        assert data['count']==2
        assert data['caps']==coins
        assert data['materials']['metal']==metal
        assert len(data['items'])==2
        assert all(item['durability']==100 for item in data['items'])
        with SessionLocal() as db:
            p=db.get(Player,pid)
            assert p.caps==10000-coins
            assert item_count(db,pid,'metal')==30-metal
        repeat=api.post('/api/gear/repair-all',headers=auth(pid))
        assert repeat.status_code==400
        with SessionLocal() as db:
            p=db.get(Player,pid)
            assert p.caps==10000-coins
            assert item_count(db,pid,'metal')==30-metal


def test_repair_all_fails_atomically_if_only_enough_metal_for_one_item():
    pid=99337002
    with TestClient(app) as api:
        make_hero(api,pid)
        ids,coins,needed=prepare_two_metal_items(pid,metal=4)
        assert needed>4
        denied=api.post('/api/gear/repair-all',headers=auth(pid))
        assert denied.status_code==400,denied.text
        with SessionLocal() as db:
            from gear import GearItem
            first=db.get(GearItem,ids[0]);second=db.get(GearItem,ids[1])
            assert durability_of(first)==45 and durability_of(second)==35
            assert db.get(Player,pid).caps==10000
            assert item_count(db,pid,'metal')==4


def test_repair_all_fails_atomically_if_caps_are_missing():
    pid=99337003
    with TestClient(app) as api:
        make_hero(api,pid)
        ids,coins,needed=prepare_two_metal_items(pid,metal=30,caps=1)
        denied=api.post('/api/gear/repair-all',headers=auth(pid))
        assert denied.status_code==400
        with SessionLocal() as db:
            from gear import GearItem
            assert durability_of(db.get(GearItem,ids[0]))==45
            assert durability_of(db.get(GearItem,ids[1]))==35
            assert db.get(Player,pid).caps==1
            assert item_count(db,pid,'metal')==30


def test_final_armory_instant_search_sort_compare_and_case_rewards_ui():
    root=Path(__file__).resolve().parents[1]
    js=(root/'static'/'app.js').read_text(encoding='utf-8')
    css=(root/'static'/'style.css').read_text(encoding='utf-8')
    from gear import repair_equipped_all
    assert callable(repair_equipped_all)
    for marker in (
        "gearSort='equipped'",
        "gearSlotFilter='all'",
        "function gearScreen()",
        "data-search-group=\"gear\"",
        "filterTabs('gear-filter'",
        "'gear-repair-all-confirm'",
        "gear/repair-all",
        "if(gearSort==='rarity')",
        "if(gearSort==='power')",
        "if(gearSort==='worn')",
        "Относительно надетого",
        "if(group==='inventory')inventoryQuery=query;else if(group==='craft')craftQuery=query;else gearQuery=query;",
        "ТВОЯ НОВАЯ ПУШКА",
        "редкий — редкой или выше",
    ):
        assert marker in js,marker
    assert ".gear-compare" in css
    assert ".gear-repair-batch" in css
