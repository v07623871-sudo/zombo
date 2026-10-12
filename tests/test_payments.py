from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.test_game import app
from models import Payment, Player, SessionLocal, StarInvoice, PaymentReview, ResourceLedger
import app as server


def test_stars_webhook_is_authenticated_and_idempotent(monkeypatch):
    sender = AsyncMock(return_value={'ok':True})
    monkeypatch.setattr(server, 'SECRET', 'test-payment-secret')
    monkeypatch.setattr(server, 'telegram_api', sender)
    pid = 986100
    h = {'Authorization':f'demo:{pid}'}
    webhook_h = {'X-Telegram-Bot-Api-Secret-Token':'test-payment-secret'}
    with TestClient(app) as client:
        assert client.post('/api/class', headers=h, json={'key':'soldier'}).status_code == 200
        message = {'message':{'chat':{'id':pid},'from':{'id':pid},'successful_payment':{
            'invoice_payload':f'{pid}:zombo_100:0123456789abcdefabcd','currency':'XTR','total_amount':100,
            'telegram_payment_charge_id':'charge-test-986100'}}}
        assert client.post('/telegram/webhook', headers={'X-Telegram-Bot-Api-Secret-Token':'wrong'}, json=message).status_code == 403
        assert client.post('/telegram/webhook', headers=webhook_h, json=message).status_code == 200
        assert client.post('/telegram/webhook', headers=webhook_h, json=message).status_code == 200
        with SessionLocal() as db:
            assert db.get(Player,pid).zombo == 100
            assert db.get(Payment,'charge-test-986100') is not None
            movements=db.scalars(select(ResourceLedger).where(ResourceLedger.player_id==pid,
                ResourceLedger.resource_key=='zombo')).all()
            assert [(row.source_event,row.delta) for row in movements]==[('stars:charge-test-986100',100)]
        messages = [x for x in sender.call_args_list if x.args[0]=='sendMessage']
        assert len(messages) == 1
        forged = {'message':{'chat':{'id':pid},'from':{'id':pid},'successful_payment':{
            **message['message']['successful_payment'],
            'telegram_payment_charge_id':'charge-test-forged','total_amount':1}}}
        assert client.post('/telegram/webhook', headers=webhook_h, json=forged).status_code == 200
        with SessionLocal() as db:
            assert db.get(Player,pid).zombo == 100
            assert db.get(Payment,'charge-test-forged') is None
        monkeypatch.setattr(server,'ACCEPT_LEGACY_STAR_INVOICES',False)
        old_link_after_cutoff={'message':{'chat':{'id':pid},'from':{'id':pid},'successful_payment':{
            **message['message']['successful_payment'],
            'telegram_payment_charge_id':'charge-legacy-disabled'}}}
        assert client.post('/telegram/webhook',headers=webhook_h,json=old_link_after_cutoff).status_code==200
        with SessionLocal() as db:
            assert db.get(Player,pid).zombo==100
            assert db.get(PaymentReview,'charge-legacy-disabled') is not None


def test_new_invoice_requires_issued_payload_and_correct_payer(monkeypatch):
    calls=[]
    async def telegram(method, payload):
        calls.append((method,payload))
        return {'ok':True,'result':'https://example.test/invoice'}
    monkeypatch.setattr(server,'telegram_api',telegram)
    monkeypatch.setattr(server,'SECRET','issued-invoice-test')
    pid=986200
    h={'Authorization':f'demo:{pid}'}
    wh={'X-Telegram-Bot-Api-Secret-Token':'issued-invoice-test'}
    with TestClient(app) as client:
        assert client.post('/api/class',headers=h,json={'key':'medic'}).status_code==200
        response=client.post('/api/stars/invoice',headers=h,json={'key':'zombo_100'})
        assert response.status_code==200 and response.json()['url']=='https://example.test/invoice'
        payload=next(v['payload'] for m,v in calls if m=='createInvoiceLink')
        with SessionLocal() as db:
            row=db.get(StarInvoice,payload)
            assert row.player_id==pid and row.stars==100 and row.zombo==100
        query={'pre_checkout_query':{'id':'q1','from':{'id':pid},'invoice_payload':payload,
                                     'currency':'XTR','total_amount':100}}
        assert client.post('/telegram/webhook',headers=wh,json=query).status_code==200
        assert calls[-1][0]=='answerPreCheckoutQuery' and calls[-1][1]['ok'] is True
        query['pre_checkout_query']['from']['id']=pid+1
        assert client.post('/telegram/webhook',headers=wh,json=query).status_code==200
        assert calls[-1][1]['ok'] is False
        forged={'message':{'chat':{'id':pid},'from':{'id':pid},'successful_payment':{
            'invoice_payload':'z1:made-up-payload','currency':'XTR','total_amount':100,
            'telegram_payment_charge_id':'charge-not-issued'}}}
        assert client.post('/telegram/webhook',headers=wh,json=forged).status_code==200
        valid={'message':{'chat':{'id':pid},'from':{'id':pid},'successful_payment':{
            'invoice_payload':payload,'currency':'XTR','total_amount':100,
            'telegram_payment_charge_id':'charge-issued-986200'}}}
        assert client.post('/telegram/webhook',headers=wh,json=valid).status_code==200
        assert client.post('/telegram/webhook',headers=wh,json=valid).status_code==200
        with SessionLocal() as db:
            assert db.get(Player,pid).zombo==100
            assert db.get(Payment,'charge-not-issued') is None
            assert db.get(PaymentReview,'charge-not-issued').reason=='invoice_not_verified'
            assert db.get(Payment,'charge-issued-986200') is not None
