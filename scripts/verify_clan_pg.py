"""GitHub Actions PostgreSQL integration check (never run against production)."""
import os
from fastapi.testclient import TestClient
from sqlalchemy import select
from models import Base, SessionLocal, engine, Player, Clan
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