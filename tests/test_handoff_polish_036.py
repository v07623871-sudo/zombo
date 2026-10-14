"""Release 0.36 handoff: no fake boss/day labels and honest premium guarantees."""
from pathlib import Path

from fastapi.testclient import TestClient

from tests.test_game import app
from premium_chests import CHESTS, GEM_CASE_PRICES
from game import RECIPES, ITEMS

ROOT=Path(__file__).resolve().parents[1]


def test_rare_chest_guarantees_rare_or_better_and_late_case_values():
    rare=CHESTS['chest_rare']
    assert rare['price']==150 and rare['drops']==4
    assert rare['rarity_weights']=={'rare':75,'epic':25}
    assert 'необычная' not in rare['description']
    assert 'редкая' in rare['description']
    legendary=CHESTS['chest_legendary']
    assert legendary['price']==500 and legendary['drops']==5
    assert legendary['rarity_weights']=={'epic':70,'legendary':30}
    assert GEM_CASE_PRICES['shadow_case']==360
    assert GEM_CASE_PRICES['relic_case']==275
    assert GEM_CASE_PRICES['shadow_case']<legendary['price']


def test_live_catalog_exposes_true_chest_odds_and_prices_without_schema_change():
    with TestClient(app) as client:
        cfg=client.get('/api/config')
        assert cfg.status_code==200,cfg.text
        data=cfg.json()
        assert len(data['cases'])==7
        assert data['cases']['shadow_case']['gem_price']==360
        assert data['cases']['relic_case']['gem_price']==275
        assert 'shop_price' in data['cases']['shadow_case']
        rare=next(item for item in data['chests'] if item['key']=='chest_rare')
        assert rare['rarity_weights']=={'rare':75,'epic':25}
        assert len(RECIPES)>50 and len(ITEMS)>70
        premium=client.get('/api/premium')
        assert premium.status_code==200
        offers={x['key']:x for x in premium.json()}
        assert offers['shadow_case']['price']==360
        assert offers['relic_case']['price']==275
        assert offers['chest_rare']['price']==150


def test_mobile_lists_can_search_and_filter_and_no_fake_colossus():
    frontend=(ROOT/'static'/'app.js').read_text(encoding='utf-8')
    css=(ROOT/'static'/'style.css').read_text(encoding='utf-8')
    assert 'СВОДКА. ДЕНЬ 014' not in frontend
    assert 'Колосс пробудился' not in frontend
    assert 'АТАКОВАТЬ КОЛОССА' not in frontend
    assert 'ЖИЗНЬ КОЛОССА' not in frontend
    for text in (
        'function inventoryScreen()',
        'function craftScreen()',
        'function inventory(filtered=false)',
        "function applySearch(group)",
        "data-list-search",
        "data-search-group",
        "inventory-filter",
        "craft-filter",
        "craft-available",
        "itemKind",
        "const own=(me.inventory",
    ):
        assert text in frontend,text
    assert 'app.addEventListener(\'input\'' in frontend
    assert '.material-cost.missing' in css
    assert '[hidden]{display:none!important}' in css
    # A misleading filter that changes only its button without filtering
    # the underlying list would not have both the itemKind and ready checks.
    assert "craftFilter==='all'||x.kind===craftFilter" in frontend
    assert "(!craftReadyOnly||x.ready)" in frontend
