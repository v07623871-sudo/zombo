"""Integration tests for scheduled world events and their real PvE/scavenge effects."""
from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.test_game import app
import app as server
from models import SessionLocal, Player, ItemStack, now
from world_events import WorldEvent, WorldEventParticipation, event_status, record_action
from admin import AdminAudit


def h(pid):
    return {'Authorization': f'demo:{pid}'}


def create_class(client, pid):
    state = client.get('/api/me', headers=h(pid))
    assert state.status_code == 200, state.text
    if state.json()['class']:
        return
    response = client.post('/api/class', headers=h(pid), json={'key': 'soldier'})
    assert response.status_code == 200, response.text


def new_event(client, aid, kind='supplies', location='city', delay=0, duration=120, uid=None):
    return client.post('/api/admin/world-events/create', headers=h(aid),
        json={'type': kind, 'location': location, 'starts_in_minutes': delay,
              'duration_minutes': duration, 'reason': 'Test global event setup',
              'request_id': uid or str(uuid4())})


def test_admin_event_auth_schedule_dedup_and_stop():
    aid, stranger = 1998701101, 1998701102
    server.ADMIN_IDS.add(aid)
    try:
        with TestClient(app) as client:
            create_class(client, aid)
            create_class(client, stranger)
            assert new_event(client, stranger).status_code == 403
            assert client.get('/api/admin/world-events', headers=h(stranger)).status_code == 403
            assert client.post('/api/admin/world-events/123/stop', headers=h(stranger),
                json={'reason':'Do not let strangers stop events','request_id':str(uuid4())}).status_code == 403
            assert new_event(client, aid, kind='horde', location='base').status_code == 400
            token = str(uuid4())
            created = new_event(client, aid, kind='horde', location='forest',
                                delay=45, duration=150, uid=token)
            assert created.status_code == 200, created.text
            event_id = created.json()['id']
            repeated = new_event(client, aid, kind='horde', location='forest',
                                 delay=45, duration=150, uid=token)
            assert repeated.status_code == 200 and repeated.json()['replayed']
            assert new_event(client, aid, kind='supplies', location='forest',
                             delay=50).status_code == 400
            # Different territory may host its own event.
            next_event = new_event(client, aid, location='hospital')
            assert next_event.status_code == 200, next_event.text
            admin_list = client.get('/api/admin/world-events', headers=h(aid))
            assert admin_list.status_code == 200
            assert any(e['id'] == event_id and e['status'] == 'scheduled'
                       for e in admin_list.json()['events'])
            with SessionLocal.begin() as db:
                e = db.get(WorldEvent, event_id)
                assert event_status(e) == 'scheduled'
            stopped = client.post(f'/api/admin/world-events/{event_id}/stop',
                headers=h(aid), json={'reason':'Test manual cancellation',
                                     'request_id':str(uuid4())})
            assert stopped.status_code == 200, stopped.text
            assert new_event(client, aid, kind='horde', location='forest',
                             delay=300).status_code == 200
            with SessionLocal.begin() as db:
                assert db.scalar(select(AdminAudit).where(
                    AdminAudit.after == f'stopped:{event_id}')) is not None
    finally:
        server.ADMIN_IDS.discard(aid)


