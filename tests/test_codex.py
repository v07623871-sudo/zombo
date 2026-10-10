"""Behavioural tests for permanent enemy discovery and tactical warnings."""
from unittest.mock import patch
from fastapi.testclient import TestClient
from tests.test_game import app
from models import SessionLocal, Player, Battle
from game import ENEMY_TACTICS, ENEMIES, record_enemy, battle_view
from sqlalchemy import select


def test_codex_records_sightings_and_rewards_only_once():
    with TestClient(app) as client:
        user={'Authorization':'demo:45001'}
        assert client.post('/api/class',json={'key':'assassin'},headers=user).status_code==200
        with SessionLocal.begin() as db:
            p=db.get(Player,45001)
            p.location='wasteland';p.level=50;p.hp=800;p.stamina=500
            p.stats={**p.stats,'strength':200,'endurance':200}
        with patch('game.choose_enemy',return_value='walker'):
            fight=client.post('/api/combat/start',headers=user)
        assert fight.status_code==200,fight.text
        assert fight.json()['battle']['enemy_id']=='walker'
        assert client.get('/api/me',headers=user).json()['enemy_codex']['walker']=={'seen':1}
        with patch('game.random.random',return_value=0):
            r=client.post('/api/combat/turn',json={'action':'attack','zone':'body'},headers=user)
        assert r.status_code==200,r.text
        assert r.json()['new_species'] is True
        assert 'Новый вид в бестиарии' in r.json()['message']
        state=client.get('/api/me',headers=user).json()
        assert state['enemy_codex']['walker']=={'seen':1,'kills':1}
        with patch('game.choose_enemy',return_value='walker'):
            assert client.post('/api/combat/start',headers=user).status_code==200
        with patch('game.random.random',return_value=0):
            r2=client.post('/api/combat/turn',json={'action':'attack','zone':'body'},headers=user)
        assert r2.status_code==200,r2.text
        assert r2.json()['new_species'] is False
        assert client.get('/api/me',headers=user).json()['enemy_codex']['walker']['kills']==2


def test_special_attack_forecast_and_defending_prevents_energy_drain():
    with TestClient(app) as client:
        user={'Authorization':'demo:45002'}
        assert client.post('/api/class',json={'key':'soldier'},headers=user).status_code==200
        with SessionLocal.begin() as db:
            p=db.get(Player,45002)
            p.hp=350;p.stamina=150;p.stats={**p.stats,'endurance':100}
            db.add(Battle(player_id=p.id,kind='zombie:howler',enemy='Крикун',enemy_hp=1000,enemy_max_hp=1000,enemy_damage=14,turn=2,log=[]))
        first=client.get('/api/me',headers=user).json()['battle']
        assert first['incoming_special'] is True
        assert first['tactics']==ENEMY_TACTICS['howler']
        with patch('game.random.random',return_value=0.999),patch('game.random.randint',return_value=0):
            r=client.post('/api/combat/turn',headers=user,json={'action':'defend'})
        assert r.status_code==200,r.text
        assert r.json()['finished'] is False
        after=client.get('/api/me',headers=user).json()
        assert after['stamina']==150
        assert after['battle']['incoming_special'] is False
        assert 'Успешный блок' in after['battle']['log'][-2]


def test_codex_ignores_unknown_species():
    from types import SimpleNamespace
    p=SimpleNamespace(stats={})
    assert record_enemy(p,'untrusted-id',True) is False
    assert p.stats=={}
    assert set(ENEMY_TACTICS)==set(ENEMIES)