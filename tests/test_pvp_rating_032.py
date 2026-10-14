"""0.32: true Elo, five leagues and daily PvP anti-farm economy."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from tests.test_game import app
from models import Player, SessionLocal
from pvp_rating import (league, elo_change, settle_rated_duel,
                        daily_remaining, DAILY_REWARDED_DUELS)


def auth(pid):return {'Authorization':f'demo:{pid}'}


def make_duel(client,attacker,defender):
    challenge=client.post('/api/pvp/challenge',headers=auth(attacker),
                          json={'player_id':defender})
    assert challenge.status_code==200,challenge.text
    current=client.get('/api/pvp',headers=auth(defender)).json()['match']
    accepted=client.post('/api/pvp/act',headers=auth(defender),
                         json={'id':current['id'],'action':'accept'})
    assert accepted.status_code==200,accepted.text
    return current['id']


def finish_duel(client,defender,duel):
    outcome=client.post('/api/pvp/act',headers=auth(defender),
                        json={'id':duel,'action':'surrender'})
    assert outcome.status_code==200,outcome.text
    return outcome.json()


def test_real_elo_and_five_leagues():
    assert elo_change(1000,1000)==16
    assert elo_change(900,1400)>elo_change(1400,900)
    assert elo_change(0,10**12)>0
    assert elo_change(10**12,0)>0
    assert [league(x)['key'] for x in (1000,1150,1400,1700,2000)]==[
        'bronze','silver','gold','platinum','diamond']


def test_repeat_surrenders_do_not_create_extra_caps_xp_or_rating():
    winner,loser=99332001,99332002
    with TestClient(app) as api:
        for pid in (winner,loser):
            response=api.post('/api/class',headers=auth(pid),json={'key':'soldier'})
            assert response.status_code==200,response.text
        first=finish_duel(api,loser,make_duel(api,winner,loser))
        assert first['rated'] is True
        assert first['elo_delta']==16
        with SessionLocal() as db:
            w,l=db.get(Player,winner),db.get(Player,loser)
            assert (w.rating,l.rating)==(1016,984)
            assert w.caps==185
            first_xp,first_wins=w.xp,w.pvp_wins
        second=finish_duel(api,loser,make_duel(api,winner,loser))
        assert second['rated'] is False and second['elo_delta']==0
        with SessionLocal() as db:
            w,l=db.get(Player,winner),db.get(Player,loser)
            assert w.caps==185 and w.xp==first_xp
            assert (w.rating,l.rating)==(1016,984)
            assert w.pvp_wins==first_wins+1
        lobby=api.get('/api/pvp',headers=auth(winner)).json()
        assert lobby['league']['key']=='bronze'
        assert lobby['remaining_rewarded']==DAILY_REWARDED_DUELS-1
        profile=api.get('/api/me',headers=auth(winner)).json()
        assert profile['league']['key']=='bronze'


def test_daily_limit_applies_to_both_opponents_and_resets_in_utc():
    start=datetime(2026,10,14,12,0,tzinfo=timezone.utc)
    hero=Player(id=99001,rating=1000,stats={})
    opponents=[Player(id=99010+i,rating=1000,stats={}) for i in range(7)]
    for other in opponents[:5]:
        allowed,delta=settle_rated_duel(hero,other,start)
        assert allowed and delta>0
    assert daily_remaining(hero,start)==0
    assert not settle_rated_duel(hero,opponents[5],start)[0]
    assert not settle_rated_duel(hero,opponents[0],start)[0]
    # Reversing winner and loser cannot re-award an already used pair.
    assert not settle_rated_duel(opponents[0],hero,start)[0]
    next_day=start+timedelta(days=1)
    assert daily_remaining(hero,next_day)==5
    assert settle_rated_duel(hero,opponents[0],next_day)[0]


def test_no_elo_inflation_on_draw_and_no_unauthenticated_arena_rewards():
    a,b=99332003,99332004
    with TestClient(app) as api:
        for pid in (a,b):
            api.post('/api/class',headers=auth(pid),json={'key':'soldier'})
        duel=make_duel(api,a,b)
        initial=api.get('/api/me',headers=auth(a)).json()['rating']
        for pid in (a,b):
            proposal=api.post('/api/pvp/act',headers=auth(pid),
                              json={'id':duel,'action':'peace'})
            assert proposal.status_code==200,proposal.text
        with SessionLocal() as db:
            assert db.get(Player,a).rating==initial
            assert db.get(Player,b).rating==initial
        unauthorized=api.post('/api/pvp/act',json={'id':duel,'action':'surrender'})
        assert unauthorized.status_code==401
