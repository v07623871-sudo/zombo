from datetime import timedelta
from fastapi.testclient import TestClient
from tests.test_game import app
from models import SessionLocal, Player, PvPMatch, now


def h(pid):
    return {'Authorization':f'demo:{pid}'}


def test_waiting_player_can_claim_expired_turn_once():
    challenger, defender = 987101, 987102
    with TestClient(app) as client:
        for pid in (challenger, defender):
            assert client.post('/api/class',headers=h(pid),json={'key':'soldier'}).status_code==200
        assert client.post('/api/pvp/challenge',headers=h(challenger),
                           json={'player_id':10**100}).status_code==422
        assert client.post('/api/pvp/challenge',headers=h(challenger),
                           json={'player_id':defender}).status_code==200
        match=client.get('/api/pvp',headers=h(defender)).json()['match']
        assert client.post('/api/pvp/act',headers=h(defender),
                           json={'id':match['id'],'action':'accept'}).status_code==200
        early=client.post('/api/pvp/act',headers=h(defender),
                          json={'id':match['id'],'action':'claim_timeout'})
        assert early.status_code==400
        with SessionLocal.begin() as db:
            db.get(PvPMatch,match['id']).updated_at=now()-timedelta(minutes=6)
            caps_before=db.get(Player,defender).caps
        result=client.post('/api/pvp/act',headers=h(defender),
                           json={'id':match['id'],'action':'claim_timeout'})
        assert result.status_code==200, result.text
        assert client.post('/api/pvp/act',headers=h(defender),
                           json={'id':match['id'],'action':'claim_timeout'}).status_code==400
        with SessionLocal() as db:
            assert db.get(PvPMatch,match['id']).state=='finished'
            winner=db.get(Player,defender)
            assert winner.caps==caps_before+35
            assert winner.pvp_wins==1
        with SessionLocal.begin() as db:
            db.get(Player,defender).frozen=True
        assert client.post('/api/pvp/challenge',headers=h(challenger),
                           json={'player_id':defender}).status_code==400
        assert defender not in [x['id'] for x in client.get('/api/pvp',headers=h(challenger)).json()['players']]
