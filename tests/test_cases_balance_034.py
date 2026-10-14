"""Seven-case balance regression: odds, sinks, rare loot, duplicate safety."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func

from tests.test_game import app
from armory_content import (
    CASES, CASE_POOLS, CASE_SHOP_PRICES, NEW_GEAR,
    case_drop_weights, raid_case_drop, RAID_CASE_WEIGHTS,
    RAID_CASE_CHANCE, validate_case_balance,
)
from gear import (
    GearItem, RARITIES, create_gear, upgrade_cost, repair_cost,
    equip_gear, wear_equipped, open_case, roll_case_drop, dismantle_gear,
)
from game import RECIPES, SHOP_PRICES, ITEMS, item_count, give_item
from models import Player, SessionLocal


NEW_CASES=('scrap_case','hunter_case','assault_case','shadow_case')


def auth(pid):
    return {'Authorization':f'demo:{pid}'}


def hero(client,pid):
    response=client.post('/api/class',headers=auth(pid),json={'key':'soldier'})
    assert response.status_code==200,response.text


def test_seven_cases_exactly_28_unique_noncraftable_guns():
    validate_case_balance()
    assert len(CASES)==7 and len(CASE_POOLS)==7
    assert all(len(CASE_POOLS[key])==4 for key in CASES)
    assert len(set().union(*map(set,CASE_POOLS.values())))==28
    assert len(NEW_CASES)==4
    for key in NEW_CASES:
        assert key in CASES and key in ITEMS and key in CASE_POOLS
        assert sum(CASES[key]['rarity_weights'].values())==100
        for gun in CASE_POOLS[key]:
            assert gun not in RECIPES
            assert NEW_GEAR[gun]['exclusive'] is True
            assert ITEMS[gun]['power']==NEW_GEAR[gun]['power']
    assert 'relic_case' not in CASE_SHOP_PRICES
    assert 'shadow_case' not in CASE_SHOP_PRICES
    assert CASE_SHOP_PRICES=={
        'scrap_case':480,'field_case':650,'hunter_case':1750,
        'military_case':3000,'assault_case':5200}
    assert all(SHOP_PRICES[k]==v for k,v in CASE_SHOP_PRICES.items())


def test_case_expected_strength_grows_with_cost_and_threat():
    def expected_power(case):
        weapons=CASE_POOLS[case]
        raw=sum(NEW_GEAR[k]['power'] for k in weapons)/len(weapons)
        weights=CASES[case]['rarity_weights']
        multiplier=sum(RARITIES[k]['mult']*v/100 for k,v in weights.items())
        return raw*multiplier
    normal=['scrap_case','field_case','hunter_case','military_case',
            'assault_case','relic_case','shadow_case']
    observed=[expected_power(x) for x in normal]
    assert observed==sorted(observed), observed
    # Marginal power growth, not exponential case damage inflation.
    assert observed[-1]/observed[-2]<1.15
    assert observed[4]/observed[3]<1.20
    assert observed[1]/observed[0]<1.50


def test_location_case_odds_and_all_seven_cases_reachable_without_multi_drops():
    for level in range(1,6):
        odds=case_drop_weights(level)
        assert set(odds)==set(CASES)
        assert 0<sum(odds.values())<2
        for key,value in odds.items():
            if value:
                assert value<=1.0
    assert case_drop_weights(1)['shadow_case']==0
    assert case_drop_weights(4)['shadow_case']==0
    assert case_drop_weights(5)['shadow_case']>0
    # Walk precisely into each disjoint cumulative probability interval.
    high=case_drop_weights(5)
    keys=sorted(high,key=lambda k:CASES[k]['tier'],reverse=True)
    cumulative=0
    class FakeRng:
        def __init__(self,value):self.value=value
        def random(self):return self.value
    for key in keys:
        width=high[key]
        if not width:continue
        result=roll_case_drop(5,FakeRng((cumulative+width*.5)/100))
        assert result==key,(result,key)
        cumulative+=width
    assert roll_case_drop(5,FakeRng(.5)) is None


def test_raid_cases_are_selected_after_a_real_win_gate():
    class Fixed:
        def __init__(self,roll,choice):self.roll,self.choice=roll,choice
        def random(self):return self.roll
        def choices(self,values,weights,k):
            assert k==1 and len(values)==len(weights)
            return [self.choice]
    for scenario,odds in RAID_CASE_WEIGHTS.items():
        assert sum(odds.values())==100
        assert all(k in CASES for k in odds)
        allowed=list(odds)
        assert raid_case_drop(scenario,Fixed(0,allowed[0]))==allowed[0]
        assert raid_case_drop(scenario,Fixed(RAID_CASE_CHANCE[scenario],allowed[0])) is None
    assert 'shadow_case' in RAID_CASE_WEIGHTS['citadel']
    assert 'shadow_case' not in RAID_CASE_WEIGHTS['outpost']
    with pytest.raises(ValueError):
        raid_case_drop('invalid')


def test_four_new_cases_can_open_and_only_one_weapon_is_paid():
    for idx,key in enumerate(NEW_CASES):
        pid=99334010+idx
        with TestClient(app) as client:
            hero(client,pid)
            catalog=client.get('/api/config').json()['cases']
            assert len(catalog)==7
            assert set(catalog[key]['weapons'])==set(CASE_POOLS[key])
            assert sum(catalog[key]['rarity_weights'].values())==100
            with SessionLocal.begin() as db:
                give_item(db,pid,key,1)
            receipt=client.post('/api/cases/open',headers=auth(pid),json={'key':key})
            assert receipt.status_code==200,receipt.text
            view=receipt.json()['gear']
            assert view['exclusive'] and view['key'] in CASE_POOLS[key]
            assert view['rarity'] in CASES[key]['rarity_weights']
            assert view['source']=='case'
            duplicate=client.post('/api/cases/open',headers=auth(pid),json={'key':key})
            assert duplicate.status_code==400
            with SessionLocal() as db:
                assert item_count(db,pid,key)==0
                assert db.scalar(select(func.count()).select_from(GearItem).where(
                    GearItem.player_id==pid))==1


def test_shop_case_stays_money_sink_even_after_dismantling_and_discounted_duplicate():
    pid=99334020
    with TestClient(app) as client:
        hero(client,pid)
        with SessionLocal.begin() as db:
            p=db.get(Player,pid);p.caps=5000
        buy=client.post('/api/shop/buy',headers=auth(pid),json={'key':'scrap_case'})
        assert buy.status_code==200,buy.text
        with SessionLocal() as db:
            assert db.get(Player,pid).caps==5000-480
            assert item_count(db,pid,'scrap_case')==1
        opened=client.post('/api/cases/open',headers=auth(pid),json={'key':'scrap_case'})
        assert opened.status_code==200,opened.text
        with SessionLocal.begin() as db:
            p=db.get(Player,pid)
            gear=db.scalar(select(GearItem).where(GearItem.player_id==pid))
            with patch('gear.random.random',return_value=0):
                loot=dismantle_gear(db,pid,gear.id)
            # Rare salvage never prints caps and common/uncommon prints no rare tokens.
            assert loot['material'] in ('metal','wood')
            assert loot['rare']<=1
            assert p.caps==4520
        with SessionLocal() as db:
            assert db.get(Player,pid).caps==4520


def test_exclusive_upgrade_and_repair_are_costlier_than_equivalent_crafted_gun():
    pid=99334021
    with TestClient(app) as client:
        hero(client,pid)
        with SessionLocal.begin() as db:
            crafted=create_gear(db,pid,'rifle','rare','craft')
            casegun=create_gear(db,pid,'assault_warden','rare','case')
            assert upgrade_cost(casegun)['caps']>upgrade_cost(crafted)['caps']
            assert upgrade_cost(casegun)['qty']>=upgrade_cost(crafted)['qty']
            for level,expected in ((4,1),(7,2),(9,3)):
                crafted.level=level
                casegun.level=level
                assert upgrade_cost(casegun)['rare']==expected
            crafted.level=0;casegun.level=0
            equip_gear(db,pid,casegun.id)
            wear_equipped(db,pid,'weapon',75)
            equip_gear(db,pid,crafted.id)
            wear_equipped(db,pid,'weapon',75)
            assert repair_cost(casegun)['caps']>repair_cost(crafted)['caps']
            assert repair_cost(casegun)['qty']>=repair_cost(crafted)['qty']


def test_all_old_and_new_exclusives_refuse_crafting():
    pid=99334022
    with TestClient(app) as client:
        hero(client,pid)
        with SessionLocal.begin() as db:
            for key in CASE_POOLS['shadow_case']:
                with pytest.raises(ValueError,match='кейса'):
                    create_gear(db,pid,key,'legendary','craft')
        result=client.post('/api/craft',headers=auth(pid),json={'key':'shadow_apex'})
        assert result.status_code==400
