"""Reproducible gross PvE reward sampling; reads game rules, never opens a DB.

This models victorious encounters only. It deliberately excludes fight survival,
travel, stamina recovery, taxes, market prices and first-discovery rewards, so
the output is a diagnostic of reward rates rather than an economy forecast.
"""
import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from game import CLASSES, ENEMIES, LOCATIONS, choose_elite_modifier, choose_enemy, xp_needed
from gear import roll_rarity


def sample(zone: str, hero_class: str, paid: bool, count: int, seed: int):
    rng = random.Random(seed)
    threat = LOCATIONS[zone]['threat']
    xp_sum = caps_sum = loot_count = gear_count = elite_count = 0
    rarities = Counter()
    species = Counter()
    for _ in range(count):
        enemy_key = choose_enemy(threat, rng)
        enemy = ENEMIES[enemy_key]
        species[enemy_key] += 1
        elite = choose_elite_modifier(threat, rng)
        elite_count += bool(elite)
        hp = max(15, int((30 + threat * 18 + rng.randint(0, 20)) * enemy['hp']))
        damage = max(2, int((3 + threat * 3) * enemy['damage']))
        if elite:
            hp = max(1, round(hp * 1.35))
            damage = max(2, round(damage * 1.12))
        xp = int((35 + hp * .3) * enemy['reward'] * rng.uniform(.85, 1.15))
        caps = int((rng.randint(9, 32) + damage) * enemy['reward'])
        if elite:
            xp = round(xp * 1.35)
            caps = round(caps * 1.35)
        # VIP and XP boost reproduce gain_xp ordering; no paid loot boost is
        # assumed because it is a separately purchased consumable.
        if paid:
            xp = int(xp * 1.2) * 2
        xp_sum += xp
        caps_sum += caps
        loot_count += rng.random() < min(.98, .44 * CLASSES[hero_class]['loot'])
        if rng.random() < min(.30, .055 + .023 * threat + (.10 if elite else 0)):
            gear_count += 1
            rarities[roll_rarity(threat, 'uncommon' if elite else 'common', rng)] += 1
    return {
        'zone': zone, 'class': hero_class, 'vip_xp_boost': paid, 'wins': count,
        'xp_per_win': round(xp_sum / count, 2), 'caps_per_win': round(caps_sum / count, 2),
        'material_drop_rate': round(loot_count / count, 4),
        'gear_drop_rate': round(gear_count / count, 4),
        'elite_rate': round(elite_count / count, 4),
        'gear_rarities': dict(sorted(rarities.items())),
        'enemy_mix': dict(sorted(species.items())),
        'gross_xp': xp_sum, 'gross_caps': caps_sum,
        'level_if_all_wins': level_from_xp(xp_sum, 1 if zone == 'forest' else 40),
    }


def level_from_xp(total: int, starting_level: int):
    level = starting_level
    while total >= xp_needed(level):
        total -= xp_needed(level)
        level += 1
    return level


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wins', type=int, default=25_000)
    parser.add_argument('--seed', type=int, default=20261012)
    args = parser.parse_args()
    if args.wins < 1 or args.wins > 1_000_000:
        parser.error('--wins must be 1..1000000')
    scenarios = [('forest', 'soldier', False), ('forest', 'thief', False),
                 ('wasteland', 'soldier', False), ('wasteland', 'soldier', True)]
    print(json.dumps({'assumptions': 'gross rewards on victories only; no costs/deaths/tax/markets/first discovery',
                      'seed': args.seed,
                      'scenarios': [sample(zone, hero, paid, args.wins, args.seed + index)
                                    for index, (zone, hero, paid) in enumerate(scenarios)]},
                     ensure_ascii=False, indent=2))
