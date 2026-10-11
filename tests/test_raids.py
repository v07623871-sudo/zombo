"""Real API-level cooperative raid tests: restrictions, fights, persistence, rewards."""
from tests.test_game import app
from fastapi.testclient import TestClient
from sqlalchemy import select
from models import SessionLocal, Player
from raids import RaidRun, RaidMember, RAIDS
from datetime import timedelta
from models import now

A={'Authorization':'demo:82001'}
B={'Authorization':'demo:82002'}
C={'Authorization':'demo:82003'}
D={'Authorization':'demo:82004'}

def test_raid_structure():
    assert len(RAIDS)==3
    for x in RAIDS.values():
        assert len(x['enemy_names'])==3
        assert x['duration_hours'] in [1,3,6]


def test_coop_raid_lifecycle(monkeypatch):
    # Deterministic damage and moderate incoming damage make raid winnable.
    import raids
    monkeypatch.setattr(raids.random,'uniform',lambda lo,hi:1.)
    with TestClient(app) as client:
        for h in [A,B,C,D]:
            assert client.post('/api/class',headers=h,json={'key':'medic'}).status_code==200
        with SessionLocal.begin() as db:
            for uid in [82001,82002,82003,82004]:
                p=db.get(Player,uid);p.level=30;p.stamina=500;p.hp=200;p.stats={'strength':30,'agility':0,'endurance':15,'accuracy':0,'regen':0,'luck':0}
        invalid=client.post('/api/raids/create',headers=A,json={'key':'nope'})
        assert invalid.status_code==400
        ret=client.post('/api/raids/create',headers=A,json={'key':'outpost'})
        assert ret.status_code==200,ret.text
        run=ret.json()['id']
        assert client.post('/api/raids/create',headers=A,json={'key':'vault'}).status_code==400
        assert client.post('/api/raids/launch',headers=A,json={'id':run}).status_code==400
        assert client.post('/api/raids/join',headers=B,json={'id':run}).status_code==200
        assert client.post('/api/raids/join',headers=C,json={'id':run}).status_code==200
        assert client.post('/api/raids/join',headers=B,json={'id':run}).status_code==400
        assert client.post('/api/raids/launch',headers=B,json={'id':run}).status_code==400
        assert client.post('/api/raids/launch',headers=A,json={'id':run}).status_code==200
        assert client.post('/api/raids/join',headers=D,json={'id':run}).status_code==400
        raid=client.get('/api/raids',headers=A).json()['my_raid']
        assert raid['member_count']==3 and raid['stage']==1 and raid['status']=='active'
        assert client.post('/api/raids/claim',headers=A,json={'id':run}).status_code==400
        assert client.post('/api/raids/act',headers=D,json={'id':run,'action':'attack'}).status_code==400
        seen=0
        # Bypass time cooldown only for this simulated test.
        for i in range(150):
            h=[A,B,C][i%3]
            with SessionLocal.begin() as db:
                for m in db.scalars(select(RaidMember).where(RaidMember.run_id==run)):
                    m.last_action=None
                    m.hp=m.max_hp
                p=db.get(Player,[82001,82002,82003][i%3]);p.stamina=500
            out=client.post('/api/raids/act',headers=h,json={'id':run,'action':'attack'})
            assert out.status_code==200,out.text
            seen+=1
            status=out.json()['raid']['status']
            if status=='cleared':break
        assert status=='cleared' and seen>1
        assert client.get('/api/raids',headers=A).json()['my_raid'] is None
        winners=client.get('/api/raids',headers=A).json()['recent']
        assert winners[0]['status']=='cleared'
        prize=client.post('/api/raids/claim',headers=A,json={'id':run})
        assert prize.status_code==200,prize.text
        assert client.post('/api/raids/claim',headers=A,json={'id':run}).status_code==400
        assert client.post('/api/raids/claim',headers=D,json={'id':run}).status_code==400


def test_raid_bad_authorization():
    with TestClient(app) as c:
        assert c.get('/api/raids').status_code==401
        assert c.post('/api/raids/create',json={'key':'outpost'}).status_code==401


def test_expired_action_persists_terminal_status():
    ids = [82901, 82902, 82903]
    with TestClient(app) as client:
        for pid in ids:
            assert client.post('/api/class', headers={'Authorization':f'demo:{pid}'}, json={'key':'medic'}).status_code == 200
        owner = {'Authorization':f'demo:{ids[0]}'}
        run = client.post('/api/raids/create', headers=owner, json={'key':'outpost'}).json()['id']
        for pid in ids[1:]:
            assert client.post('/api/raids/join', headers={'Authorization':f'demo:{pid}'}, json={'id':run}).status_code == 200
        assert client.post('/api/raids/launch', headers=owner, json={'id':run}).status_code == 200
        with SessionLocal.begin() as db:
            db.get(RaidRun, run).expires_at = now() - timedelta(seconds=1)
        response = client.post('/api/raids/act', headers=owner, json={'id':run,'action':'attack'})
        assert response.status_code == 200
        assert response.json()['raid']['status'] == 'expired'
        with SessionLocal() as db:
            assert db.get(RaidRun, run).status == 'expired'
