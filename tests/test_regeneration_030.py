"""0.30: tick must preserve unspent time and hourly passive recovery."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from game import STAMINA_REGEN_PER_TICK, tick, max_hp
from models import Player


START=datetime(2026,10,13,12,0,tzinfo=timezone.utc)


def make_player():
    return Player(id=99330001,name='Tester',hero_class='soldier',
                  level=1,hp=40,stamina=100,skills=[],
                  stats={'strength':0,'agility':0,'endurance':0,
                         'accuracy':0,'regen':0,'luck':0},
                  last_tick=START)


def advance(player,delta):
    with patch('game.now',return_value=START+delta):
        tick(player)


def test_energy_preserves_leftover_seconds_over_frequent_requests():
    p=make_player()
    advance(p,timedelta(minutes=4,seconds=59))
    assert p.stamina==100 and p.last_tick==START
    advance(p,timedelta(minutes=5,seconds=1))
    assert p.stamina==100+STAMINA_REGEN_PER_TICK
    assert p.last_tick==START+timedelta(minutes=5)
    advance(p,timedelta(minutes=9,seconds=58))
    assert p.stamina==105 and p.last_tick==START+timedelta(minutes=5)
    advance(p,timedelta(minutes=10,seconds=3))
    assert p.stamina==110
    assert p.last_tick==START+timedelta(minutes=10)
    # Same instant is idempotent.
    advance(p,timedelta(minutes=10,seconds=3))
    assert p.stamina==110


def test_hourly_hp_regenerates_despite_twelve_five_minute_polls():
    p=make_player()
    assert p.hp==40
    for minute in range(5,65,5):
        advance(p,timedelta(minutes=minute))
    assert p.hp==41
    assert p.stamina==100+12*STAMINA_REGEN_PER_TICK
    assert p.stats['_hp_regen_at']==(START+timedelta(hours=1)).isoformat()
    advance(p,timedelta(minutes=119))
    assert p.hp==41
    advance(p,timedelta(hours=2,seconds=20))
    assert p.hp==42


def test_vip_expiry_credits_only_completed_intervals():
    p=make_player()
    p.vip_until=START+timedelta(minutes=7)
    advance(p,timedelta(minutes=15,seconds=5))
    # 5-min tick at 5:00 is doubled; 10:00 and 15:00 are normal.
    assert p.stamina==100+4*STAMINA_REGEN_PER_TICK
    advance(p,timedelta(minutes=20))
    assert p.stamina==100+5*STAMINA_REGEN_PER_TICK


def test_hp_and_energy_are_capped_after_long_offline_period():
    p=make_player()
    p.stamina=499
    p.hp=max_hp(p)-1
    advance(p,timedelta(days=3))
    assert p.stamina==500 and p.hp==max_hp(p)
    stamp=p.stats['_hp_regen_at']
    advance(p,timedelta(days=3))
    assert p.stats['_hp_regen_at']==stamp
    assert p.stamina==500


def test_migrated_player_can_have_existing_non_talent_stats_fields():
    p=make_player()
    p.stats={**p.stats,'_insurance_until':START.isoformat(),
             '_enemy_codex':{'walker':{'seen':1,'kills':1}}}
    advance(p,timedelta(hours=1,minutes=2))
    assert p.stats['_enemy_codex']['walker']['kills']==1
    assert '_insurance_until' in p.stats
    assert p.hp==41
