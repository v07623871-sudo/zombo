"""0.33: balance, durable equipment, real case payouts and transaction safety."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func

from tests.test_game import app
from models import Player, ItemStack, SessionLocal
from gear import (
    BASE_GEAR, GearItem, GearCondition, MAX_GEAR, create_gear, gear_stats,
    gear_view, durability_of, wear_equipped, repair_gear, open_case,
    roll_case_drop, equip_gear, RARITIES,
)
from armory_content import NEW_RECIPES, CASES, CASE_POOLS, NEW_GEAR, case_drop_weights
from game import ITEMS, RECIPES, item_count, give_item


def auth(pid):
    return {'Authorization':f'demo:{pid}'}


def create(api,pid):
    response=api.post('/api/class',headers=auth(pid),json={'key':'soldier'})
    assert response.status_code==200,response.text


def test_catalog_has_16_craftables_12_unguessable_noncraft_case_exclusives():
    assert len(NEW_RECIPES)==16 and len(CASES)==7
    assert len(RECIPES)>=56
    exclusive={key for key,v in NEW_GEAR.items() if v.get('exclusive')}
    assert len(exclusive)==28
    assert not exclusive.intersection(RECIPES)
    for key,pool in CASE_POOLS.items():
        assert len(pool)==4 and set(pool)<=exclusive
        assert sum(CASES[key]['rarity_weights'].values())==100
        assert all(k in RARITIES for k in CASES[key]['rarity_weights'])
    for key,recipe in NEW_RECIPES.items():
        assert key in BASE_GEAR and key in ITEMS
        assert all(mat in ITEMS and qty>0 for mat,qty in recipe['cost'].items())
    # Case-only purchases: no free case printing from monster wins.
    for threat in range(1,6):
        assert sum(case_drop_weights(threat).values())==0


def test_open_case_consumes_one_real_item_and_mints_exclusive_gun_only_once():
    pid=99333001
    with TestClient(app) as api:
        create(api,pid)
        with SessionLocal.begin() as db:give_item(db,pid,'field_case',1)
        before=api.get('/api/me',headers=auth(pid)).json()
        assert any(x['key']=='field_case' for x in before['inventory'])
        response=api.post('/api/cases/open',headers=auth(pid),json={'key':'field_case'})
        assert response.status_code==200,response.text
        prize=response.json()['gear']
        assert prize['exclusive'] and prize['key'] in CASE_POOLS['field_case']
        assert prize['source']=='case' and prize['durability']==100
        assert prize['rarity'] in CASES['field_case']['rarity_weights']
        assert prize['level']==0
        second=api.post('/api/cases/open',headers=auth(pid),json={'key':'field_case'})
        assert second.status_code==400
        with SessionLocal() as db:
            assert item_count(db,pid,'field_case')==0
            assert db.scalar(select(func.count()).select_from(GearItem)
                             .where(GearItem.player_id==pid))==1


def test_noncraftable_exclusive_gun_rejected_through_generic_creation():
    pid=99333002
    with TestClient(app) as api:
        create(api,pid)
        with SessionLocal.begin() as db:
            with pytest.raises(ValueError,match='кейса'):
                create_gear(db,pid,'black_sun','legendary','craft')
        attempt=api.post('/api/craft',headers=auth(pid),json={'key':'black_sun'})
        assert attempt.status_code==400


def test_full_gear_locker_prevents_case_consumption_and_orphan_gear():
    pid=99333003
    with TestClient(app) as api:
        create(api,pid)
        with SessionLocal.begin() as db:
            give_item(db,pid,'military_case',1)
            for _ in range(MAX_GEAR):create_gear(db,pid,'knife','common')
        response=api.post('/api/cases/open',headers=auth(pid),
                          json={'key':'military_case'})
        assert response.status_code==400,response.text
        with SessionLocal() as db:
            assert item_count(db,pid,'military_case')==1
            assert db.scalar(select(func.count()).select_from(GearItem)
                             .where(GearItem.player_id==pid))==MAX_GEAR


def test_gear_wear_reduces_actual_attack_and_armor_then_repairs_at_real_cost():
    pid=99333004
    with TestClient(app) as api:
        create(api,pid)
        with SessionLocal.begin() as db:
            p=db.get(Player,pid)
            p.caps=10000
            give_item(db,pid,'metal',30)
            gun=create_gear(db,pid,'rifle','rare')
            equip_gear(db,pid,gun.id)
            assert gear_view(gun)['durability']==100
            original=gear_stats(db,pid)['power']
            for _ in range(70):wear_equipped(db,pid,'weapon',1)
            assert durability_of(gun)==30
            assert gear_stats(db,pid)['power']<original
            cost=gear_view(gun)['repair_cost']
            assert cost['caps']>0 and cost['qty']>0
            funds=p.caps
            materials=item_count(db,pid,'metal')
            repair_gear(db,p,gun.id)
            assert durability_of(gun)==100
            assert gear_stats(db,pid)['power']==original
            assert p.caps==funds-cost['caps']
            db.flush()
            assert item_count(db,pid,'metal')==materials-cost['qty']
            with pytest.raises(ValueError,match='целая'):
                repair_gear(db,p,gun.id)
        with SessionLocal() as db:
            gun=db.scalar(select(GearItem).where(GearItem.player_id==pid))
            assert durability_of(gun)==100


def test_worn_gear_becomes_broken_then_can_be_repaired():
    pid=99333005
    with TestClient(app) as api:
        create(api,pid)
        with SessionLocal.begin() as db:
            p=db.get(Player,pid)
            p.caps=10000
            give_item(db,pid,'cloth',25)
            vest=create_gear(db,pid,'vest','common')
            equip_gear(db,pid,vest.id)
            wear_equipped(db,pid,'armor',100)
            assert gear_stats(db,pid)['defense']==0
            assert gear_view(vest)['durability']==0
            repair_gear(db,p,vest.id)
            assert gear_stats(db,pid)['defense']>0


def test_repair_cannot_target_another_players_gear():
    owner,thief=99333006,99333007
    with TestClient(app) as api:
        create(api,owner);create(api,thief)
        with SessionLocal.begin() as db:
            item=create_gear(db,owner,'rifle')
            equip_gear(db,owner,item.id)
            wear_equipped(db,owner,'weapon',10)
            item_id=item.id
        forged=api.post('/api/gear/repair',headers=auth(thief),json={'id':item_id})
        assert forged.status_code==400


def test_legacy_gear_without_condition_is_full_health():
    pid=99333008
    with TestClient(app) as api:
        create(api,pid)
        with SessionLocal.begin() as db:
            item=create_gear(db,pid,'vest','rare')
            db.flush()
            assert item.condition is None
            assert gear_view(item)['durability']==100
            assert gear_view(item)['repair_cost'] is None
