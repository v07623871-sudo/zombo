"""Regressions for lifetime-XP and clan treasury audit: real, atomic DB entries."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from tests.test_game import app
import app as server
from models import (SessionLocal, Player, Clan, ResourceLedger, ClanTreasuryLedger,
                    tag_resource_operation)
from game import gain_xp


def headers(pid):
    return {'Authorization': f'demo:{pid}'}


def xp_rows(pid):
    with SessionLocal() as db:
        return db.scalars(select(ResourceLedger).where(
            ResourceLedger.player_id == pid, ResourceLedger.kind == 'xp')
            .order_by(ResourceLedger.id)).all()


def treasury_rows(cid):
    with SessionLocal() as db:
        return db.scalars(select(ClanTreasuryLedger).where(
            ClanTreasuryLedger.clan_id == cid).order_by(ClanTreasuryLedger.id)).all()


def test_xp_ledger_accounts_for_level_up_and_loss():
    pid = 99872201
    with TestClient(app) as client:
        assert client.get('/api/me', headers=headers(pid)).status_code == 200
        assert xp_rows(pid) == []
        with SessionLocal.begin() as db:
            p = db.get(Player, pid)
            gain_xp(p, 450)  # Level 1 requires exactly 450 XP.
        with SessionLocal() as db:
            p = db.get(Player, pid)
            assert p.level == 2 and p.xp == 0
        rows = xp_rows(pid)
        assert [(r.delta, r.balance_after) for r in rows] == [(450, 450)]

        with SessionLocal.begin() as db:
            p = db.get(Player, pid)
            gain_xp(p, 30)
        assert [(r.delta, r.balance_after) for r in xp_rows(pid)] == [
            (450, 450), (30, 480)]

        with SessionLocal.begin() as db:
            p = db.get(Player, pid)
            p.xp = 10  # XP can also be reduced on death.
        assert [(r.delta, r.balance_after) for r in xp_rows(pid)] == [
            (450, 450), (30, 480), (-20, 460)]

        with pytest.raises(RuntimeError):
            with SessionLocal.begin() as db:
                db.get(Player, pid).xp += 80
                db.flush()
                raise RuntimeError('force rollback')
        assert [r.delta for r in xp_rows(pid)] == [450, 30, -20]


def test_clan_treasury_audited_and_stable_event_cannot_pay_twice():
    pid = 99872202
    with TestClient(app) as client:
        assert client.get('/api/me', headers=headers(pid)).status_code == 200
        with SessionLocal.begin() as db:
            db.add(Clan(name='Ledger Treasury Test 022', leader_id=pid, treasury=180))
        with SessionLocal() as db:
            cid = db.scalar(select(Clan.id).where(Clan.name == 'Ledger Treasury Test 022'))
        assert [(r.delta, r.balance_after) for r in treasury_rows(cid)] == [(180, 180)]

        with SessionLocal.begin() as db:
            tag_resource_operation(db, 'clan:022:weekly:reward', stable=True)
            c = db.scalar(select(Clan).where(Clan.id == cid).with_for_update())
            c.treasury += 60
        rows = treasury_rows(cid)
        assert [(r.delta, r.balance_after) for r in rows] == [(180, 180), (60, 240)]
        assert rows[-1].source_event == 'clan:022:weekly:reward'

        with pytest.raises(IntegrityError):
            with SessionLocal.begin() as db:
                tag_resource_operation(db, 'clan:022:weekly:reward', stable=True)
                c = db.scalar(select(Clan).where(Clan.id == cid).with_for_update())
                c.treasury += 60
        with SessionLocal() as db:
            assert db.get(Clan, cid).treasury == 240
        assert len(treasury_rows(cid)) == 2

        with pytest.raises(RuntimeError):
            with SessionLocal.begin() as db:
                db.get(Clan, cid).treasury -= 30
                db.flush()
                assert any(r.delta == -30 for r in db.scalars(
                    select(ClanTreasuryLedger).where(ClanTreasuryLedger.clan_id == cid)))
                raise RuntimeError('force rollback')
        assert len(treasury_rows(cid)) == 2


def test_admin_treasury_permissions_filters_and_xp_resource_kind():
    admin_id, player_id = 99872203, 99872204
    server.ADMIN_IDS.add(admin_id)
    try:
        with TestClient(app) as client:
            for pid in (admin_id, player_id):
                assert client.get('/api/me', headers=headers(pid)).status_code == 200
            with SessionLocal.begin() as db:
                db.add(Clan(name='Ledger Admin Test 022', leader_id=player_id, treasury=20))
                gain_xp(db.get(Player, player_id), 55)
            with SessionLocal() as db:
                cid = db.scalar(select(Clan.id).where(Clan.name == 'Ledger Admin Test 022'))
            assert client.get('/api/admin/treasury-ledger', headers=headers(player_id)).status_code == 403
            a = client.get('/api/admin/treasury-ledger', headers=headers(admin_id),
                           params={'clan_id': cid, 'page': 1})
            assert a.status_code == 200, a.text
            assert len(a.json()['items']) == 1
            assert a.json()['items'][0]['delta'] == 20
            assert a.json()['items'][0]['clan_id'] == cid
            assert client.get('/api/admin/treasury-ledger', headers=headers(admin_id),
                              params={'clan_id': cid + 500000}).json()['items'] == []
            assert client.get('/api/admin/treasury-ledger', headers=headers(admin_id),
                              params={'page': 0}).status_code == 422
            res = client.get('/api/admin/ledger', headers=headers(admin_id),
                             params={'kind': 'xp', 'player_id': player_id})
            assert res.status_code == 200, res.text
            assert [(x['delta'], x['resource_key']) for x in res.json()['items']] == [
                (55, 'lifetime')]
    finally:
        server.ADMIN_IDS.discard(admin_id)
