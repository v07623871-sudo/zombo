"""Regression tests for persistent per-player quotas and Telegram update de-duplication."""
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models import Base
from security import enforce_quota, TooManyActions, claim_update, finish_update, TelegramReceipt, prune_update_receipts
from tests.test_game import app


@pytest.fixture
def db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def test_write_quota_is_persistent_and_rolls_over(db):
    assert enforce_quota(db, 1234, 'write', limit=2, timestamp=120) == 1
    assert enforce_quota(db, 1234, 'write', limit=2, timestamp=121) == 2
    with pytest.raises(TooManyActions) as e:
        enforce_quota(db, 1234, 'write', limit=2, timestamp=122)
    assert e.value.retry_after == 58
    # Even on multiple workers the new minute resets the persisted counter.
    assert enforce_quota(db, 1234, 'write', limit=2, timestamp=180) == 1
    assert enforce_quota(db, 1235, 'write', limit=2, timestamp=180) == 1


def test_receipt_duplicate_busy_and_crash_recovery(db):
    first, lease = claim_update(db, 500, timestamp=1000)
    assert first == 'claimed' and lease
    db.commit()
    assert claim_update(db, 500, timestamp=1000)[0] == 'busy'  # same second is still busy
    assert claim_update(db, 500, timestamp=1100)[0] == 'busy'
    res, recovered_lease = claim_update(db, 500, timestamp=1301)
    assert res == 'claimed' and recovered_lease != lease
    finish_update(db, 500, completed=True, lease=lease)
    assert db.get(TelegramReceipt, 500).state == 'processing'
    finish_update(db, 500, completed=True, lease=recovered_lease)
    db.commit()
    assert claim_update(db, 500, timestamp=1500)[0] == 'duplicate'
    status, lease501 = claim_update(db, 501, timestamp=1500)
    assert status == 'claimed'
    finish_update(db, 501, completed=False, lease=lease501)
    db.commit()
    assert db.get(TelegramReceipt, 501) is None
    assert claim_update(db, 501, timestamp=1501)[0] == 'claimed'
    with pytest.raises(ValueError):claim_update(db, -1)


def test_webhook_delivery_duplicate_and_retry(monkeypatch):
    import app as module
    sender = AsyncMock(return_value={'ok':True})
    monkeypatch.setattr(module,'telegram_api',sender)
    monkeypatch.setattr(module,'SECRET','in-test-secret')
    request = {'update_id': 19910701, 'message':{'chat':{'id': 50177},'from':{'id': 50177},'text':'/help'}}
    headers={'X-Telegram-Bot-Api-Secret-Token':'in-test-secret'}
    with TestClient(app) as client:
        assert client.post('/telegram/webhook',json=request,headers=headers).status_code==200
        assert sender.await_count == 1
        replay=client.post('/telegram/webhook',json=request,headers=headers)
        assert replay.status_code==200 and replay.json()['duplicate']
        assert sender.await_count == 1
        sender.reset_mock()
        sender.return_value={'ok':False}
        request['update_id']+=1
        assert client.post('/telegram/webhook',json=request,headers=headers).status_code==503
        sender.return_value={'ok':True}
        assert client.post('/telegram/webhook',json=request,headers=headers).status_code==200
        assert sender.await_count == 2


def test_unauthorized_webhook_never_reserves_receipt(monkeypatch):
    import app as module
    monkeypatch.setattr(module,'SECRET','in-test-secret')
    with TestClient(app) as client:
        body={'update_id':19910703,'message':{'chat':{'id':1},'from':{'id':1},'text':'/help'}}
        assert client.post('/telegram/webhook',json=body,headers={'X-Telegram-Bot-Api-Secret-Token':'invalid'}).status_code==403
        from models import SessionLocal
        with SessionLocal() as session:
            assert session.get(TelegramReceipt,19910703) is None


def test_http_api_rate_limit_is_authenticated(monkeypatch):
    from models import SessionLocal
    import app as module
    # Each request is charged. We can seed the quota close to its limit.
    with TestClient(app) as client:
        uid=91237718
        headers={'Authorization':f'demo:{uid}'}
        assert client.post('/api/class',json={'key':'soldier'},headers=headers).status_code==200
        from sqlalchemy import text
        with SessionLocal.begin() as session:
            session.execute(text("UPDATE api_quotas SET count=180 WHERE player_id=:pid AND scope='write'"),{'pid':uid})
        denied=client.post('/api/daily',headers=headers)
        assert denied.status_code==429
        assert int(denied.headers['Retry-After'])>0
        assert 'Слишком много' in denied.json()['detail']
        # The game mutation was not applied despite a valid signed user.
        from models import Player
        with SessionLocal() as session:
            assert not session.get(Player,uid).last_daily
