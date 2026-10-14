"""0.39: paid chest rewards survive a fresh profile load and appear in backpack.

An exclusive gun is stored in unique GearItem (not ItemStack); the client must
render both inventories together. Supplies remain ItemStacks. No extra credit
must occur just to make the interface show its contents.
"""
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select, func

from tests.test_game import app
from premium_chests import CHESTS
from models import Player, SessionLocal
from gear import GearItem


def auth(pid):
    return {'Authorization':f'demo:{pid}'}


def hero(api,pid):
    r=api.post('/api/class',headers=auth(pid),json={'key':'soldier'})
    assert r.status_code==200,r.text


def stack_total(profile,key):
    return sum(i['qty'] for i in profile['inventory'] if i['key']==key)


def test_every_chest_credits_unique_weapon_and_all_supply_stacks_to_fresh_profile():
    for ix,(case,data) in enumerate(CHESTS.items()):
        pid=99339001+ix
        with TestClient(app) as api:
            hero(api,pid)
            before=api.get('/api/me',headers=auth(pid)).json()
            before_ids={g['id'] for g in before['gear']}
            with SessionLocal.begin() as db:
                db.get(Player,pid).zombo=data['price']
            purchase=api.post('/api/premium/buy',headers=auth(pid),json={'key':case})
            assert purchase.status_code==200,purchase.text
            opened=api.post('/api/chests/open',headers=auth(pid),json={'key':case})
            assert opened.status_code==200,opened.text
            rewards=opened.json()['rewards']
            assert len(rewards)==data['drops']
            awarded_gear=rewards[0]['gear']
            assert awarded_gear['id'] not in before_ids
            assert awarded_gear['source']=='premium_chest'
            expected={}
            for item in rewards[1:]:
                expected[item['key']]=expected.get(item['key'],0)+item['qty']
            # Close and re-open a new DB-backed profile HTTP request, not the
            # opening action's UI receipt.
            after=api.get('/api/me',headers=auth(pid))
            assert after.status_code==200,after.text
            profile=after.json()
            actual=[g for g in profile['gear'] if g['id']==awarded_gear['id']]
            assert len(actual)==1 and actual[0]['rarity']==awarded_gear['rarity']
            assert actual[0]['key']==awarded_gear['key']
            for key,qty in expected.items():
                assert stack_total(profile,key)==stack_total(before,key)+qty
            assert stack_total(profile,case)==0
            with SessionLocal() as db:
                persisted=db.scalar(select(GearItem).where(
                    GearItem.id==awarded_gear['id'],GearItem.player_id==pid))
                assert persisted is not None
                assert persisted.source=='premium_chest'
                assert db.get(Player,pid).zombo==0


def test_paid_single_weapon_case_is_persisted_separately_and_visible_to_client():
    pid=99339021
    with TestClient(app) as api:
        hero(api,pid)
        before=api.get('/api/me',headers=auth(pid)).json()
        with SessionLocal.begin() as db:
            db.get(Player,pid).zombo=100
        bought=api.post('/api/premium/buy',headers=auth(pid),json={'key':'field_case'})
        assert bought.status_code==200,bought.text
        opened=api.post('/api/cases/open',headers=auth(pid),json={'key':'field_case'})
        assert opened.status_code==200,opened.text
        winner=opened.json()['gear']
        later=api.get('/api/me',headers=auth(pid)).json()
        assert any(g['id']==winner['id'] and g['source']=='case' for g in later['gear'])
        assert not any(g['id']==winner['id'] for g in before['gear'])


def test_backpack_renders_all_uniques_and_stacks_with_correct_navigation():
    src=(Path(__file__).resolve().parents[1]/'static'/'app.js').read_text(encoding='utf-8')
    style=(Path(__file__).resolve().parents[1]/'static'/'style.css').read_text(encoding='utf-8')
    for marker in (
        'function ownedInventory()',
        'const stacks=(me.inventory||[])',
        'const unique=(me.gear||[])',
        'return [...unique,...stacks]',
        'const total=ownedInventory().reduce',
        "inventoryFilter==='unique'",
        "['unique','Уникальное']",
        "unique?btn(i.equipped?",
        "'loot-to-inventory'",
        "'В ИНВЕНТАРЬ'",
        "НАГРАДЫ СОХРАНЕНЫ",
    ):
        assert marker in src,marker
    assert 'inventory-unique' in style
    # ItemStack and GearItem remain separate in the database by design.
    assert src.count('const unique=(me.gear||[])')==1
