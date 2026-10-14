"""Seven case-exclusive collections retained, now sold strictly for Zombo."""
from fastapi.testclient import TestClient
from sqlalchemy import select, func

from tests.test_game import app
from armory_content import (
    CASES, CASE_POOLS, CASE_SHOP_PRICES, NEW_GEAR,
    case_drop_weights, raid_case_drop, validate_case_balance,
)
from premium_chests import GEM_CASE_PRICES
from gear import (
    GearItem, RARITIES, create_gear, upgrade_cost, repair_cost,
    equip_gear, wear_equipped, roll_case_drop
)
from game import RECIPES, SHOP_PRICES, ITEMS, item_count
from models import Player, SessionLocal


NEW_CASES=('scrap_case','hunter_case','assault_case','shadow_case')


def auth(pid):
    return {'Authorization':f'demo:{pid}'}


def hero(client,pid):
    response=client.post('/api/class',headers=auth(pid),json={'key':'soldier'})
    assert response.status_code==200,response.text


def test_seven_cases_and_twenty_eight_real_weapons_are_all_premium_only():
    validate_case_balance()
    assert len(CASES)==7 and all(len(pool)==4 for pool in CASE_POOLS.values())
    assert len(set().union(*(set(p) for p in CASE_POOLS.values())))==28
    assert set(GEM_CASE_PRICES)==set(CASES)
    assert not (set(CASES)&set(SHOP_PRICES))
    assert not (set(CASES)&set(RECIPES))
    for key,pool in CASE_POOLS.items():
        assert sum(CASES[key]['rarity_weights'].values())==100
        for gun in pool:
            assert gun not in RECIPES and NEW_GEAR[gun]['exclusive']
            assert ITEMS[gun]['power']==NEW_GEAR[gun]['power']
    assert len(NEW_CASES)==4


def test_case_expected_strength_stays_ordered_without_runaway_power_creep():
    def expected(case):
        guns=CASE_POOLS[case]
        base=sum(NEW_GEAR[g]['power'] for g in guns)/len(guns)
        return base*sum(RARITIES[r]['mult']*weight/100
                        for r,weight in CASES[case]['rarity_weights'].items())
    order=['scrap_case','field_case','hunter_case','military_case',
           'assault_case','relic_case','shadow_case']
    scores=[expected(k) for k in order]
    assert scores==sorted(scores),scores
    assert scores[-1]/scores[-2]<1.15


def test_cases_never_spawn_in_pve_or_raids():
    for threat in range(1,6):
        assert set(case_drop_weights(threat))==set(CASES)
        assert all(value==0 for value in case_drop_weights(threat).values())
        assert roll_case_drop(threat) is None
    for scenario in ('outpost','vault','citadel'):
        assert raid_case_drop(scenario) is None


def test_any_of_four_new_legacy_cases_can_still_open():
    from game import give_item
    for ix,key in enumerate(NEW_CASES):
        pid=99334010+ix
        with TestClient(app) as api:
            hero(api,pid)
            config=api.get('/api/config').json()
            assert config['cases'][key]['shop_price'] is None
            assert config['cases'][key]['gem_price']==GEM_CASE_PRICES[key]
            with SessionLocal.begin() as db:
                give_item(db,pid,key)
            opened=api.post('/api/cases/open',headers=auth(pid),json={'key':key})
            assert opened.status_code==200,opened.text
            reward=opened.json()['gear']
            assert reward['exclusive'] and reward['key'] in CASE_POOLS[key]
            assert reward['rarity'] in CASES[key]['rarity_weights']
            assert api.post('/api/cases/open',headers=auth(pid),json={'key':key}).status_code==400
            with SessionLocal() as db:
                assert item_count(db,pid,key)==0


def test_case_shop_requires_gems_not_caps_and_cannot_print_currency():
    pid=99334020
    with TestClient(app) as api:
        hero(api,pid)
        with SessionLocal.begin() as db:
            db.get(Player,pid).caps=10000
        assert api.post('/api/shop/buy',headers=auth(pid),
                        json={'key':'scrap_case'}).status_code==400
        assert api.post('/api/premium/buy',headers=auth(pid),
                        json={'key':'scrap_case'}).status_code==400
        with SessionLocal.begin() as db:
            db.get(Player,pid).zombo=100
        bought=api.post('/api/premium/buy',headers=auth(pid),
                        json={'key':'scrap_case'})
        assert bought.status_code==200,bought.text
        with SessionLocal() as db:
            p=db.get(Player,pid)
            assert p.caps==10000 and p.zombo==100-GEM_CASE_PRICES['scrap_case']
            assert item_count(db,pid,'scrap_case')==1
        opened=api.post('/api/cases/open',headers=auth(pid),
                        json={'key':'scrap_case'})
        assert opened.status_code==200,opened.text
        assert opened.json()['gear']['exclusive']
        with SessionLocal() as db:
            assert db.get(Player,pid).caps==10000


def test_exclusive_upgrades_and_repairs_remain_more_expensive():
    pid=99334021
    with TestClient(app) as api:
        hero(api,pid)
        with SessionLocal.begin() as db:
            normal=create_gear(db,pid,'rifle','rare','craft')
            special=create_gear(db,pid,'assault_warden','rare','case')
            assert upgrade_cost(special)['caps']>upgrade_cost(normal)['caps']
            assert upgrade_cost(special)['qty']>=upgrade_cost(normal)['qty']
            for level,need in ((4,1),(7,2),(9,3)):
                normal.level=level;special.level=level
                assert upgrade_cost(special)['rare']==need
            normal.level=special.level=0
            equip_gear(db,pid,special.id);wear_equipped(db,pid,'weapon',75)
            equip_gear(db,pid,normal.id);wear_equipped(db,pid,'weapon',75)
            assert repair_cost(special)['caps']>repair_cost(normal)['caps']
