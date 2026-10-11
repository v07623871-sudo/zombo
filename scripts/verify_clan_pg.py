"""GitHub Actions PostgreSQL integration check (never run against production)."""
import os
from fastapi.testclient import TestClient
from sqlalchemy import select
from models import Base, SessionLocal, engine, Player, Clan, now
from game import progress
from clan_missions import ClanMission, ClanSeasonScore, TASKS
from app import app

assert os.getenv('DATABASE_URL','').startswith('postgresql'), 'Test must use disposable PostgreSQL'
assert not os.getenv('BOT_TOKEN'), 'Never run with a production bot token'
assert os.getenv('DEMO_MODE') == '1', 'Only local demo auth is supported'
Base.metadata.create_all(bind=engine)
headers={'Authorization':'demo:9927000101'}
with TestClient(app) as api:
    r=api.post('/api/class',headers=headers,json={'key':'soldier'})
    assert r.status_code==200,('class',r.text)
    with SessionLocal.begin() as db:
        db.get(Player,9927000101).caps=257
    r=api.post('/api/clans/create',headers=headers,json={'name':'CI Clan'})
    assert r.status_code==200,('clan create',r.text)
    clan_id=r.json()['id']
    with SessionLocal.begin() as db:
        progress(db,9927000101,'kills',TASKS['kills']['target'])
    board=api.get('/api/clan-missions',headers=headers)
    assert board.status_code==200,board.text
    task=next(x for x in board.json()['missions'] if x['code']=='kills')
    assert task['completed'] and task['can_claim'] and task['progress']==TASKS['kills']['target']
    r=api.post('/api/clan-missions/claim',headers=headers,json={'code':'kills'})
    assert r.status_code==200,('reward',r.text)
    r=api.post('/api/clan-missions/claim',headers=headers,json={'code':'kills'})
    assert r.status_code==400,('double claim',r.text)
    with SessionLocal.begin() as db:
        assert db.get(Clan,clan_id).treasury == TASKS['kills']['treasury']
        assert db.scalar(select(ClanMission).where(ClanMission.clan_id==clan_id,ClanMission.code=='kills')).completed_at
        assert db.scalar(select(ClanSeasonScore).where(ClanSeasonScore.clan_id==clan_id)).points==TASKS['kills']['renown']
    print('PostgreSQL clan missions and API: PASS')

# Real PostgreSQL expedition incident smoke: event row, leader permissions,
# risk/reward decision, settlement and idempotent payout.
from datetime import timedelta
from expeditions import ExpeditionRun, ExpeditionIncident

crew_ids = [9927000201, 9927000202, 9927000203]
with TestClient(app) as api:
    for pid in crew_ids:
        r = api.post('/api/class', headers={'Authorization': f'demo:{pid}'}, json={'key': 'soldier'})
        assert r.status_code == 200, ('create crew member', r.text)
    with SessionLocal.begin() as db:
        for pid in crew_ids:
            db.get(Player, pid).level = 30
    r = api.post('/api/expeditions/create', headers={'Authorization': f'demo:{crew_ids[0]}'},
                 json={'key': 'relay'})
    assert r.status_code == 200, ('create expedition', r.text)
    run_id = r.json()['id']
    for pid in crew_ids[1:]:
        r = api.post('/api/expeditions/join', headers={'Authorization': f'demo:{pid}'},
                     json={'id': run_id})
        assert r.status_code == 200, ('join expedition', r.text)
    for pid, role in zip(crew_ids, ('guard', 'scout', 'medic')):
        r = api.post('/api/expeditions/prepare', headers={'Authorization': f'demo:{pid}'},
                     json={'id': run_id, 'role': role})
        assert r.status_code == 200, ('prepare role', r.text)
    leader = {'Authorization': f'demo:{crew_ids[0]}'}
    r = api.post('/api/expeditions/launch', headers=leader, json={'id': run_id})
    assert r.status_code == 200, ('launch expedition', r.text)
    with SessionLocal.begin() as db:
        run = db.get(ExpeditionRun, run_id)
        run.started_at = now() - timedelta(hours=5)
        run.finishes_at = now() + timedelta(hours=7)
        event = db.scalar(select(ExpeditionIncident).where(ExpeditionIncident.run_id == run_id))
        assert event is not None
        event.roll = 0
    r = api.post('/api/expeditions/event', headers=leader,
                 json={'id': run_id, 'choice': 'cautious'})
    assert r.status_code == 200 and r.json()['reward_percent'] == 85, ('expedition event', r.text)
    r = api.post('/api/expeditions/event', headers=leader,
                 json={'id': run_id, 'choice': 'risky'})
    assert r.status_code == 400, ('replayed incident', r.text)
    with SessionLocal.begin() as db:
        db.get(ExpeditionRun, run_id).finishes_at = now() - timedelta(seconds=1)
    before = api.get('/api/me', headers=leader).json()['caps']
    r = api.post('/api/expeditions/claim', headers=leader, json={'id': run_id})
    assert r.status_code == 200 and r.json()['status'] == 'cleared', ('claim expedition', r.text)
    after = api.get('/api/me', headers=leader).json()['caps']
    assert after - before == 180 * 85 // 100
    assert api.post('/api/expeditions/claim', headers=leader, json={'id': run_id}).status_code == 400
    print('PostgreSQL timed expedition incident and one-time rewards: PASS')
