"""Real HTTP checks for restricted admin exports and read-only economy risk signals."""
from uuid import uuid4
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from tests.test_game import app
from models import Player, PaymentReview, SessionLocal, now
from gear_market import GearSale
from admin import AdminAudit


def headers(pid):
    return {'Authorization': f'demo:{pid}'}


def test_admin_risk_permissions_and_export_with_spreadsheet_safety():
    import app as server
    admin_id, seller_id, buyer_id = 982101, 982102, 982103
    server.ADMIN_IDS.add(admin_id)
    try:
        with TestClient(app) as client:
            for pid in (admin_id, seller_id, buyer_id):
                assert client.get('/api/me', headers=headers(pid)).status_code == 200
            with SessionLocal.begin() as db:
                for number in range(4):
                    db.add(GearSale(gear_id=40 + number, item_snapshot={'name':'Клинок'},
                                    seller_id=seller_id, buyer_id=buyer_id, price=180000,
                                    status='sold', expires_at=now(), closed_at=now()))
                db.add(PaymentReview(charge_id='risk_review_'+uuid4().hex, player_id=buyer_id,
                                     payload='test', currency='XTR', amount=400, reason='invoice_not_verified'))
                db.add(AdminAudit(request_id=str(uuid4()), actor_id=admin_id, target_id=seller_id,
                                  action='resource', field='caps', before='0', after='60000',
                                  reason='=SUM(1,2)'))
            assert client.get('/api/admin/risk', headers=headers(seller_id)).status_code == 403
            assert client.get('/api/admin/audit/export', headers=headers(seller_id)).status_code == 403
            report = client.get('/api/admin/risk', headers=headers(admin_id))
            assert report.status_code == 200, report.text
            body = report.json()
            kinds = {finding['type'] for finding in body['findings']}
            assert {'large_sale', 'repeated_trades', 'payment_review', 'large_admin_adjustment'} <= kinds
            assert body['transactions_examined'] >= 4
            assert body['disclaimer'] and body['total_findings'] >= 4
            exported = client.get('/api/admin/audit/export?limit=100', headers=headers(admin_id))
            assert exported.status_code == 200, exported.text
            assert exported.content.startswith(bytes([239, 187, 191]))
            assert 'text/csv' in exported.headers['content-type']
            assert 'no-store' in exported.headers['cache-control']
            assert "'=SUM(1,2)" in exported.text
            assert 'actor_id' in exported.text
    finally:
        server.ADMIN_IDS.discard(admin_id)


def test_bot_id_and_admin_commands_only_disclose_id_in_private_chat(monkeypatch):
    import app as module
    sender=AsyncMock(return_value={'ok':True})
    monkeypatch.setattr(module,'telegram_api',sender)
    monkeypatch.setattr(module,'SECRET','test-admin-onboard')
    pid=982111
    def cmd(client,word,chat_type='private'):
        sender.reset_mock()
        response=client.post('/telegram/webhook',
            json={'message':{'chat':{'id':pid,'type':chat_type},
                             'from':{'id':pid},'text':word}},
            headers={'X-Telegram-Bot-Api-Secret-Token':'test-admin-onboard'})
        assert response.status_code==200, response.text
        return sender.call_args.args[1]['text']
    with TestClient(app) as client:
        assert str(pid) in cmd(client,'/id')
        assert str(pid) not in cmd(client,'/id','group')
        assert 'ADMIN_IDS' in cmd(client,'/admin')
        module.ADMIN_IDS.add(pid)
        try:
            assert 'Доступ подтверждён' in cmd(client,'/admin')
        finally:
            module.ADMIN_IDS.discard(pid)
