"""Elite fights keep one server roll and pay the reward at most once."""
import random
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.test_game import app
from game import (ELITE_MODIFIERS, battle_view, choose_elite_modifier,
                  combat_round, elite_modifier)
from models import Battle, Player, SessionLocal


def headers(pid):
    return {'Authorization': f'demo:{pid}'}


def create_hero(client, pid):
    response = client.post('/api/class', headers=headers(pid), json={'key':'soldier'})
    assert response.status_code == 200, response.text
    with SessionLocal.begin() as db:
        p = db.get(Player, pid)
        p.location = 'factory'
        p.level = 30
        p.hp = 500
        p.stamina = 500


def test_elite_roll_is_rare_and_absent_in_starting_zone():
    rng = random.Random(1357)
    assert all(choose_elite_modifier(1, rng) is None for _ in range(500))
    outcomes = [choose_elite_modifier(5, rng) for _ in range(10000)]
    assert 500 < sum(x is not None for x in outcomes) < 1100
    assert set(outcomes) - {None} == set(ELITE_MODIFIERS)


def test_elite_spawn_persists_and_marker_survives_long_fight():
    pid = 42101
    with TestClient(app) as client:
        create_hero(client, pid)
        with patch('game.choose_enemy', return_value='walker'), patch(
                'game.choose_elite_modifier', return_value='armor'):
            spawned = client.post('/api/combat/start', headers=headers(pid))
        assert spawned.status_code == 200, spawned.text
        battle = spawned.json()['battle']
        assert battle['enemy_id'] == 'walker' and battle['elite']['key'] == 'armor'
        assert all(not line.startswith('!elite:') for line in battle['log'])
        assert client.get('/api/me', headers=headers(pid)).json()['battle']['elite']['key'] == 'armor'
        with SessionLocal.begin() as db:
            p = db.get(Player, pid)
            b = db.scalar(select(Battle).where(Battle.player_id == pid))
            assert elite_modifier(b) == 'armor'
            for _ in range(12):
                result = combat_round(db, p, b, 'defend')
                assert not result['finished']
            assert b.turn == 12 and elite_modifier(b) == 'armor'
            assert battle_view(b)['elite']['key'] == 'armor'


def test_four_modifiers_change_real_combat():
    ids = [42111, 42112, 42113, 42114, 42115, 42116]
    with TestClient(app) as client:
        for pid in ids:
            create_hero(client, pid)
        with SessionLocal.begin() as db:
            for pid, modifier in zip(ids, [None, 'armor', 'frenzy', 'venom', 'regen', 'venom']):
                db.add(Battle(player_id=pid, kind='zombie:walker', enemy='Шатун',
                              enemy_hp=200 if modifier == 'regen' else 300,
                              enemy_max_hp=300, enemy_damage=20,
                              turn=2 if modifier == 'venom' else 0,
                              log=[f'!elite:{modifier}'] if modifier else []))
            db.flush()
            with patch('game.attack_power', return_value=40), patch(
                    'game.random.uniform', return_value=1), patch(
                    'game.random.random', return_value=.5), patch(
                    'game.random.randint', return_value=0):
                outputs = {}
                for pid in ids:
                    p = db.get(Player, pid)
                    b = db.scalar(select(Battle).where(Battle.player_id == pid))
                    if pid == 42116:
                        assert battle_view(b)['elite_warning'] == 'Ядовитый укус'
                    before_hp, before_stamina = p.hp, p.stamina
                    result = combat_round(db, p, b, 'defend' if pid == 42116 else 'attack')
                    assert not result['finished']
                    outputs[pid] = (b.enemy_hp, before_hp - p.hp,
                                    before_stamina - p.stamina)
            assert outputs[42112][0] > outputs[42111][0]  # Armor resisted.
            assert outputs[42113][1] > outputs[42111][1]  # Frenzy hit harder.
            assert outputs[42114][2] >= outputs[42111][2] + 8  # Poison drain.
            assert outputs[42115][0] > 200 - 40  # Regeneration after hit.
            assert outputs[42116][2] == 0  # Defending prevents poison.


def test_elite_kill_claims_once_and_old_battle_stays_normal():
    pid = 42121
    with TestClient(app) as client:
        create_hero(client, pid)
        with patch('game.choose_enemy', return_value='walker'), patch(
                'game.choose_elite_modifier', return_value='regen'):
            assert client.post('/api/combat/start', headers=headers(pid)).status_code == 200
        with SessionLocal.begin() as db:
            db.scalar(select(Battle).where(Battle.player_id == pid)).enemy_hp = 1
        with patch('game.random.random', return_value=.5), patch(
                'game.random.uniform', return_value=1):
            won = client.post('/api/combat/turn', headers=headers(pid),
                              json={'action':'attack','zone':'body'})
        assert won.status_code == 200, won.text
        assert won.json()['finished'] and won.json()['won'] and won.json()['elite'] == 'regen'
        assert client.post('/api/combat/turn', headers=headers(pid),
                           json={'action':'attack','zone':'body'}).status_code == 400
        with SessionLocal() as db:
            assert db.get(Player, pid).kills == 1
            assert db.scalar(select(Battle).where(Battle.player_id == pid)) is None
        legacy = Battle(kind='zombie', enemy='Шатун', enemy_hp=10, enemy_max_hp=10,
                        enemy_damage=2, log=['Старый бой'])
        assert battle_view(legacy)['elite'] is None


def test_elite_player_death_never_pays_victory_reward():
    pid = 42131
    with TestClient(app) as client:
        create_hero(client, pid)
        with SessionLocal.begin() as db:
            p = db.get(Player, pid)
            p.hp = 1
            p.caps = 100
            db.add(Battle(player_id=pid, kind='zombie:walker', enemy='Элитный Шатун',
                          enemy_hp=100, enemy_max_hp=100, enemy_damage=100,
                          log=['!elite:frenzy']))
        with SessionLocal.begin() as db, patch('game.random.random', return_value=.5), patch(
                'game.random.randint', return_value=0):
            p = db.get(Player, pid)
            b = db.scalar(select(Battle).where(Battle.player_id == pid))
            result = combat_round(db, p, b, 'defend')
            assert result['finished'] and not result['won']
        with SessionLocal() as db:
            p = db.get(Player, pid)
            assert p.kills == 0 and p.caps == 80 and p.cooldown is not None
            assert db.scalar(select(Battle).where(Battle.player_id == pid)) is None
