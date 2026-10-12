"""Raid and clan-war signals are opt-in, transactional, and checked at delivery."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.test_game import app
from models import SessionLocal, Player, TerritoryWar
from notifications import NotificationOutbox, _eligible
from raids import RaidRun
from clan_wars import roster, _finish, ZONE
from tests.test_clan_wars import setup


def headers(pid):
    return {'Authorization': f'demo:{pid}'}


def signals(db, prefix):
    return db.scalars(select(NotificationOutbox).where(
        NotificationOutbox.event_key.like(prefix + '%')).order_by(NotificationOutbox.id)).all()


def test_raid_signals_and_stale_delivery():
    ids = [988501, 988502, 988503]
    with TestClient(app) as client:
        for pid in ids:
            assert client.post('/api/class', headers=headers(pid),
                               json={'key': 'soldier'}).status_code == 200
        for pid in ids[:2]:
            response = client.post('/api/notifications/settings', headers=headers(pid),
                                   json={'category': 'raids', 'enabled': True})
            assert response.status_code == 200, response.text
        run_id = client.post('/api/raids/create', headers=headers(ids[0]),
                             json={'key': 'outpost'}).json()['id']
        for pid in ids[1:]:
            assert client.post('/api/raids/join', headers=headers(pid),
                               json={'id': run_id}).status_code == 200
        with SessionLocal() as db:
            rows = signals(db, f'raid:{run_id}:')
            assert [(r.kind, r.player_id) for r in rows] == [('raid_ready', ids[0])]
            assert _eligible(db, rows[0], datetime.now(timezone.utc))
        assert client.post('/api/raids/launch', headers=headers(ids[0]),
                           json={'id': run_id}).status_code == 200
        with SessionLocal() as db:
            rows = signals(db, f'raid:{run_id}:')
            assert len(rows) == 5
            assert sorted(r.kind for r in rows).count('raid_started') == 2
            assert sorted(r.kind for r in rows).count('raid_deadline') == 2
            ready = next(r for r in rows if r.kind == 'raid_ready')
            assert not _eligible(db, ready, datetime.now(timezone.utc))
        with SessionLocal.begin() as db:
            run = db.get(RaidRun, run_id)
            run.stage = 2
            run.enemy_hp = 1
        result = client.post('/api/raids/act', headers=headers(ids[0]),
                             json={'id': run_id, 'action': 'attack'})
        assert result.status_code == 200, result.text
        assert result.json()['raid']['status'] == 'cleared'
        with SessionLocal() as db:
            rows = signals(db, f'raid:{run_id}:')
            cleared = [r for r in rows if r.kind == 'raid_cleared']
            assert len(cleared) == 1 and cleared[0].player_id == ids[0]
            assert _eligible(db, cleared[0], datetime.now(timezone.utc))
            assert all(not _eligible(db, r, datetime.now(timezone.utc))
                       for r in rows if r.kind in ('raid_started', 'raid_deadline'))
        assert client.post('/api/raids/claim', headers=headers(ids[0]),
                           json={'id': run_id}).status_code == 200
        with SessionLocal() as db:
            assert not _eligible(db, db.get(NotificationOutbox, cleared[0].id),
                                 datetime.now(timezone.utc))
        with SessionLocal.begin() as db:
            for row in signals(db, f'raid:{run_id}:'):
                row.status = 'skipped'


def test_clan_war_signals_follow_roster_and_result():
    def stamp(hour):
        return datetime(2026, 10, 20, hour, tzinfo=ZONE).astimezone(timezone.utc)

    with TestClient(app) as client:
        with SessionLocal.begin() as db:
            (pa, ca), (pb, cb) = setup(db, 5000)
            war = TerritoryWar(territory_id='clinic', war_date='2026-10-20',
                               attacker_clan_id=ca.id, defender_clan_id=cb.id,
                               status='formation', bid=100)
            db.add(war)
            db.flush()
            war_id, player_id = war.id, pa.id
        response = client.post('/api/notifications/settings', headers=headers(player_id),
                               json={'category': 'clans', 'enabled': True})
        assert response.status_code == 200, response.text
        with SessionLocal.begin() as db:
            roster(db, db.get(Player, player_id), war_id, player_id, True, stamp(11))
            roster(db, db.get(Player, 101002), war_id, 101002, True, stamp(11))
        with SessionLocal() as db:
            rows = signals(db, f'war:{war_id}:')
            assert len(rows) == 1 and rows[0].kind == 'war_start'
            assert _eligible(db, rows[0], stamp(16))
        with SessionLocal.begin() as db:
            roster(db, db.get(Player, player_id), war_id, player_id, False, stamp(12))
        with SessionLocal() as db:
            assert not _eligible(db, db.get(NotificationOutbox, rows[0].id), stamp(16))
        with SessionLocal.begin() as db:
            roster(db, db.get(Player, player_id), war_id, player_id, True, stamp(13))
        with SessionLocal.begin() as db:
            _finish(db, db.get(TerritoryWar, war_id), db.get(TerritoryWar, war_id).attacker_clan_id,
                    'Атакующие победили')
        with SessionLocal() as db:
            rows = signals(db, f'war:{war_id}:')
            assert [r.kind for r in rows] == ['war_start', 'war_result']
            assert not _eligible(db, rows[0], stamp(16))
            assert _eligible(db, rows[1], stamp(17))
        response = client.post('/api/notifications/settings', headers=headers(player_id),
                               json={'category': 'clans', 'enabled': False})
        assert response.status_code == 200, response.text
        with SessionLocal() as db:
            assert not _eligible(db, db.get(NotificationOutbox, rows[1].id), stamp(17))
        with SessionLocal.begin() as db:
            for row in signals(db, f'war:{war_id}:'):
                row.status = 'skipped'
