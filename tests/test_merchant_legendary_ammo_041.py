"""v0.41: merchant CSS coin and fully working legendary rounds.

Money buys single rounds, or 5 rounds can be crafted with found supplies.
Only legendary firearms use this ammunition. Legendary melee and standard
gear retain the existing combat flow; attacks never deadlock without ammo.
"""
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.test_game import app
from models import SessionLocal, Player, Battle
from gear import create_gear, equip_gear, gear_view, open_case
from game import (
    ITEMS, SHOP_PRICES, RECIPES, give_item, item_count, attack_power
)
from legendary_ammo import (
    AMMO_KEY, AMMO_SHOP_PRICE, AMMO_RECIPE, STARTER_LEGENDARY_ROUNDS,
    is_firearm, equipped_legendary_firearm, spend_legendary_round
)
from premium_chests import CHESTS, open_paid_chest


def auth(pid):
    return {'Authorization':f'demo:{pid}'}


def hero(api,pid):
    response=api.post('/api/class',headers=auth(pid),json={'key':'soldier'})
    assert response.status_code==200,response.text


def test_merchant_coin_is_css_not_broken_emoji_and_ammo_exists_for_caps():
    root=Path(__file__).resolve().parents[1]
    js=(root/'static'/'app.js').read_text(encoding='utf-8')
    css=(root/'static'/'style.css').read_text(encoding='utf-8')
    assert "'🪙 '+item.price" not in js
    assert "merchant-buy" in js and "merchant-coin" in js
    assert 'aria-hidden=' in js
    assert ".merchant-buy" in css and ".merchant-coin" in css
    assert "radial-gradient" in css
    assert "legendaryStock" in js
    assert "gear-ammo" in js
    assert AMMO_KEY in ITEMS and ITEMS[AMMO_KEY]['type']=='material'
    assert SHOP_PRICES[AMMO_KEY]==AMMO_SHOP_PRICE
    assert RECIPES[AMMO_KEY]==AMMO_RECIPE
    assert AMMO_RECIPE['qty']==5
    with TestClient(app) as api:
        offers=api.get('/api/shop').json()
        assert any(i['key']==AMMO_KEY and i['price']==AMMO_SHOP_PRICE for i in offers)
        cfg=api.get('/api/config').json()
        assert AMMO_KEY in cfg['items'] and AMMO_KEY in cfg['recipes']


def test_legendary_firearm_requires_round_for_bonus_but_never_blocks_survival():
    pid=99410001
    with TestClient(app) as api:
        hero(api,pid)
        with SessionLocal.begin() as db:
            p=db.get(Player,pid)
            rifle=create_gear(db,pid,'rifle','legendary',source='admin')
            db.flush();equip_gear(db,pid,rifle.id);db.flush()
            assert equipped_legendary_firearm(db,pid).id==rifle.id
            view=gear_view(rifle)
            assert view['ammo_key']==AMMO_KEY
            ready_power=attack_power(db,p)
            no_round=spend_legendary_round(db,pid)
            assert no_round=='empty'
            unarmed_power=attack_power(db,p,ammo_status=no_round)
            assert unarmed_power<ready_power
            give_item(db,pid,AMMO_KEY,2);db.flush()
            assert spend_legendary_round(db,pid)=='spent'
            assert item_count(db,pid,AMMO_KEY)==1
            assert attack_power(db,p,ammo_status='spent')==ready_power
            assert spend_legendary_round(db,pid)=='spent'
            assert item_count(db,pid,AMMO_KEY)==0
            assert spend_legendary_round(db,pid)=='empty'
        with SessionLocal() as db:
            assert item_count(db,pid,AMMO_KEY)==0


def test_no_rounds_for_legendary_melee_or_regular_ranged():
    for ix,(key,rarity) in enumerate((('knife','legendary'),('rifle','epic'))):
        pid=99410010+ix
        with TestClient(app) as api:
            hero(api,pid)
            with SessionLocal.begin() as db:
                weapon=create_gear(db,pid,key,rarity,source='admin')
                db.flush();equip_gear(db,pid,weapon.id)
                assert equipped_legendary_firearm(db,pid) is None
                assert gear_view(weapon)['ammo_key'] is None
                assert spend_legendary_round(db,pid)=='normal'
    assert not is_firearm('knife')
    assert not is_firearm('hunting_bow')
    assert not is_firearm('crossbow')
    assert is_firearm('shadow_apex')


