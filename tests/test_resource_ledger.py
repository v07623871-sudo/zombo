"""The ledger must mirror committed resource changes without creating rewards."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from tests.test_game import app
import app as server
from models import SessionLocal, Player, ResourceLedger, tag_resource_operation
from game import give_item, take_item
from gear import create_gear, GearItem


def headers(pid):
    return {'Authorization': f'demo:{pid}'}


def entries(pid, *, kind=None, key=None):
    with SessionLocal() as db:
        statement = select(ResourceLedger).where(ResourceLedger.player_id == pid)
        if kind:
            statement = statement.where(ResourceLedger.kind == kind)
        if key:
            statement = statement.where(ResourceLedger.resource_key == key)
        return db.scalars(statement.order_by(ResourceLedger.id)).all()


def test_registration_daily_replay_and_transaction_rollback():
    pid = 99872001
    with TestClient(app) as client:
        assert client.get('/api/me', headers=headers(pid)).status_code == 200
        opening = entries(pid)
        assert [(row.kind, row.resource_key, row.delta) for row in opening if row.kind == 'currency'] == [
            ('currency', 'caps', 150)]
        assert {(row.resource_key, row.delta) for row in opening if row.kind == 'item'} == {
            ('knife', 1), ('medkit', 2), ('food', 2), ('water', 2), ('wood', 3)}
        assert len({row.source_event for row in opening}) == 1
        assert len({row.sequence for row in opening}) == len(opening)
        assert opening[0].source_event.startswith('GET:/api/me:')

        assert client.post('/api/class', headers=headers(pid), json={'key': 'soldier'}).status_code == 200
        assert client.post('/api/daily', headers=headers(pid)).status_code == 200
        after = entries(pid, kind='currency', key='caps')
        assert [row.delta for row in after] == [150, 75]
        assert [row.balance_after for row in after] == [150, 225]
        assert client.post('/api/daily', headers=headers(pid)).status_code == 400
        assert [row.delta for row in entries(pid, kind='currency', key='caps')] == [150, 75]

        with pytest.raises(RuntimeError):
            with SessionLocal.begin() as db:
                player = db.get(Player, pid)
                player.caps += 900
                db.flush()
                assert db.scalar(select(ResourceLedger.id).where(
                    ResourceLedger.player_id == pid, ResourceLedger.delta == 900)) is not None
                raise RuntimeError('force rollback')
        assert [row.delta for row in entries(pid, kind='currency', key='caps')] == [150, 75]
        with SessionLocal() as db:
            assert db.get(Player, pid).caps == 225


def test_stacked_items_and_gear_ownership_are_recorded():
    seller, buyer = 99872002, 99872003
    with TestClient(app) as client:
        for pid in (seller, buyer):
            assert client.get('/api/me', headers=headers(pid)).status_code == 200
        with SessionLocal.begin() as db:
            give_item(db, seller, 'metal', 3)
            gear = create_gear(db, seller, 'rifle', 'rare', 'test')
            gear_id = gear.id
        assert [row.delta for row in entries(seller, kind='item', key='metal')] == [3]
        assert [row.delta for row in entries(seller, kind='gear', key=str(gear_id))] == [1]

        with SessionLocal.begin() as db:
            take_item(db, seller, 'metal', 3)
            item = db.get(GearItem, gear_id)
            item.player_id = buyer
        assert [row.delta for row in entries(seller, kind='item', key='metal')] == [3, -3]
        assert [row.delta for row in entries(seller, kind='gear', key=str(gear_id))] == [1, -1]
        assert [row.delta for row in entries(buyer, kind='gear', key=str(gear_id))] == [1]


def test_ledger_admin_filters_and_permission():
    admin_id, player_id = 99872004, 99872005
    server.ADMIN_IDS.add(admin_id)
    try:
        with TestClient(app) as client:
            for pid in (admin_id, player_id):
                assert client.get('/api/me', headers=headers(pid)).status_code == 200
            assert client.get('/api/admin/ledger', headers=headers(player_id)).status_code == 403
            response = client.get('/api/admin/ledger', headers=headers(admin_id),
                                  params={'player_id': player_id, 'kind': 'currency', 'page': 1})
            assert response.status_code == 200, response.text
            rows = response.json()['items']
            assert rows and all(row['player_id'] == player_id and row['kind'] == 'currency' for row in rows)
            assert client.get('/api/admin/ledger', headers=headers(admin_id),
                              params={'kind': 'unknown'}).status_code == 422
            assert client.get('/api/admin/ledger', headers=headers(admin_id),
                              params={'page': 0}).status_code == 422
    finally:
        server.ADMIN_IDS.discard(admin_id)


def test_stable_source_event_replay_rolls_back_balance():
    pid = 99872006
    with TestClient(app) as client:
        assert client.get('/api/me', headers=headers(pid)).status_code == 200
        with SessionLocal.begin() as db:
            tag_resource_operation(db, 'test:fixed-payout', stable=True)
            player = db.get(Player, pid)
            player.zombo += 10
        assert [row.delta for row in entries(pid, kind='currency', key='zombo')] == [10]
        with pytest.raises(IntegrityError):
            with SessionLocal.begin() as db:
                tag_resource_operation(db, 'test:fixed-payout', stable=True)
                db.get(Player, pid).zombo += 10
        with SessionLocal() as db:
            assert db.get(Player, pid).zombo == 10
        assert [row.delta for row in entries(pid, kind='currency', key='zombo')] == [10]
