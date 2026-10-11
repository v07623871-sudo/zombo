from uuid import uuid4
import os
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(tempfile.gettempdir()) / ('zombo_admin_' + uuid4().hex + '.db'))
os.environ['DEMO_MODE'] = '1'
import app as server


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
