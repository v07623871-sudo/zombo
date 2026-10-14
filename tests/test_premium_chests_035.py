"""Premium monetization contracts: Stars-funded Zombo, chests, supplies and antifarm."""
from fastapi.testclient import TestClient
from sqlalchemy import select, func

from tests.test_game import app
from armory_content import CASES, CASE_POOLS, case_drop_weights
from premium_chests import CHESTS, GEM_CASE_PRICES, EXTRA_SUPPLIES
from game import ITEMS, RECIPES, CONSUMABLE_EFFECTS, item_count, give_item
from gear import GearItem, MAX_GEAR, create_gear, RARITIES
from models import Player, SessionLocal


def auth(pid):
    return {'Authorization':f'demo:{pid}'}


def hero(api,pid):
    r=api.post('/api/class',headers=auth(pid),json={'key':'soldier'})
    assert r.status_code==200,r.text


def test_shop_is_free_of_cases_and_chests_and_stars_offers_are_unchanged():
    with TestClient(app) as api:
        shop=api.get('/api/shop').json()
        assert not any(i['key'] in set(CASES)|set(CHESTS) for i in shop)
        offers={i['key']:i for i in api.get('/api/premium').json()}
        for key in CASES:
            assert offers[key]['kind']=='case'
            assert offers[key]['price']==GEM_CASE_PRICES[key]
        for key,price,drops in (
                ('chest_common',50,3),('chest_rare',150,4),
                ('chest_legendary',500,5)):
            assert offers[key]['kind']=='chest'
            assert offers[key]['price']==price
            assert offers[key]['drops']==drops
        stars=api.get('/api/stars').json()
        assert [(x['stars'],x['zombo']) for x in stars]==[
            (100,100),(500,550),(1500,1800),(5000,6500)]


def test_premium_chest_purchase_requires_real_zombo_and_persists():
    pid=99335001
    with TestClient(app) as api:
        hero(api,pid)
        with SessionLocal.begin() as db:
            p=db.get(Player,pid)
            p.caps=99999
            p.zombo=49
        cannot=api.post('/api/premium/buy',headers=auth(pid),
                        json={'key':'chest_common'})
        assert cannot.status_code==400
        with SessionLocal() as db:
            assert item_count(db,pid,'chest_common')==0
            assert db.get(Player,pid).caps==99999
        with SessionLocal.begin() as db:
            db.get(Player,pid).zombo=100
        paid=api.post('/api/premium/buy',headers=auth(pid),
                      json={'key':'chest_common'})
        assert paid.status_code==200,paid.text
        with SessionLocal() as db:
            p=db.get(Player,pid)
            assert p.zombo==50 and p.caps==99999
            assert item_count(db,pid,'chest_common')==1
        r=api.post('/api/chests/open',headers=auth(pid),
                   json={'key':'chest_common'})
        assert r.status_code==200,r.text
        prizes=r.json()['rewards']
        assert r.json()['count']==len(prizes)==3
        assert prizes[0]['kind']=='gear'
        assert prizes[0]['key'] in (CASE_POOLS['scrap_case']+CASE_POOLS['field_case'])
        assert prizes[0]['rarity'] in CHESTS['chest_common']['rarity_weights']
        assert all(x['kind']=='item' for x in prizes[1:])
        assert api.post('/api/chests/open',headers=auth(pid),
                        json={'key':'chest_common'}).status_code==400
        with SessionLocal() as db:
            p=db.get(Player,pid)
            assert p.zombo==50 and p.caps==99999
            assert item_count(db,pid,'chest_common')==0
            assert db.scalar(select(func.count()).select_from(GearItem)
                             .where(GearItem.player_id==pid))==1


