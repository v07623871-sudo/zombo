"""Timed cooperative expedition incidents are durable and award exactly once."""
from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.test_game import app
from models import SessionLocal, Player, now
from expeditions import ExpeditionRun, ExpeditionIncident, SCENARIOS


def h(pid):
    return {'Authorization': f'demo:{pid}'}


def prepare_run(client, ids, scenario):
    for pid in ids:
        response = client.post('/api/class', headers=h(pid), json={'key': 'soldier'})
        assert response.status_code == 200, response.text
    with SessionLocal.begin() as db:
        for pid in ids:
            db.get(Player, pid).level = 50
    response = client.post('/api/expeditions/create', headers=h(ids[0]), json={'key': scenario})
    assert response.status_code == 200, response.text
    run_id = response.json()['id']
    for pid in ids[1:]:
        assert client.post('/api/expeditions/join', headers=h(pid), json={'id': run_id}).status_code == 200
    for pid, role in zip(ids, ('guard', 'scout', 'medic')):
        assert client.post('/api/expeditions/prepare', headers=h(pid),
                           json={'id': run_id, 'role': role}).status_code == 200
    response = client.post('/api/expeditions/launch', headers=h(ids[0]), json={'id': run_id})
    assert response.status_code == 200, response.text
    return run_id


def make_incident_available(run_id, roll):
    with SessionLocal.begin() as db:
        run = db.get(ExpeditionRun, run_id)
        run.started_at = now() - timedelta(hours=5)
        run.finishes_at = now() + timedelta(hours=7)
        event = db.scalar(select(ExpeditionIncident).where(ExpeditionIncident.run_id == run_id))
        assert event is not None
        event.roll = roll
        run.will_succeed = roll < run.success_chance


def test_event_leader_only_after_four_hours_and_rewards():
    ids = (93401, 93402, 93403)
    with TestClient(app) as client:
        run_id = prepare_run(client, ids, 'relay')
        state = client.get('/api/expeditions', headers=h(ids[0])).json()['my_run']
        assert state['event']['ready'] is False
        assert state['event']['choice'] is None
        assert 'roll' not in state['event']
        payload = {'id': run_id, 'choice': 'cautious'}
        assert client.post('/api/expeditions/event', headers=h(ids[0]), json=payload).status_code == 400
        make_incident_available(run_id, 1)
        assert client.post('/api/expeditions/event', headers=h(ids[1]), json=payload).status_code == 400
        assert client.post('/api/expeditions/event', headers=h(ids[0]),
                           json={'id': run_id, 'choice': 'hack'}).status_code == 400
        before = client.get('/api/expeditions', headers=h(ids[0])).json()['my_run']['success_chance']
        decided = client.post('/api/expeditions/event', headers=h(ids[0]), json=payload)
        assert decided.status_code == 200, decided.text
        assert decided.json()['success_chance'] == min(95, before + 12)
        assert decided.json()['reward_percent'] == 85
        assert client.post('/api/expeditions/event', headers=h(ids[0]), json=payload).status_code == 400
        with SessionLocal.begin() as db:
            event = db.scalar(select(ExpeditionIncident).where(ExpeditionIncident.run_id == run_id))
            assert event.choice == 'cautious' and event.reward_percent == 85
            db.get(ExpeditionRun, run_id).finishes_at = now() - timedelta(seconds=1)
        caps_before = client.get('/api/me', headers=h(ids[0])).json()['caps']
        claim = client.post('/api/expeditions/claim', headers=h(ids[0]), json={'id': run_id})
        assert claim.status_code == 200, claim.text
        assert claim.json()['status'] == 'cleared'
        assert client.get('/api/me', headers=h(ids[0])).json()['caps'] - caps_before == 153
        assert client.post('/api/expeditions/claim', headers=h(ids[0]), json={'id': run_id}).status_code == 400


def test_risky_event_failure_and_new_route():
    ids = (93501, 93502, 93503)
    with TestClient(app) as client:
        run_id = prepare_run(client, ids, 'bunker')
        make_incident_available(run_id, 99)
        prior = client.get('/api/expeditions', headers=h(ids[0])).json()['my_run']['success_chance']
        resp = client.post('/api/expeditions/event', headers=h(ids[0]),
                           json={'id': run_id, 'choice': 'risky'})
        assert resp.status_code == 200, resp.text
        assert resp.json()['success_chance'] == max(15, prior - 8)
        with SessionLocal.begin() as db:
            db.get(ExpeditionRun, run_id).finishes_at = now() - timedelta(seconds=1)
        caps_before = client.get('/api/me', headers=h(ids[1])).json()['caps']
        claim = client.post('/api/expeditions/claim', headers=h(ids[1]), json={'id': run_id})
        assert claim.status_code == 200 and claim.json()['status'] == 'failed'
        assert client.get('/api/me', headers=h(ids[1])).json()['caps'] - caps_before == (760 * 135 // 100) // 4
        assert client.post('/api/expeditions/event', headers=h(ids[0]),
                           json={'id': run_id, 'choice': 'risky'}).status_code == 400
        assert 'hospital' in SCENARIOS and 'bunker' in SCENARIOS
