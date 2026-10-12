"""Persistent encounter choices: no rerolls, no repeated rewards and real costs."""
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.test_game import app
from models import Player, SessionLocal, now
from encounters import EncounterState, EncounterClue, start, ENCOUNTERS
import encounters


def headers(pid):
    return {'Authorization': f'demo:{pid}'}


def prepare(client, pid, *, zone='forest'):
    response = client.post('/api/class', headers=headers(pid), json={'key':'soldier'})
    assert response.status_code == 200, response.text
    if zone != 'forest':
        with SessionLocal.begin() as db:
            db.get(Player,pid).level=45
    response = client.post('/api/travel', headers=headers(pid), json={'key':zone})
    assert response.status_code == 200, response.text


def test_exploration_resume_blocked_actions_and_replay(monkeypatch):
    pid = 1987000101
    with TestClient(app) as client:
        assert client.post('/api/encounters/explore', headers=headers(pid)).status_code == 400
        prepare(client, pid)
        monkeypatch.setattr(encounters.secrets, 'choice', lambda choices: choices[0])
        monkeypatch.setattr(encounters.secrets, 'randbelow', lambda max_value: 7)
        before = client.get('/api/me',headers=headers(pid)).json()
        started = client.post('/api/encounters/explore',headers=headers(pid))
        assert started.status_code == 200, started.text
        assert started.json()['encounter']['title'] == ENCOUNTERS['survivor']['title']
        assert 'roll' not in started.json()['encounter']
        info = client.get('/api/encounters', headers=headers(pid)).json()
        assert info['pending']
        assert set(info['encounter']['choices']) == {'help','leave'}
        assert client.get('/api/me',headers=headers(pid)).json()['encounter_pending']
        assert client.post('/api/encounters/explore',headers=headers(pid)).status_code == 400
        assert client.post('/api/travel',headers=headers(pid),json={'key':'base'}).status_code == 400
        assert client.post('/api/scavenge',headers=headers(pid)).status_code == 400
        assert client.post('/api/combat/start',headers=headers(pid)).status_code == 400
        assert client.post('/api/encounters/resolve',headers=headers(pid),
                           json={'action':'not-a-choice'}).status_code == 400
        got = client.post('/api/encounters/resolve',headers=headers(pid),json={'action':'help'})
        assert got.status_code == 200, got.text
        assert '+2 металла' in got.json()['message']
        final = client.get('/api/me',headers=headers(pid)).json()
        assert final['encounter_pending'] is False
        assert final['karma'] == before['karma'] + 4
        assert final['stamina'] == before['stamina'] - 6
        def inventory(state,key):
            return sum(i['qty'] for i in state['inventory'] if i['key']==key)
        assert inventory(final,'food') == inventory(before,'food')-1
        assert inventory(final,'metal') == inventory(before,'metal')+2
        assert client.post('/api/encounters/resolve',headers=headers(pid),
                           json={'action':'help'}).status_code == 400
        after_replay = client.get('/api/me',headers=headers(pid)).json()
        assert after_replay['karma']==final['karma']
        assert client.post('/api/encounters/explore',headers=headers(pid)).status_code == 400
        with SessionLocal.begin() as db:
            state = db.get(EncounterState, pid)
            assert state.status == 'resolved' and state.roll == 7
            state.resolved_at = now() - timedelta(minutes=2)
        again = client.post('/api/encounters/explore',headers=headers(pid))
        assert again.status_code == 200,again.text
        # Same story cannot appear immediately after last encounter.
        assert again.json()['encounter']['title'] != ENCOUNTERS['survivor']['title']
        assert client.get('/api/encounters',headers=headers(pid)).json()['pending']


def test_choice_requires_resources_and_remains_pending():
    pid=1987000102
    with TestClient(app) as client:
        prepare(client,pid)
        with SessionLocal.begin() as db:
            p=db.scalar(select(Player).where(Player.id==pid).with_for_update())
            p.caps=12
            start(db,p,key='trader',roll=1)
        denied=client.post('/api/encounters/resolve',headers=headers(pid),json={'action':'buy'})
        assert denied.status_code==400
        assert client.get('/api/encounters',headers=headers(pid)).json()['pending']
        skipped=client.post('/api/encounters/resolve',headers=headers(pid),json={'action':'leave'})
        assert skipped.status_code==200
        assert client.get('/api/me',headers=headers(pid)).json()['caps']==12


