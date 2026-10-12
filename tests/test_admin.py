from uuid import uuid4
import os
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(tempfile.gettempdir()) / ('zombo_admin_' + uuid4().hex + '.db'))
os.environ['DEMO_MODE'] = '1'
import app as server
from datetime import timedelta
from models import SessionLocal, ResourceLedger, now
from sqlalchemy import select
from notifications import NotificationOutbox


def headers(pid):
    return {'Authorization': f'demo:{pid}'}


def test_admin_permissions_audit_and_idempotency():
    admin_id, target_id = 981001, 981002
    server.ADMIN_IDS.add(admin_id)
    try:
        with TestClient(server.app) as client:
            client.get('/api/me', headers=headers(admin_id))
            client.get('/api/me', headers=headers(target_id))
            assert client.get('/api/admin/summary', headers=headers(target_id)).status_code == 403
            assert client.post(f'/api/admin/players/{target_id}/resources', headers=headers(target_id),
                               json={'field':'caps','amount':100,'reason':'test change','request_id':str(uuid4())}).status_code == 403
            assert client.get('/api/admin/summary', headers=headers(admin_id)).status_code == 200
            assert client.get('/api/admin/players', headers=headers(admin_id), params={'q':str(target_id)}).json()['items'][0]['id'] == target_id
            assert client.get('/api/admin/players', headers=headers(admin_id),
                              params={'q':'9'*70}).status_code == 200
            assert client.get('/api/admin/players/'+('9'*70), headers=headers(admin_id)).status_code == 422
            before = client.get(f'/api/admin/players/{target_id}', headers=headers(admin_id)).json()
            uid = str(uuid4())
            payload = {'field':'caps','amount':100,'reason':'test adjustment','request_id':uid}
            first = client.post(f'/api/admin/players/{target_id}/resources', headers=headers(admin_id), json=payload)
            assert first.status_code == 200, first.text
            second = client.post(f'/api/admin/players/{target_id}/resources', headers=headers(admin_id), json=payload)
            assert second.status_code == 200 and second.json()['replayed']
            after = client.get(f'/api/admin/players/{target_id}', headers=headers(admin_id)).json()
            assert after['caps'] == before['caps'] + 100
            assert after['zombo'] == before['zombo']
            with SessionLocal() as db:
                logged=db.scalars(select(ResourceLedger).where(
                    ResourceLedger.source_event==f'admin-resource:{uid}')).all()
                assert [(row.player_id,row.resource_key,row.delta) for row in logged]==[
                    (target_id,'caps',100)]
            material = client.post(f'/api/admin/players/{target_id}/resources', headers=headers(admin_id),
                                   json={'field':'material','item_key':'metal','amount':3,
                                         'reason':'test materials','request_id':str(uuid4())})
            assert material.status_code == 200, material.text
            assert any(i['key']=='metal' and i['quantity']==3 for i in client.get(
                f'/api/admin/players/{target_id}', headers=headers(admin_id)).json()['inventory'])
            assert client.post(f'/api/admin/players/{target_id}/resources', headers=headers(admin_id),
                               json={'field':'xp','amount':-1,'reason':'invalid deduction','request_id':str(uuid4())}).status_code == 400
            assert client.post(f'/api/admin/players/{target_id}/resources', headers=headers(admin_id),
                               json={'field':'zombo','amount':100,'reason':'not allowed','request_id':str(uuid4())}).status_code == 422
            assert client.post(f'/api/admin/players/{target_id}/status', headers=headers(admin_id),
                               json={'field':'banned','value':True,'reason':'test moderation','request_id':str(uuid4())}).status_code == 200
            assert client.get('/api/me', headers=headers(target_id)).status_code == 403
            assert client.post(f'/api/admin/players/{target_id}/status', headers=headers(admin_id),
                               json={'field':'banned','value':False,'reason':'test reversal','request_id':str(uuid4())}).status_code == 200
            assert client.get('/api/me', headers=headers(target_id)).status_code == 200
            assert client.post(f'/api/admin/players/{admin_id}/status', headers=headers(admin_id),
                               json={'field':'banned','value':True,'reason':'self block','request_id':str(uuid4())}).status_code == 409
            logs = client.get('/api/admin/audit', headers=headers(admin_id)).json()['items']
            assert any(x['field'] == 'caps' and x['target_id'] == target_id for x in logs)
    finally:
        server.ADMIN_IDS.discard(admin_id)


def test_admin_operation_diagnostics_hide_private_message_text():
    admin_id, target_id = 981101, 981102
    server.ADMIN_IDS.add(admin_id)
    try:
        with TestClient(server.app) as client:
            client.get('/api/me', headers=headers(admin_id))
            client.get('/api/me', headers=headers(target_id))
            with SessionLocal.begin() as db:
                db.add(NotificationOutbox(player_id=target_id,
                    event_key='admin:diagnostics:pending',category='raids',
                    kind='raid_started',message='Секретный текст уведомления',
                    status='pending',scheduled_at=now()-timedelta(minutes=8)))
                db.add(NotificationOutbox(player_id=target_id,
                    event_key='admin:diagnostics:stuck',category='clans',
                    kind='war_start',message='Другое личное сообщение',
                    status='sending',scheduled_at=now()-timedelta(minutes=10),
                    lease_until=now()-timedelta(minutes=2),attempts=3,
                    last_error='telegram_retry'))
            assert client.get('/api/admin/operations', headers=headers(target_id)).status_code == 403
            assert client.get('/api/admin/notifications', headers=headers(target_id)).status_code == 403
            counters=client.get('/api/admin/operations', headers=headers(admin_id))
            assert counters.status_code == 200, counters.text
            assert counters.json()['notifications_due'] >= 1
            assert counters.json()['notifications_stuck'] >= 1
            assert counters.json()['oldest_due_at']
            rows=client.get('/api/admin/notifications', headers=headers(admin_id),
                params={'status':'sending','category':'clans','player_id':target_id}).json()['items']
            assert len(rows)==1 and rows[0]['attempts']==3
            assert 'message' not in rows[0]
            assert client.get('/api/admin/notifications', headers=headers(admin_id),
                params={'status':'wrong'}).status_code == 422
            assert client.get('/api/admin/notifications', headers=headers(admin_id),
                params={'player_id':-2}).status_code == 422
    finally:
        server.ADMIN_IDS.discard(admin_id)
