"""0.31: companions never farm supplies by fleeing or reusing a skill."""
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.test_game import app
from game import item_count
from models import Battle, Player, SessionLocal


def auth(pid):
    return {'Authorization':f'demo:{pid}'}


def hero(api,pid):
    resp=api.post('/api/class',headers=auth(pid),json={'key':'soldier'})
    assert resp.status_code==200,resp.text
    with SessionLocal.begin() as db:
        p=db.get(Player,pid)
        p.stats={**p.stats,'_pet':{'key':'cat','level':10,'xp':0}}
        p.hp=1000;p.stamina=500
        db.add(Battle(player_id=pid,kind='zombie:walker',enemy='Шатун',
                      enemy_hp=5000,enemy_max_hp=5000,enemy_damage=1,turn=0,log=[]))


def turn(api,pid,action):
    return api.post('/api/combat/turn',headers=auth(pid),
                    json={'action':action,'zone':'body'})


def test_pet_loot_is_not_paid_until_actual_victory_and_forfeit_on_flee():
    pid=99331001
    with TestClient(app) as api:
        hero(api,pid)
        with SessionLocal() as db:
            old=item_count(db,pid,'rubber')
        with patch('game.random.choice',return_value='rubber'):
            response=turn(api,pid,'pet')
        assert response.status_code==200,response.text
        assert not response.json()['finished']
        with SessionLocal() as db:
            assert item_count(db,pid,'rubber')==old
        result=turn(api,pid,'flee')
        assert result.status_code==200,result.text
        with SessionLocal() as db:
            assert item_count(db,pid,'rubber')==old
            assert db.scalar(select(Battle).where(Battle.player_id==pid)) is None


def test_long_battle_never_unlocks_same_pet_again():
    pid=99331002
    with TestClient(app) as api:
        hero(api,pid)
        with patch('game.random.choice',return_value='rubber'):
            assert turn(api,pid,'pet').status_code==200
        for _ in range(28):
            result=turn(api,pid,'defend')
            assert result.status_code==200,result.text
            assert result.json()['battle']['pet_available'] is False
        repeated=turn(api,pid,'pet')
        assert repeated.status_code==400,repeated.text
        with SessionLocal() as db:
            b=db.scalar(select(Battle).where(Battle.player_id==pid))
            assert b.turn>=29
            assert b.log.count('!pet:used')==1
            assert len([x for x in b.log if x.startswith('!pet:loot:')])==1
            assert len(b.log)<=24


def test_pet_supply_paid_exactly_once_after_victory():
    pid=99331003
    with TestClient(app) as api:
        hero(api,pid)
        with SessionLocal() as db:
            old=item_count(db,pid,'rubber')
        with patch('game.random.choice',return_value='rubber'):
            assert turn(api,pid,'pet').status_code==200
        with SessionLocal.begin() as db:
            battle=db.scalar(select(Battle).where(Battle.player_id==pid))
            battle.enemy_hp=1
        with patch('game.random.random',return_value=.2):
            won=turn(api,pid,'attack')
        assert won.status_code==200,won.text
        assert won.json()['finished'] and won.json()['won']
        assert 'rubber' in won.json()['loot']
        with SessionLocal() as db:
            assert item_count(db,pid,'rubber')==old+1
        assert turn(api,pid,'attack').status_code==400
        with SessionLocal() as db:
            assert item_count(db,pid,'rubber')==old+1
