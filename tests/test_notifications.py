"""Notification preferences, durable queue, retries, leases and actual gameplay hooks."""
from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy import select, func

from tests.test_game import app
from models import SessionLocal, Player, now
from notifications import (
    NotificationOutbox, NotificationPreference, queue_notification,
    claim_batch, complete_delivery, aware,
)
from expeditions import ExpeditionRun, ExpeditionIncident


def h(pid):
    return {'Authorization': f'demo:{pid}'}


def choose(client, pid):
    response = client.post('/api/class', headers=h(pid), json={'key': 'soldier'})
    assert response.status_code == 200, response.text


def enable(client, pid, category):
    response = client.post('/api/notifications/settings', headers=h(pid),
                           json={'category': category, 'enabled': True})
    assert response.status_code == 200, response.text
    assert response.json()['settings'][category] is True


def test_opt_in_delivery_retry_and_permanent_rejection():
    pid, other = 986101, 986102
    with TestClient(app) as client:
        choose(client, pid)
        choose(client, other)
        overview = client.get('/api/notifications', headers=h(pid))
        assert overview.status_code == 200
        assert overview.json()['settings'] == {'market': False, 'expeditions': False,
                                               'raids': False, 'clans': False}
        assert client.post('/api/notifications/settings', headers=h(pid),
                           json={'category': 'invalid', 'enabled': True}).status_code == 400
        with SessionLocal.begin() as db:
            assert not queue_notification(db, pid, 'test:no-opt', 'market', 'gear_sale_sold', 'none')
        enable(client, pid, 'market')
        with SessionLocal.begin() as db:
            assert queue_notification(db, pid, 'test:market:001', 'market', 'gear_sale_sold', 'Продано')
            assert not queue_notification(db, other, 'test:other', 'market', 'gear_sale_sold', 'none')
            assert not queue_notification(db, pid, 'test:market:001', 'market', 'gear_sale_sold', 'Повтор')
        jobs = claim_batch()
        assert len(jobs) == 1 and jobs[0]['message'] == 'Продано'
        job = jobs[0]
        assert not complete_delivery(job['id'], 'wrong-lease', {'ok': True})
        assert complete_delivery(job['id'], job['lease'], {'ok': False, 'error_code': 429,
                                                          'parameters': {'retry_after': 70}})
        with SessionLocal.begin() as db:
            row = db.get(NotificationOutbox, job['id'])
            assert row.status == 'pending' and row.attempts == 1
            assert aware(row.scheduled_at) > now() + timedelta(seconds=60)
            row.scheduled_at = now() - timedelta(seconds=5)
        [again] = claim_batch()
        assert again['id'] == job['id'] and again['lease'] != job['lease']
        assert complete_delivery(again['id'], again['lease'], {'ok': True})
        assert not complete_delivery(again['id'], again['lease'], {'ok': True})
        with SessionLocal.begin() as db:
            assert db.get(NotificationOutbox, job['id']).status == 'sent'
            assert queue_notification(db, pid, 'test:market:002', 'market',
                                      'gear_sale_expired', 'Срок вышел')
        [next_job] = claim_batch()
        assert complete_delivery(next_job['id'], next_job['lease'],
                                 {'ok': False, 'error_code': 403})
        with SessionLocal.begin() as db:
            assert db.get(NotificationOutbox, next_job['id']).status == 'failed'
            assert queue_notification(db, pid, 'test:market:003', 'market',
                                      'gear_sale_sold', 'Новое сообщение')
        assert client.post('/api/notifications/settings', headers=h(pid),
                           json={'category': 'market', 'enabled': False}).json()['settings']['market'] is False
        assert claim_batch() == []
        history = client.get('/api/notifications', headers=h(pid)).json()['history']
        assert any(row['status'] == 'skipped' for row in history)
        assert any(row['status'] == 'failed' for row in history)
        assert any(row['status'] == 'sent' for row in history)


