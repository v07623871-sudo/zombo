"""ZOMBO 0.25 workshop: 40 real craft transactions, usable outputs, zone mats."""
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.test_game import app
from game import ITEMS, RECIPES, scavenge_pool, item_count, give_item, attack_power
from gear import BASE_GEAR, GearItem
from models import Player, SessionLocal


def auth(pid):
    return {'Authorization':f'demo:{pid}'}


def test_all_forty_recipes_use_real_inputs_and_usable_outputs():
    assert len(RECIPES)>=56
    assert len(BASE_GEAR)>=52
    for key,recipe in RECIPES.items():
        output=recipe.get('output',key)
        assert output in ITEMS,key
        assert isinstance(recipe['qty'],int) and recipe['qty']>0
        assert recipe['cost'] and all(k in ITEMS and isinstance(n,int) and n>0
                                      for k,n in recipe['cost'].items()),key
        assert output in BASE_GEAR or ITEMS[output]['type'] in ('consumable','material')
    assert 'rubber' not in scavenge_pool('forest')
    assert 'rubber' in scavenge_pool('factory')
    assert 'wire' in scavenge_pool('city')
    assert 'stone' in scavenge_pool('factory')
    assert 'rare' in scavenge_pool('wasteland')


def test_craft_unique_weapon_and_armor_are_equippable_and_affect_combat():
    pid=99325001
    with TestClient(app) as client:
        assert client.post('/api/class',headers=auth(pid),json={'key':'soldier'}).status_code==200
        with SessionLocal.begin() as db:
            p=db.get(Player,pid)
            initial_attack=attack_power(db,p)
            for key,qty in RECIPES['revolver']['cost'].items():
                give_item(db,pid,key,qty)
            for key,qty in RECIPES['hardened_vest']['cost'].items():
                give_item(db,pid,key,qty)
        for key in ('revolver','hardened_vest'):
            result=client.post('/api/craft',headers=auth(pid),json={'key':key})
            assert result.status_code==200,result.text
        with SessionLocal() as db:
            gear=list(db.scalars(select(GearItem).where(GearItem.player_id==pid)))
            assert {'revolver','hardened_vest'} <= {x.base_key for x in gear}
            gear_ids={x.base_key:x.id for x in gear}
        for key in ('revolver','hardened_vest'):
            result=client.post('/api/gear/equip',headers=auth(pid),
                               json={'id':gear_ids[key]})
            assert result.status_code==200,result.text
        with SessionLocal() as db:
            p=db.get(Player,pid)
            assert attack_power(db,p)>initial_attack
        inventory=client.get('/api/gear',headers=auth(pid)).json()
        assert inventory['stats']['defense']>=6


def test_bundle_is_not_free_and_produces_correct_stacked_amount():
    pid=99325002
    with TestClient(app) as client:
        client.post('/api/class',headers=auth(pid),json={'key':'medic'})
        with SessionLocal.begin() as db:
            give_item(db,pid,'cloth',7)
            db.flush()
            initial_bandages=item_count(db,pid,'bandage')
            initial_cloth=item_count(db,pid,'cloth')
        result=client.post('/api/craft',headers=auth(pid),json={'key':'bandage_bundle'})
        assert result.status_code==200,result.text
        with SessionLocal() as db:
            assert item_count(db,pid,'bandage')==initial_bandages+4
            assert item_count(db,pid,'cloth')==initial_cloth-7
        again=client.post('/api/craft',headers=auth(pid),json={'key':'bandage_bundle'})
        assert again.status_code==400
        with SessionLocal() as db:
            assert item_count(db,pid,'bandage')==initial_bandages+4


def test_crafted_consumables_change_live_player_resources_once():
    pid=99325003
    with TestClient(app) as client:
        client.post('/api/class',headers=auth(pid),json={'key':'thief'})
        with SessionLocal.begin() as db:
            p=db.get(Player,pid)
            p.hp=10;p.stamina=40;p.hunger=80;p.thirst=85
            for key in ('bandage','stimulant','ration','water_filter'):
                give_item(db,pid,key)
        for key in ('bandage','stimulant','ration','water_filter'):
            result=client.post('/api/item/use',headers=auth(pid),json={'key':key})
            assert result.status_code==200,result.text
            again=client.post('/api/item/use',headers=auth(pid),json={'key':key})
            assert again.status_code==400
        with SessionLocal() as db:
            p=db.get(Player,pid)
            assert p.hp>10 and p.stamina==85
            assert p.hunger==20 and p.thirst==0
