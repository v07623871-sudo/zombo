"""Combat bestiary integration, old battles and game-ready assets."""
from pathlib import Path
from tests.test_game import app,H
from fastapi.testclient import TestClient
from models import SessionLocal, Battle, Player
from game import ENEMIES, choose_enemy, enemy_info, spawn_battle, battle_view, combat_round
from unittest.mock import patch
from sqlalchemy import select


def test_all_ten_archetypes_have_safe_game_assets_and_balanced_zones():
    assert len(ENEMIES) == 10
    assert set(ENEMIES) == {'walker','crawler','runner','howler','spitter','stalker','armored','brute','toxic','reaper'}
    static = Path(__file__).resolve().parents[1] / 'static' / 'mobs'
    for key, mob in ENEMIES.items():
        assert (static/(key+'.svg')).is_file(),key
        source = (static/(key+'.svg')).read_text()
        assert '<svg' in source and '<script' not in source
        assert mob['tier'] >= mob['min_threat'] - 1
        assert mob['name'] and mob['skill'] and mob['lore']
    for _ in range(200):
        assert ENEMIES[choose_enemy(1)]['tier'] <= 2
        assert ENEMIES[choose_enemy(2)]['tier'] <= 3
        assert ENEMIES[choose_enemy(3)]['min_threat'] <= 3
        assert ENEMIES[choose_enemy(5)]['tier'] <= 5


def test_existing_battles_render_and_new_spawn_persists_archetype():
    assert enemy_info('zombie')[0] == 'walker'
    assert enemy_info('zombie:doesnotexist')[0] == 'walker'
    with TestClient(app) as client:
        cfg = client.get('/api/config')
        assert cfg.status_code == 200
        assert len(cfg.json()['enemies']) == 10
        for key in ENEMIES:
            response = client.get('/static/mobs/'+key+'.svg')
            assert response.status_code == 200
            assert response.headers['content-type'].startswith('image/svg+xml')
        client.post('/api/class',json={'key':'soldier'},headers={'Authorization':'demo:42042'})
        with SessionLocal.begin() as db:
            p = db.get(Player,42042)
            p.location = 'factory';p.level=19;p.stamina=500;p.hp=125
        with patch('game.choose_enemy',return_value='armored'):
            fight = client.post('/api/combat/start',headers={'Authorization':'demo:42042'})
        assert fight.status_code == 200, fight.text
        battle = fight.json()['battle']
        assert battle['enemy_id']=='armored'
        assert battle['trait']=='armor'
        assert battle['tier']==4
        assert battle['skill'] == ENEMIES['armored']['skill']
        with SessionLocal.begin() as db:
            b = db.scalar(select(Battle).where(Battle.player_id == 42042))
            assert b.kind == 'zombie:armored'
            b.kind = 'zombie'
            assert battle_view(b)['enemy_id']=='walker'


def test_new_enemy_fight_turn_and_rewards():
    with TestClient(app) as client:
        user={'Authorization':'demo:42043'}
        assert client.post('/api/class',json={'key':'assassin'},headers=user).status_code==200
        with SessionLocal.begin() as db:
            p=db.get(Player,42043)
            p.location='wasteland';p.level=55;p.hp=650;p.stamina=500
            p.stats={'strength':13,'agility':9,'endurance':100,'accuracy':9,'regen':0,'luck':0,'_talent_v2':1}
        with patch('game.choose_enemy',return_value='reaper'):
            spawned=client.post('/api/combat/start',headers=user)
        assert spawned.status_code==200,spawned.text
        assert spawned.json()['battle']['enemy_id']=='reaper'
        for _ in range(20):
            result=client.post('/api/combat/turn',headers=user,json={'action':'attack','zone':'body'})
            assert result.status_code==200,result.text
            if result.json()['finished']:
                assert 'message' in result.json()
                break
        else:raise AssertionError('Fight took too long')