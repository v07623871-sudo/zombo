"""API checks for persisted twelve-hour expeditions and one-time rewards."""
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, func

from tests.test_game import app
from expeditions import ExpeditionRun, ExpeditionMember
from gear import GearItem
from models import Player, SessionLocal, now


def headers(pid):
    return {'Authorization': f'demo:{pid}'}


def select_class(client, pid):
    assert client.post('/api/class', headers=headers(pid), json={'key': 'soldier'}).status_code == 200


def test_expedition_lifecycle_and_idempotent_rewards():
    ids = [93001, 93002, 93003, 93004]
    with TestClient(app) as client:
        for pid in ids:
            select_class(client, pid)
        with SessionLocal.begin() as db:
            for pid in ids:
                db.get(Player, pid).level = 30
        assert client.get('/api/expeditions').status_code == 401
        assert client.post('/api/expeditions/create', headers=headers(ids[0]), json={'key': 'invalid'}).status_code == 400
        created = client.post('/api/expeditions/create', headers=headers(ids[0]), json={'key': 'relay'})
        assert created.status_code == 200, created.text
        run_id = created.json()['id']
        assert client.post('/api/expeditions/create', headers=headers(ids[0]), json={'key': 'relay'}).status_code == 400
        for pid in ids[1:3]:
            assert client.post('/api/expeditions/join', headers=headers(pid), json={'id': run_id}).status_code == 200
        assert client.post('/api/expeditions/launch', headers=headers(ids[1]), json={'id': run_id}).status_code == 400
        assert client.post('/api/expeditions/launch', headers=headers(ids[0]), json={'id': run_id}).status_code == 400
        for pid in ids[:3]:
            assert client.post('/api/expeditions/prepare', headers=headers(pid), json={'id': run_id, 'role': 'guard'}).status_code == 200
        assert client.post('/api/expeditions/launch', headers=headers(ids[0]), json={'id': run_id}).status_code == 400
        assert client.post('/api/expeditions/prepare', headers=headers(ids[1]), json={'id': run_id, 'role': 'scout'}).status_code == 200
        assert client.post('/api/expeditions/launch', headers=headers(ids[0]), json={'id': run_id}).status_code == 200
        active = client.get('/api/expeditions', headers=headers(ids[0])).json()['my_run']
        assert active['status'] == 'active' and active['member_count'] == 3
        assert active['success_chance'] > 0 and active['finishes_at']
        assert client.post('/api/expeditions/claim', headers=headers(ids[0]), json={'id': run_id}).status_code == 400
        assert client.post('/api/expeditions/join', headers=headers(ids[3]), json={'id': run_id}).status_code == 400
        with SessionLocal.begin() as db:
            run = db.get(ExpeditionRun, run_id)
            run.finishes_at = now() - timedelta(seconds=1)
            run.will_succeed = True
        result = client.get('/api/expeditions', headers=headers(ids[0])).json()
        assert result['my_run'] is None and result['recent'][0]['status'] == 'cleared'
        with SessionLocal() as db:
            assert db.get(ExpeditionRun, run_id).status == 'cleared'
        assert client.post('/api/expeditions/claim', headers=headers(ids[3]), json={'id': run_id}).status_code == 400
        before = client.get('/api/me', headers=headers(ids[0])).json()['caps']
        prize = client.post('/api/expeditions/claim', headers=headers(ids[0]), json={'id': run_id})
        assert prize.status_code == 200, prize.text
        assert client.post('/api/expeditions/claim', headers=headers(ids[0]), json={'id': run_id}).status_code == 400
        assert client.get('/api/me', headers=headers(ids[0])).json()['caps'] == before + 180
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(GearItem).where(
                GearItem.player_id == ids[0], GearItem.source == 'expedition')) == 1
            assert db.scalar(select(ExpeditionMember).where(ExpeditionMember.run_id == run_id,
                ExpeditionMember.player_id == ids[0])).rewarded