class LegendaryRng:
    def choice(self,values):
        return values[0]
    def choices(self,values,weights=None,k=1):
        return ['legendary'] if 'legendary' in values else [values[0]]


def test_legendary_single_case_delivers_matching_ammo_atomically():
    pid=99410020
    with TestClient(app) as api:
        hero(api,pid)
        with SessionLocal.begin() as db:
            give_item(db,pid,'shadow_case',1)
        with SessionLocal.begin() as db:
            prize=open_case(db,pid,'shadow_case',rng=LegendaryRng())
            assert prize.rarity=='legendary'
        with SessionLocal() as db:
            assert item_count(db,pid,'shadow_case')==0
            assert item_count(db,pid,AMMO_KEY)==STARTER_LEGENDARY_ROUNDS


def test_legendary_paid_chest_has_exactly_five_prizes_including_ammo():
    pid=99410021
    with TestClient(app) as api:
        hero(api,pid)
        with SessionLocal.begin() as db:
            give_item(db,pid,'chest_legendary',1)
        with SessionLocal.begin() as db:
            prizes=open_paid_chest(db,pid,'chest_legendary',rng=LegendaryRng())
            assert len(prizes)==CHESTS['chest_legendary']['drops']==5
            assert prizes[0]['kind']=='gear'
            assert prizes[0]['rarity']=='legendary'
            assert prizes[-1]['key']==AMMO_KEY
            assert prizes[-1]['qty']==STARTER_LEGENDARY_ROUNDS
        with SessionLocal() as db:
            assert item_count(db,pid,'chest_legendary')==0
            assert item_count(db,pid,AMMO_KEY)==STARTER_LEGENDARY_ROUNDS


def test_shop_purchase_and_pve_really_consume_one_round_per_attack_attempt():
    pid=99410022
    with TestClient(app) as api:
        hero(api,pid)
        with SessionLocal.begin() as db:
            db.get(Player,pid).caps=300
        bought=api.post('/api/shop/buy',headers=auth(pid),json={'key':AMMO_KEY})
        assert bought.status_code==200,bought.text
        with SessionLocal() as db:
            assert db.get(Player,pid).caps==300-AMMO_SHOP_PRICE
            assert item_count(db,pid,AMMO_KEY)==1
        travel=api.post('/api/travel',headers=auth(pid),json={'key':'forest'})
        assert travel.status_code==200,travel.text
        with SessionLocal.begin() as db:
            weapon=create_gear(db,pid,'rifle','legendary',source='admin')
            db.flush();equip_gear(db,pid,weapon.id)
        fight=api.post('/api/combat/start',headers=auth(pid))
        assert fight.status_code==200,fight.text
        with SessionLocal.begin() as db:
            b=db.scalar(select(Battle).where(Battle.player_id==pid))
            b.enemy_hp=b.enemy_max_hp=10000
        first=api.post('/api/combat/turn',headers=auth(pid),
                       json={'action':'attack','zone':'body'})
        assert first.status_code==200,first.text
        assert 'Легендарный патрон' in first.json()['message']
        with SessionLocal() as db:
            assert item_count(db,pid,AMMO_KEY)==0
        second=api.post('/api/combat/turn',headers=auth(pid),
                        json={'action':'attack','zone':'body'})
        assert second.status_code==200,second.text
        assert 'Нет легендарных патронов' in second.json()['message']
        with SessionLocal() as db:
            assert item_count(db,pid,AMMO_KEY)==0


def test_pvp_raid_and_worldboss_apply_the_same_one_round_rule():
    app_code=(Path(__file__).resolve().parents[1]/'app.py').read_text(encoding='utf-8')
    raid_code=(Path(__file__).resolve().parents[1]/'raids.py').read_text(encoding='utf-8')
    game_code=(Path(__file__).resolve().parents[1]/'game.py').read_text(encoding='utf-8')
    assert app_code.count('spend_legendary_round(db,p.id)')>=2
    assert 'spend_legendary_round(db,p.id)' in raid_code
    assert 'spend_legendary_round(db,p.id)' in game_code
    assert "ammo_status=ammo_status" in app_code
    assert "ammo_status=ammo_status" in raid_code
