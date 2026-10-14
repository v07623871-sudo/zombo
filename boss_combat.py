"""Actual world-boss retaliation, phases and unique attacks.

The shared boss is locked by the caller. The per-player turn counter lives in
Player.stats; no new tables, scheduler or volatile in-memory state is needed.
"""
import random
from datetime import timedelta

from sqlalchemy import select

from models import Battle, ItemStack, now
from game import (CLASSES, WORLD_BOSS_ROTATION, aware, death_penalty, max_hp,
                  talent_bonus, pet_bonus)


def boss_profile(boss):
    return next((x for x in WORLD_BOSS_ROTATION if x['name']==boss.name),
                WORLD_BOSS_ROTATION[0])


def combat_phase(boss):
    if not boss.max_hp:
        return 'Обычная'
    ratio=boss.hp / boss.max_hp
    if ratio<=.20:return 'Ярость'
    if ratio<=.50:return 'Опасная'
    return 'Обычная'


def current_turn(p, cycle):
    record=(p.stats or {}).get('_boss_combat')
    if isinstance(record,dict) and record.get('cycle')==cycle:
        return max(0,min(100_000,int(record.get('turns',0))))
    return 0


def next_turn(p, cycle):
    turn=current_turn(p,cycle)+1
    p.stats={**(p.stats or {}),'_boss_combat':{'cycle':cycle,'turns':turn}}
    return turn


def boss_counterattack(db,p,boss,turn,*,rng=None):
    """One deterministic-under-seed retaliation; caller owns the transaction.

    The third player hit is a boss-specific special. All effects use the live
    health/stamina/food/water and equipment statistics, not a display-only roll.
    """
    rng=rng or random
    profile=boss_profile(boss)
    phase=combat_phase(boss)
    special=turn%3==0
    kind=profile['attack_kind']
    # Early characters can participate; late bosses are harder but don't
    # one-shot players solely due to their level.
    base=profile['attack_damage']+min(100,max(0,p.level-1))*.16
    raw=max(1,round(base+rng.randint(-2,2)))
    if phase=='Опасная':raw=round(raw*1.20)
    elif phase=='Ярость':raw=round(raw*1.45)
    if special:
        raw=round(raw*({'smash':1.65,'swarm':1.20,'venom':1.25,
                         'radiation':1.35,'execute':1.45}[kind]))
    if kind=='execute' and p.hp<=max_hp(p)//2:
        raw=round(raw*1.35)
    if p.hero_class=='medic':
        p.hp=min(max_hp(p),p.hp+max(1,round(max_hp(p)*.05)))

    from gear import gear_stats
    defense=gear_stats(db,p.id)['defense']
    old_vest=db.scalar(select(ItemStack).where(
        ItemStack.player_id==p.id,ItemStack.equipped.is_(True),
        ItemStack.item_key=='vest'))
    if old_vest:defense+=4
    evade=min(.65,CLASSES[p.hero_class].get('dodge',0)
              +max(0,p.stats.get('agility',0))*.005
              +talent_bonus(p,'dodge')+pet_bonus(p,'dodge'))
    missed=rng.random()<evade
    reduction=min(.70,CLASSES[p.hero_class].get('mitigation',0)
                  +talent_bonus(p,'mitigation')+talent_bonus(p,'armor')
                  +pet_bonus(p,'mitigation'))
    taken=0 if missed else max(1,round(max(1,raw-defense)*(1-reduction)))
    p.hp=max(0,p.hp-taken)
    if taken:
        from gear import wear_equipped
        wear_equipped(db,p.id,'armor',1)

    drained=0
    if special and not missed:
        if kind=='swarm':
            drained=min(p.stamina,4)
        elif kind=='venom':
            drained=min(p.stamina,8)
            p.thirst=min(100,p.thirst+4)
        elif kind=='radiation':
            drained=min(p.stamina,10)
            p.thirst=min(100,p.thirst+10)
            p.hunger=min(100,p.hunger+5)
        p.stamina-=drained
    if missed:
        message=f'{boss.name} атакует, но ты уклоняешься!'
    else:
        message=(f'{boss.name}: {profile["attack_name"]}'
                 +(' · ОСОБАЯ АТАКА!' if special else '')
                 +f' · −{taken} HP'
                 +(f', −{drained} энергии' if drained else ''))
    lost=None
    if p.hp==0:
        lost=death_penalty(db,p)
        p.hp=max(1,max_hp(p)//2)
        p.location='base'
        p.cooldown=now()+timedelta(seconds=30)
        message+=' · Ты повержена! Возвращение в убежище. '
        message+=f'Потеряно {lost["caps"]} крышек, {lost["xp"]} XP и {lost["items"]} предметов.'
        if lost['insured']:message+=' Страховка сработала.'
    return {'message':message,'damage_received':taken,'stamina_drained':drained,
            'dodged':missed,'special':special,'phase':phase,'defeated':lost is not None,
            'losses':lost}
