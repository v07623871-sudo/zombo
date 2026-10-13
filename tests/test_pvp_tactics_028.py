"""PvP 0.28: seven meaningful actions, real resource spending and 90 sec clock."""
from datetime import timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from tests.test_game import app
from models import Player, PvPMatch, SessionLocal, now
from game import item_count


def auth(pid):
    return {'Authorization':f'demo:{pid}'}


def pair(api,a,b):
    for pid in (a,b):
        assert api.post('/api/class',headers=auth(pid),
                        json={'key':'thief' if pid==a else 'soldier'}).status_code==200
    challenge=api.post('/api/pvp/challenge',headers=auth(a),json={'player_id':b})
    assert challenge.status_code==200,challenge.text
    match=api.get('/api/pvp',headers=auth(a)).json()['match']
    accept=api.post('/api/pvp/act',headers=auth(b),json={'id':match['id'],'action':'accept'})
    assert accept.status_code==200,accept.text
    return match['id']


def act(api,pid,match,action):
    return api.post('/api/pvp/act',headers=auth(pid),json={'id':match,'action':action})


def test_pvp_steal_once_and_medkit_heals_actual_match_hp():
    a,b=99328001,99328002
    with TestClient(app) as api:
        mid=pair(api,a,b)
        with SessionLocal.begin() as db:
            db.get(Player,a).caps=100
            db.get(Player,b).caps=100
            match=db.get(PvPMatch,mid)
            match.hp_a=10
        with SessionLocal() as db:
            before_items=item_count(db,a,'medkit')
        theft=act(api,a,mid,'steal')
        assert theft.status_code==200,theft.text
        with SessionLocal() as db:
            assert db.get(Player,a).caps+db.get(Player,b).caps==200
            assert db.get(Player,a).caps>100
        assert act(api,b,mid,'defend').status_code==200
        assert act(api,a,mid,'steal').status_code==400
        match=api.get('/api/pvp',headers=auth(a)).json()['match']
        assert match['current_id']==a and match['turn_seconds']==90
        assert not any(x.startswith('!pvp:') for x in match['log'])
        heal=act(api,a,mid,'heal')
        assert heal.status_code==200,heal.text
        with SessionLocal() as db:
            m=db.get(PvPMatch,mid)
            assert m.hp_a>10
            assert item_count(db,a,'medkit')==before_items-1


def test_pvp_two_sided_peace_is_draw_without_rating_or_money_farming():
    a,b=99328003,99328004
    with TestClient(app) as api:
        mid=pair(api,a,b)
        with SessionLocal() as db:
            ratings=(db.get(Player,a).rating,db.get(Player,b).rating)
            wins=(db.get(Player,a).pvp_wins,db.get(Player,b).pvp_wins)
        proposal=act(api,a,mid,'peace')
        assert proposal.status_code==200,proposal.text
        accepted=act(api,b,mid,'peace')
        assert accepted.status_code==200,accepted.text
        with SessionLocal() as db:
            assert db.get(PvPMatch,mid).state=='finished'
            assert (db.get(Player,a).rating,db.get(Player,b).rating)==ratings
            assert (db.get(Player,a).pvp_wins,db.get(Player,b).pvp_wins)==wins


def test_pvp_timeout_after_ninety_seconds():
    a,b=99328005,99328006
    with TestClient(app) as api:
        mid=pair(api,a,b)
        with SessionLocal.begin() as db:
            db.get(PvPMatch,mid).updated_at=now()-timedelta(seconds=92)
        timeout=act(api,b,mid,'claim_timeout')
        assert timeout.status_code==200,timeout.text
        with SessionLocal() as db:
            assert db.get(PvPMatch,mid).state=='finished'


def test_pvp_crit_and_feint_are_distinct_attacks():
    a,b=99328007,99328008
    with TestClient(app) as api:
        mid=pair(api,a,b)
        with SessionLocal.begin() as db:
            m=db.get(PvPMatch,mid)
            m.hp_a=2000;m.hp_b=2000
        with patch('app.random.random',return_value=0),patch(
                'app.random.uniform',return_value=.8):
            first=act(api,a,mid,'crit')
            assert first.status_code==200,first.text
            assert 'критическая атака' in first.json()['message']
            second=act(api,b,mid,'defend')
            assert second.status_code==200,second.text
            third=act(api,a,mid,'feint')
            assert third.status_code==200,third.text
            assert 'финт' in third.json()['message']
        state=api.get('/api/pvp',headers=auth(a)).json()['match']
        assert state['defender']['hp']<2000