def test_scheduled_expedition_notifications_and_stale_decisions():
    crew = (986201, 986202, 986203)
    with TestClient(app) as client:
        for pid in crew:
            choose(client, pid)
            enable(client, pid, 'expeditions')
        with SessionLocal.begin() as db:
            for pid in crew:
                db.get(Player, pid).level = 50
        created = client.post('/api/expeditions/create', headers=h(crew[0]), json={'key': 'hospital'})
        assert created.status_code == 200, created.text
        run_id = created.json()['id']
        for pid in crew[1:]:
            assert client.post('/api/expeditions/join', headers=h(pid),
                               json={'id': run_id}).status_code == 200
        for pid, role in zip(crew, ('guard', 'scout', 'medic')):
            assert client.post('/api/expeditions/prepare', headers=h(pid),
                               json={'id': run_id, 'role': role}).status_code == 200
        started = client.post('/api/expeditions/launch', headers=h(crew[0]), json={'id': run_id})
        assert started.status_code == 200, started.text
        with SessionLocal.begin() as db:
            rows = db.scalars(select(NotificationOutbox).where(
                NotificationOutbox.event_key.like(f'expedition:{run_id}:%'))).all()
            assert len(rows) == 7
            assert sum(x.kind == 'expedition_started' for x in rows) == 3
            assert sum(x.kind == 'expedition_finished' for x in rows) == 3
            assert sum(x.kind == 'expedition_incident' for x in rows) == 1
        launches = claim_batch()
        assert len(launches) == 3
        for job in launches:
            assert complete_delivery(job['id'], job['lease'], {'ok': True})
        with SessionLocal.begin() as db:
            run = db.get(ExpeditionRun, run_id)
            run.started_at = now() - timedelta(hours=5)
            run.finishes_at = now() + timedelta(hours=7)
            incident = db.scalar(select(ExpeditionIncident).where(
                ExpeditionIncident.run_id == run_id))
            incident.roll = 40
            event = db.scalar(select(NotificationOutbox).where(
                NotificationOutbox.kind == 'expedition_incident',
                NotificationOutbox.event_key.like(f'expedition:{run_id}:%')))
            event.scheduled_at = now() - timedelta(minutes=1)
        decision = client.post('/api/expeditions/event', headers=h(crew[0]),
                               json={'id': run_id, 'choice': 'cautious'})
        assert decision.status_code == 200, decision.text
        assert claim_batch() == []  # Already resolved: no stale "choose now" alert.
        with SessionLocal.begin() as db:
            event = db.scalar(select(NotificationOutbox).where(
                NotificationOutbox.kind == 'expedition_incident',
                NotificationOutbox.event_key.like(f'expedition:{run_id}:%')))
            assert event.status == 'skipped'
            for row in db.scalars(select(NotificationOutbox).where(
                    NotificationOutbox.kind == 'expedition_finished',
                    NotificationOutbox.event_key.like(f'expedition:{run_id}:%'))):
                row.scheduled_at = now() - timedelta(seconds=1)
        finished_jobs = claim_batch()
        assert len(finished_jobs) == 3
        for job in finished_jobs:
            complete_delivery(job['id'], job['lease'], {'ok': True})


def test_outbox_remains_unchanged_when_operation_rolls_back():
    pid = 986301
    with TestClient(app) as client:
        choose(client, pid)
        enable(client, pid, 'market')
        try:
            with SessionLocal.begin() as db:
                assert queue_notification(db, pid, 'test:rollback', 'market',
                                          'gear_sale_sold', 'Never send')
                raise ValueError('rollback')
        except ValueError:
            pass
        with SessionLocal.begin() as db:
            assert not db.scalar(select(NotificationOutbox.id).where(
                NotificationOutbox.event_key == 'test:rollback'))


def test_gear_sale_and_expiry_queue_once_with_real_escrow():
    from gear import create_gear
    from gear_market import GearSale, list_gear, buy_gear, expire_sales
    seller_id, buyer_id = 986401, 986402
    with TestClient(app) as client:
        choose(client, seller_id)
        choose(client, buyer_id)
        enable(client, seller_id, 'market')
        with SessionLocal.begin() as db:
            seller = db.get(Player, seller_id)
            buyer = db.get(Player, buyer_id)
            buyer.caps = 2000
            first = create_gear(db, seller_id, 'pistol', 'rare')
            second = create_gear(db, seller_id, 'vest', 'rare')
            sale1 = list_gear(db, seller, first.id, 700)
            sale2 = list_gear(db, seller, second.id, 800)
            one, two = sale1.id, sale2.id
        with SessionLocal.begin() as db:
            buy_gear(db, db.get(Player, buyer_id), one)
            expired = db.scalar(select(GearSale).where(GearSale.id == two))
            expired.expires_at = now() - timedelta(seconds=1)
            db.flush()  # SessionLocal has autoflush disabled.
            assert expire_sales(db) == 1
            assert expire_sales(db) == 0
        with SessionLocal.begin() as db:
            rows = db.scalars(select(NotificationOutbox).where(
                NotificationOutbox.player_id == seller_id)).all()
            assert sorted(row.kind for row in rows) == ['gear_sale_expired', 'gear_sale_sold']
            assert all(row.status == 'pending' for row in rows)
            assert all(row.message for row in rows)
            assert db.get(Player, seller_id).caps >= 150
            assert db.get(Player, buyer_id).caps == 1300