def test_risk_outcomes_are_stable_and_award_once():
    # Two predetermined server-side rolls for each risky route.
    scenarios=[
        ('ambulance','search',1,'medkit',2),
        ('checkpoint','loot',1,'wire',2),
        ('radio','answer',1,None,0),
        ('door','rescue',1,'medkit',1),
        ('ambulance','search',95,None,0),
        ('checkpoint','loot',95,None,0),
        ('radio','answer',95,None,0),
        ('door','rescue',95,None,0),
        ('trader','buy',1,'medkit',1),
    ]
    with TestClient(app) as client:
        for index,(kind,choice,roll,item,qty) in enumerate(scenarios):
            pid=1987000200+index
            prepare(client,pid,zone='city' if kind in ('checkpoint', 'radio', 'door') else 'forest')
            with SessionLocal.begin() as db:
                p=db.scalar(select(Player).where(Player.id==pid).with_for_update())
                p.caps=200
                p.stamina=125
                start(db,p,key=kind,roll=roll)
            pre=client.get('/api/me',headers=headers(pid)).json()
            before_qty=sum(x['qty'] for x in pre['inventory'] if x['key']==item) if item else 0
            response=client.post('/api/encounters/resolve',headers=headers(pid),json={'action':choice})
            assert response.status_code==200,(kind,roll,response.text)
            after=client.get('/api/me',headers=headers(pid)).json()
            after_qty=sum(x['qty'] for x in after['inventory'] if x['key']==item) if item else 0
            assert after_qty-before_qty==qty,(kind,roll,after_qty,before_qty)
            if kind in ('ambulance','checkpoint','door') and roll==95:
                assert after['hp']<pre['hp']
            if kind=='trader':
                assert after['caps']==pre['caps']-25
            if kind=='radio' and roll==1:
                assert after['caps']==pre['caps']+50
            if kind=='radio' and roll==95:
                assert after['stamina']==pre['stamina']-8
            assert client.post('/api/encounters/resolve',headers=headers(pid),
                               json={'action':choice}).status_code==400
            assert client.get('/api/me',headers=headers(pid)).json()['caps']==after['caps']


def test_location_pool_and_survivor_radio_consequence(monkeypatch):
    pid = 1987000301
    with TestClient(app) as client:
        prepare(client, pid)
        pools = []
        monkeypatch.setattr(encounters.secrets, 'choice', lambda choices: pools.append(list(choices)) or choices[0])
        monkeypatch.setattr(encounters.secrets, 'randbelow', lambda _: 74)
        first = client.post('/api/encounters/explore', headers=headers(pid))
        assert first.status_code == 200, first.text
        assert set(pools[0]) == {'survivor', 'ambulance', 'trader'}
        assert first.json()['encounter']['danger'] == 1
        assert client.post('/api/encounters/resolve', headers=headers(pid), json={'action': 'help'}).status_code == 200
        with SessionLocal.begin() as db:
            assert db.get(EncounterClue, (pid, 'survivor_frequency')) is not None
            db.get(EncounterState, pid).resolved_at = now() - timedelta(minutes=2)
            db.get(Player, pid).level = 45
        assert client.post('/api/travel', headers=headers(pid), json={'key': 'city'}).status_code == 200
        with SessionLocal.begin() as db:
            player = db.scalar(select(Player).where(Player.id == pid).with_for_update())
            state = start(db, player, key='radio', roll=74)
            assert encounters.view(state, encounters.clue_codes(db, pid))['choices']['trace']['locked'] is False
        before = client.get('/api/me', headers=headers(pid)).json()
        result = client.post('/api/encounters/resolve', headers=headers(pid), json={'action': 'trace'})
        assert result.status_code == 200, result.text
        after = client.get('/api/me', headers=headers(pid)).json()
        assert after['caps'] == before['caps'] + 55
        assert client.post('/api/encounters/resolve', headers=headers(pid), json={'action': 'trace'}).status_code == 400
        with SessionLocal.begin() as db:
            assert db.get(EncounterClue, (pid, 'survivor_frequency')) is None


