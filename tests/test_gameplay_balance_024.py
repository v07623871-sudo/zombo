"""Release 0.24: real class perks, insured losses and consumable money sinks."""
from collections import Counter
from datetime import timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.test_game import app
from game import CLASSES, combat_round, death_penalty, insurance_active, max_hp, tick, STAMINA_REGEN_PER_TICK
from models import Battle, ItemStack, Player, SessionLocal, now
from scripts import simulate_economy as sim


def auth(pid):
    return {'Authorization': f'demo:{pid}'}


def create(client, pid, cls):
    response=client.post('/api/class',headers=auth(pid),json={'key':cls})
    assert response.status_code==200,response.text


def test_baseline_class_survivability_is_real_not_only_a_label():
    results={}
    with TestClient(app) as c:
        for index,klass in enumerate(('soldier','medic','assassin','thief'),1):
            pid=99324000+index
            create(c,pid,klass)
            with SessionLocal.begin() as db:
                p=db.get(Player,pid)
                p.stamina=500
                p.hp=50
                b=Battle(player_id=pid,kind='zombie:walker',enemy='Шатун',
                         enemy_hp=500,enemy_max_hp=500,enemy_damage=20,turn=0,log=[])
                db.add(b)
                db.flush()
                before=p.hp
                with patch('game.random.random',return_value=.2),patch('game.random.randint',return_value=0):
                    result=combat_round(db,p,b,'defend')
                assert not result['finished']
                results[klass]=before-p.hp
    assert results['thief']==0,results
    assert results['assassin']<results['soldier'],results
    assert results['medic']<results['soldier'],results
    assert CLASSES['thief']['dodge']==.25
    assert CLASSES['assassin']['mitigation']==.10


def test_uninsured_death_really_removes_half_of_unbound_stackable_supplies():
    with TestClient(app) as c:
        pid=99324011
        create(c,pid,'soldier')
        with SessionLocal.begin() as db:
            p=db.get(Player,pid)
            p.caps=1000;p.xp=200
            before=db.scalars(select(ItemStack).where(
                ItemStack.player_id==pid,ItemStack.equipped.is_(False))).all()
            total=sum(x.quantity for x in before)
            loss=death_penalty(db,p)
            assert loss=={'caps':200,'xp':60,'items':int(total*.5),'insured':False}
        with SessionLocal() as db:
            p=db.get(Player,pid)
            remaining=db.scalars(select(ItemStack).where(
                ItemStack.player_id==pid,ItemStack.equipped.is_(False))).all()
            assert p.caps==800 and p.xp==140
            assert sum(x.quantity for x in remaining)==total-int(total*.5)


def test_premium_insurance_purchase_persists_and_reduces_real_death_losses():
    with TestClient(app) as c:
        pid=99324012
        create(c,pid,'thief')
        with SessionLocal.begin() as db:
            p=db.get(Player,pid)
            p.zombo=250
        buy=c.post('/api/premium/buy',headers=auth(pid),json={'key':'insurance_day'})
        assert buy.status_code==200,buy.text
        offers=c.get('/api/premium').json()
        assert any(o['key']=='insurance_day' and o['price']==200 for o in offers)
        with SessionLocal.begin() as db:
            p=db.get(Player,pid)
            assert p.zombo==50 and insurance_active(p)
            p.caps=1000;p.xp=200
            stacks=db.scalars(select(ItemStack).where(
                ItemStack.player_id==pid,ItemStack.equipped.is_(False))).all()
            total=sum(s.quantity for s in stacks)
            lost=death_penalty(db,p)
            assert lost=={'caps':50,'xp':20,'items':int(total*.1),'insured':True}


def test_passive_energy_and_flee_cost_on_actual_player():
    with TestClient(app) as c:
        pid=99324013
        create(c,pid,'soldier')
        with SessionLocal.begin() as db:
            p=db.get(Player,pid)
            p.stamina=100
            p.last_tick=now()-timedelta(minutes=10)
            tick(p)
            assert p.stamina==100+2*STAMINA_REGEN_PER_TICK
        assert c.post('/api/travel',headers=auth(pid),json={'key':'forest'}).status_code==200
        assert c.post('/api/combat/start',headers=auth(pid)).status_code==200
        with SessionLocal() as db:
            before=db.get(Player,pid).stamina
        response=c.post('/api/combat/turn',headers=auth(pid),
                        json={'action':'flee'})
        assert response.status_code==200,response.text
        with SessionLocal() as db:
            assert db.get(Player,pid).stamina==before-2


def test_medicine_shopping_is_a_real_money_sink_in_economy_model():
    state={'class':'soldier','level':1,'hp':1,'caps':55,'medkits':0,
           'medkits_used':0,'medkits_bought':0,'merchant_spend':0,
           'crafted_medkits':0,'materials':Counter()}
    sim.heal_if_needed(state)
    assert state['caps']==0 and state['merchant_spend']==55
    assert state['medkits_bought']==state['medkits_used']==1
    assert state['hp']>1
    run=sim.simulate('forest','soldier',days=5,actions=15,seed=99)
    assert run['medkits_bought']*55==run['merchant_spend']
    assert (run['gross_combat_caps']+run['daily_caps']+run['quest_caps']
            -run['territory_tax']-run['death_losses']-run['merchant_spend']
            ==run['net_caps'])
