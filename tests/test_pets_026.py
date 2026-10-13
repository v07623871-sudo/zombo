"""Six permanent pets: adoption, progression, bonus and once-per-battle skill."""
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.test_game import app
from game import PETS, attack_power, pet_status, pet_bonus, pet_try_find, pet_victory
from models import Battle, Player, SessionLocal


def auth(pid):
    return {'Authorization':f'demo:{pid}'}


def test_pet_catalog_and_adoption_deduct_caps_and_persist():
    pid=99326001
    with TestClient(app) as c:
        assert len(c.get('/api/config').json()['pets'])==6
        assert c.post('/api/class',headers=auth(pid),json={'key':'soldier'}).status_code==200
        with SessionLocal.begin() as db:
            db.get(Player,pid).caps=1300
        response=c.post('/api/pets/adopt',headers=auth(pid),json={'key':'wolf'})
        assert response.status_code==200,response.text
        assert response.json()['pet']['key']=='wolf'
        assert c.get('/api/me',headers=auth(pid)).json()['pet']['level']==1
        with SessionLocal() as db:
            p=db.get(Player,pid)
            assert p.caps==50 and pet_status(p)['ability']=='Укус'
            assert pet_bonus(p,'power')>0
        again=c.post('/api/pets/adopt',headers=auth(pid),json={'key':'raven'})
        assert again.status_code==400
        assert c.post('/api/pets/adopt',headers=auth(pid),json={'key':'invalid'}).status_code==400


def test_companion_can_act_only_once_per_battle_and_costs_energy():
    pid=99326002
    with TestClient(app) as c:
        c.post('/api/class',headers=auth(pid),json={'key':'soldier'})
        with SessionLocal.begin() as db:
            p=db.get(Player,pid)
            p.stats={**p.stats,'_pet':{'key':'boar','level':3,'xp':1}}
            p.stamina=500
            db.add(Battle(player_id=pid,kind='zombie:walker',enemy='Шатун',
                          enemy_hp=2000,enemy_max_hp=2000,enemy_damage=1,log=[]))
        before=c.get('/api/me',headers=auth(pid)).json()
        assert before['battle']['pet_available']
        result=c.post('/api/combat/turn',headers=auth(pid),
                      json={'action':'pet','zone':'body'})
        assert result.status_code==200,result.text
        state=c.get('/api/me',headers=auth(pid)).json()
        assert state['stamina']==before['stamina']-3
        assert not state['battle']['pet_available']
        assert all('!pet:' not in entry for entry in state['battle']['log'])
        assert state['battle']['hp']<before['battle']['hp']
        repeated=c.post('/api/combat/turn',headers=auth(pid),
                        json={'action':'pet','zone':'body'})
        assert repeated.status_code==400
        with SessionLocal() as db:
            assert db.get(Player,pid).stamina==before['stamina']-3


def test_pet_xp_caps_at_level_ten_and_wolf_changes_real_damage():
    pid=99326003
    with TestClient(app) as c:
        c.post('/api/class',headers=auth(pid),json={'key':'soldier'})
        with SessionLocal.begin() as db:
            p=db.get(Player,pid)
            original=attack_power(db,p)
            p.stats={**p.stats,'_pet':{'key':'wolf','level':1,'xp':0}}
            assert attack_power(db,p)>original
            for _ in range(5):pet_victory(p)
            assert pet_status(p)['level']==2
            p.stats={**p.stats,'_pet':{'key':'wolf','level':10,'xp':0}}
            pet_victory(p)
            assert pet_status(p)['level']==10


def test_finding_companion_never_replaces_existing_one():
    pid=99326004
    with TestClient(app) as c:
        c.post('/api/class',headers=auth(pid),json={'key':'thief'})
        with SessionLocal.begin() as db:
            p=db.get(Player,pid)
            with patch('game.random.random',return_value=.001),patch('game.random.choice',return_value='cat'):
                assert pet_try_find(p)=='cat'
                assert pet_try_find(p) is None
            assert pet_status(p)['key']=='cat'