def test_unavailable_encounter_cannot_consume_stamina():
    pid = 1987000303
    with TestClient(app) as client:
        prepare(client, pid)
        before = client.get('/api/me', headers=headers(pid)).json()['stamina']
        with pytest.raises(ValueError, match='недоступна'):
            with SessionLocal.begin() as db:
                player = db.scalar(select(Player).where(Player.id == pid).with_for_update())
                start(db, player, key='radio', roll=0)
        assert client.get('/api/me', headers=headers(pid)).json()['stamina'] == before


def test_pending_legacy_encounter_can_finish_after_location_rules_change():
    pid = 1987000304
    with TestClient(app) as client:
        prepare(client, pid)
        with SessionLocal.begin() as db:
            db.add(EncounterState(player_id=pid, key='radio', location='forest',
                                  roll=1, status='pending', created_at=now()))
        before = client.get('/api/me', headers=headers(pid)).json()['caps']
        assert client.get('/api/encounters', headers=headers(pid)).json()['encounter']['status'] == 'pending'
        response = client.post('/api/encounters/resolve', headers=headers(pid), json={'action': 'answer'})
        assert response.status_code == 200, response.text
        assert client.get('/api/me', headers=headers(pid)).json()['caps'] == before + 50


def test_checkpoint_trader_clue_is_required_and_spent_once():
    pid = 1987000302
    with TestClient(app) as client:
        prepare(client, pid, zone='city')
        with SessionLocal.begin() as db:
            player = db.scalar(select(Player).where(Player.id == pid).with_for_update())
            start(db, player, key='checkpoint', roll=5)
        assert client.post('/api/encounters/resolve', headers=headers(pid), json={'action': 'observe'}).status_code == 200
        assert 'Маршрут торговца' in client.get('/api/encounters', headers=headers(pid)).json()['clues']
        with SessionLocal.begin() as db:
            db.get(EncounterState, pid).resolved_at = now() - timedelta(minutes=2)
            player = db.scalar(select(Player).where(Player.id == pid).with_for_update())
            start(db, player, key='trader', roll=0)
        before = client.get('/api/me', headers=headers(pid)).json()
        assert not client.get('/api/encounters', headers=headers(pid)).json()['encounter']['choices']['trade_map']['locked']
        traded = client.post('/api/encounters/resolve', headers=headers(pid), json={'action': 'trade_map'})
        assert traded.status_code == 200, traded.text
        after = client.get('/api/me', headers=headers(pid)).json()
        assert after['caps'] == before['caps']
        assert client.get('/api/encounters', headers=headers(pid)).json()['clues'] == []
        with SessionLocal.begin() as db:
            db.get(EncounterState, pid).resolved_at = now() - timedelta(minutes=2)
            player = db.scalar(select(Player).where(Player.id == pid).with_for_update())
            start(db, player, key='trader', roll=0)
        assert client.get('/api/encounters', headers=headers(pid)).json()['encounter']['choices']['trade_map']['locked']
        denied = client.post('/api/encounters/resolve', headers=headers(pid), json={'action': 'trade_map'})
        assert denied.status_code == 400
        assert client.get('/api/encounters', headers=headers(pid)).json()['pending']


def test_new_direct_choices_have_actual_costs_and_single_rewards():
    with TestClient(app) as client:
        for index, (kind, action, roll) in enumerate((
                ('ambulance', 'force', 5), ('ambulance', 'force', 95),
                ('door', 'listen', 95))):
            pid = 1987000401 + index
            prepare(client, pid, zone='city')
            with SessionLocal.begin() as db:
                player = db.scalar(select(Player).where(Player.id == pid).with_for_update())
                player.stamina = 125
                start(db, player, key=kind, roll=roll)
            before = client.get('/api/me', headers=headers(pid)).json()
            result = client.post('/api/encounters/resolve', headers=headers(pid), json={'action': action})
            assert result.status_code == 200, result.text
            after = client.get('/api/me', headers=headers(pid)).json()
            assert after['stamina'] == before['stamina'] - (6 if action == 'force' else 0)
            if action == 'force' and roll == 5:
                qty = lambda state: sum(item['qty'] for item in state['inventory'] if item['key'] == 'medkit')
                assert qty(after) == qty(before) + 1
            if action == 'force' and roll == 95:
                assert after['hp'] == before['hp'] - 10
            if action == 'listen':
                assert after['xp'] == before['xp'] + 10
            assert client.post('/api/encounters/resolve', headers=headers(pid), json={'action': action}).status_code == 400