def test_military_cargo_scavenge_progress_and_one_time_claim(monkeypatch):
    aid, pid, outsider = 1998701201, 1998701202, 1998701203
    server.ADMIN_IDS.add(aid)
    try:
        with TestClient(app) as client:
            for who in (aid, pid, outsider):
                create_class(client, who)
            with SessionLocal.begin() as db:
                p = db.get(Player, pid)
                p.level = 25
                p.stamina = 400
            created = new_event(client, aid, kind='supplies', location='city')
            assert created.status_code == 200, created.text
            eid = created.json()['id']
            # Disable random encounter/bonus gear so material delta is deterministic.
            monkeypatch.setattr(server.random, 'choice', lambda items: items[0])
            monkeypatch.setattr(server.random, 'randint', lambda lo, hi: lo)
            monkeypatch.setattr(server.random, 'random', lambda: 0.99)
            travel = client.post('/api/travel', headers=h(pid), json={'key':'city'})
            assert travel.status_code == 200, travel.text
            before = client.get('/api/me', headers=h(pid)).json()
            qty_before = sum(x['qty'] for x in before['inventory']
                             if x['key'] == 'cloth' and not x['equipped'])
            action = client.post('/api/scavenge', headers=h(pid))
            assert action.status_code == 200, action.text
            assert action.json()['battle'] is False
            after = client.get('/api/me', headers=h(pid)).json()
            qty_after = sum(x['qty'] for x in after['inventory']
                            if x['key'] == 'cloth' and not x['equipped'])
            assert qty_after == qty_before + 2
            world = client.get('/api/world-events', headers=h(pid))
            assert world.status_code == 200
            event = next(e for e in world.json()['events'] if e['id'] == eid)
            assert event['progress'] == 1 and event['my_actions'] == 1
            assert not event['can_claim']
            assert client.post('/api/world-events/claim', headers=h(pid),
                               json={'id':eid}).status_code == 400
            with SessionLocal.begin() as db:
                user = db.get(Player, pid)
                for i in range(34):
                    record_action(db, user, 'supplies')
            with SessionLocal.begin() as db:
                e = db.get(WorldEvent, eid)
                assert e.total_progress == 35
                e.ends_at = now() - timedelta(seconds=1)
            # End-of-event reward: only real participants, no duplicate claim.
            assert client.post('/api/world-events/claim', headers=h(outsider),
                               json={'id':eid}).status_code == 400
            before_caps = client.get('/api/me', headers=h(pid)).json()['caps']
            claimed = client.post('/api/world-events/claim', headers=h(pid), json={'id':eid})
            assert claimed.status_code == 200, claimed.text
            assert 'Награда события' in claimed.json()['message']
            assert client.get('/api/me', headers=h(pid)).json()['caps'] == before_caps + 70
            assert client.post('/api/world-events/claim', headers=h(pid),
                               json={'id':eid}).status_code == 400
            with SessionLocal.begin() as db:
                part = db.scalar(select(WorldEventParticipation).where(
                    WorldEventParticipation.event_id == eid,
                    WorldEventParticipation.player_id == pid))
                assert part.actions == 35 and part.claimed
    finally:
        server.ADMIN_IDS.discard(aid)


def test_horde_changes_actual_zombie_combat_and_rewards(monkeypatch):
    aid, pid = 1998701301, 1998701302
    server.ADMIN_IDS.add(aid)
    try:
        with TestClient(app) as client:
            create_class(client, aid)
            create_class(client, pid)
            with SessionLocal.begin() as db:
                p = db.get(Player, pid)
                p.level = 50
                p.stats = {**p.stats, 'strength': 50, 'accuracy': 50}
                p.stamina = 350
            start = new_event(client, aid, kind='horde', location='forest')
            assert start.status_code == 200, start.text
            eid = start.json()['id']
            assert client.post('/api/travel', headers=h(pid), json={'key':'forest'}).status_code == 200
            battle = client.post('/api/combat/start', headers=h(pid))
            assert battle.status_code == 200, battle.text
            with SessionLocal.begin() as db:
                e = db.get(WorldEvent, eid)
                assert event_status(e) == 'active'
                b = db.scalar(select(server.Battle).where(server.Battle.player_id == pid))
                assert b.enemy_hp > 0 and b.enemy_max_hp >= 15
            final = None
            for _ in range(30):
                response = client.post('/api/combat/turn', headers=h(pid),
                                       json={'action':'attack','zone':'body'})
                assert response.status_code == 200, response.text
                final = response.json()
                if final.get('finished'):
                    break
            assert final and final.get('won'), final
            with SessionLocal.begin() as db:
                e = db.get(WorldEvent, eid)
                part = db.scalar(select(WorldEventParticipation).where(
                    WorldEventParticipation.event_id == eid,
                    WorldEventParticipation.player_id == pid))
                assert e.total_progress == 1 and part.actions == 1
            # A reload cannot repeat the same finished battle.
            assert client.post('/api/combat/turn', headers=h(pid),
                               json={'action':'attack','zone':'body'}).status_code == 400
            with SessionLocal.begin() as db:
                assert db.get(WorldEvent, eid).total_progress == 1
    finally:
        server.ADMIN_IDS.discard(aid)