def test_all_premium_chests_have_guaranteed_strong_enough_weapons_and_exact_drops():
    for ix,(key,config) in enumerate(CHESTS.items()):
        pid=99335010+ix
        with TestClient(app) as api:
            hero(api,pid)
            with SessionLocal.begin() as db:
                db.get(Player,pid).zombo=config['price']
            bought=api.post('/api/premium/buy',headers=auth(pid),
                            json={'key':key})
            assert bought.status_code==200,bought.text
            opened=api.post('/api/chests/open',headers=auth(pid),json={'key':key})
            assert opened.status_code==200,opened.text
            prizes=opened.json()['rewards']
            assert len(prizes)==config['drops']
            assert prizes[0]['kind']=='gear'
            assert prizes[0]['rarity'] in config['rarity_weights']
            assert prizes[0]['gear']['exclusive']
            assert all(x['qty']>0 for x in prizes[1:])
            assert len(prizes[1:])==config['drops']-1
            with SessionLocal() as db:
                assert db.get(Player,pid).zombo==0
                assert item_count(db,pid,key)==0
                for prize in prizes[1:]:
                    assert item_count(db,pid,prize['key'])>=prize['qty']
            assert api.post('/api/chests/open',headers=auth(pid),
                            json={'key':key}).status_code==400
            if key=='chest_legendary':
                assert prizes[0]['rarity'] in ('epic','legendary')
                assert any(x['key']=='rare' and x['qty']>=4 for x in prizes)


def test_full_gear_locker_retains_paid_chest_and_cannot_mint_second_weapon():
    pid=99335030
    with TestClient(app) as api:
        hero(api,pid)
        with SessionLocal.begin() as db:
            db.get(Player,pid).zombo=150
            for _ in range(MAX_GEAR):
                create_gear(db,pid,'knife')
        bought=api.post('/api/premium/buy',headers=auth(pid),
                        json={'key':'chest_rare'})
        assert bought.status_code==200,bought.text
        cannot=api.post('/api/chests/open',headers=auth(pid),
                        json={'key':'chest_rare'})
        assert cannot.status_code==400,cannot.text
        with SessionLocal() as db:
            p=db.get(Player,pid)
            assert p.zombo==0
            assert item_count(db,pid,'chest_rare')==1
            assert db.scalar(select(func.count()).select_from(GearItem)
                             .where(GearItem.player_id==pid))==MAX_GEAR


def test_premium_items_cannot_be_traded_for_caps_or_materials():
    pid=99335040
    with TestClient(app) as api:
        hero(api,pid)
        with SessionLocal.begin() as db:
            give_item(db,pid,'chest_common')
            give_item(db,pid,'field_case')
        for first,second in (('chest_common','medkit'),
                             ('field_case','wood'),
                             ('wood','chest_common')):
            response=api.post('/api/market/create',headers=auth(pid),
                json={'offer':first,'qty':1,'want':second,'want_qty':1})
            assert response.status_code==400,response.text
        with SessionLocal() as db:
            assert item_count(db,pid,'chest_common')==1
            assert item_count(db,pid,'field_case')==1


def test_eight_new_free_items_have_actual_recipes_effects_and_not_just_icons():
    assert len(EXTRA_SUPPLIES)==8
    for key,data in EXTRA_SUPPLIES.items():
        assert ITEMS[key]['type']=='consumable'
        assert key in RECIPES and RECIPES[key]==data['recipe']
        assert CONSUMABLE_EFFECTS[key]==data['effect']
        assert all(qty>0 for qty in data['effect'].values())
        assert sum(data['effect'].values())>0
    pid=99335050
    with TestClient(app) as api:
        hero(api,pid)
        with SessionLocal.begin() as db:
            p=db.get(Player,pid)
            p.hp=1;p.stamina=10;p.hunger=90;p.thirst=90
            give_item(db,pid,'combat_meds')
            give_item(db,pid,'military_ration')
        for key in ('combat_meds','military_ration'):
            r=api.post('/api/item/use',headers=auth(pid),json={'key':key})
            assert r.status_code==200,r.text
        with SessionLocal() as db:
            p=db.get(Player,pid)
            assert p.hp>1 and p.stamina>10
            assert p.hunger<90 and p.thirst<90