def test_expired_lobby_and_leader_handoff():
    ids = [93101, 93102, 93103]
    with TestClient(app) as client:
        for pid in ids:
            select_class(client, pid)
        with SessionLocal.begin() as db:
            for pid in ids:
                db.get(Player, pid).level = 25
        run_id = client.post('/api/expeditions/create', headers=headers(ids[0]), json={'key': 'convoy'}).json()['id']
        assert client.post('/api/expeditions/join', headers=headers(ids[1]), json={'id': run_id}).status_code == 200
        assert client.post('/api/expeditions/leave', headers=headers(ids[0]), json={'id': run_id}).status_code == 200
        assert client.get('/api/expeditions', headers=headers(ids[1])).json()['my_run']['leader_id'] == ids[1]
        with SessionLocal.begin() as db:
            db.get(ExpeditionRun, run_id).lobby_expires_at = now() - timedelta(seconds=1)
        assert client.get('/api/expeditions', headers=headers(ids[1])).json()['my_run'] is None
        with SessionLocal() as db:
            assert db.get(ExpeditionRun, run_id).status == 'expired'
        assert client.post('/api/expeditions/join', headers=headers(ids[2]), json={'id': run_id}).status_code == 400
        assert client.post('/api/expeditions/claim', headers=headers(ids[1]), json={'id': run_id}).status_code == 400


def test_failed_expedition_consolation_once():
    ids = [93201, 93202, 93203]
    with TestClient(app) as client:
        for pid in ids:
            select_class(client, pid)
        with SessionLocal.begin() as db:
            for pid in ids:
                db.get(Player, pid).level = 10
        run_id = client.post('/api/expeditions/create', headers=headers(ids[0]), json={'key': 'relay'}).json()['id']
        for pid in ids[1:]:
            assert client.post('/api/expeditions/join', headers=headers(pid), json={'id': run_id}).status_code == 200
        for pid, role in zip(ids, ['guard', 'scout', 'medic']):
            assert client.post('/api/expeditions/prepare', headers=headers(pid), json={'id': run_id, 'role': role}).status_code == 200
        assert client.post('/api/expeditions/launch', headers=headers(ids[0]), json={'id': run_id}).status_code == 200
        with SessionLocal.begin() as db:
            run = db.get(ExpeditionRun, run_id)
            run.finishes_at = now() - timedelta(seconds=1)
            run.will_succeed = False
        before = client.get('/api/me', headers=headers(ids[0])).json()['caps']
        result = client.post('/api/expeditions/claim', headers=headers(ids[0]), json={'id': run_id})
        assert result.status_code == 200 and result.json()['status'] == 'failed'
        assert client.get('/api/me', headers=headers(ids[0])).json()['caps'] == before + 45
        assert client.post('/api/expeditions/claim', headers=headers(ids[0]), json={'id': run_id}).status_code == 400


def test_full_gear_inventory_keeps_reward_unclaimed():
    ids = [93301, 93302, 93303]
    with TestClient(app) as client:
        for pid in ids:
            select_class(client, pid)
        with SessionLocal.begin() as db:
            for pid in ids:
                db.get(Player, pid).level = 10
        run_id = client.post('/api/expeditions/create', headers=headers(ids[0]), json={'key': 'relay'}).json()['id']
        for pid in ids[1:]:
            assert client.post('/api/expeditions/join', headers=headers(pid), json={'id': run_id}).status_code == 200
        for pid, role in zip(ids, ['guard', 'scout', 'medic']):
            assert client.post('/api/expeditions/prepare', headers=headers(pid), json={'id': run_id, 'role': role}).status_code == 200
        assert client.post('/api/expeditions/launch', headers=headers(ids[0]), json={'id': run_id}).status_code == 200
        with SessionLocal.begin() as db:
            run = db.get(ExpeditionRun, run_id)
            run.finishes_at = now() - timedelta(seconds=1)
            run.will_succeed = True
            db.add_all(GearItem(player_id=ids[0], base_key='knife', rarity='common', source='test') for _ in range(80))
        before = client.get('/api/me', headers=headers(ids[0])).json()['caps']
        assert client.post('/api/expeditions/claim', headers=headers(ids[0]), json={'id': run_id}).status_code == 400
        assert client.get('/api/me', headers=headers(ids[0])).json()['caps'] == before
        with SessionLocal.begin() as db:
            member = db.scalar(select(ExpeditionMember).where(ExpeditionMember.run_id == run_id,
                ExpeditionMember.player_id == ids[0]))
            assert not member.rewarded
            spare = db.scalar(select(GearItem).where(GearItem.player_id == ids[0]))
            db.delete(spare)
        assert client.post('/api/expeditions/claim', headers=headers(ids[0]), json={'id': run_id}).status_code == 200
