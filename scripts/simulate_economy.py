"""Reproducible *net* ZOMBO PvE cycle model, not a prediction of real users.

Uses live enemy pools, level thresholds, rewards and item recipes. A simple
body-attack strategy approximates combat without opening the production DB.
Costs, death, stamina, 1% tax carry, daily and once-only quest rewards and
scavenge loot are included; paid boosters and markets are excluded by default.
"""
import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from game import CLASSES, ENEMIES, LOCATIONS, RECIPES, QUESTS, choose_enemy, choose_elite_modifier, xp_needed, SHOP_PRICES, STAMINA_REGEN_PER_TICK, scavenge_pool

DAYS_MAX=90
RUNS_MAX=2000
DAILY_STAMINA_REGEN=24*60//5*STAMINA_REGEN_PER_TICK
ZONES=('forest','city','factory','hospital','wasteland')
BASIC_WEAPONS={'forest':7,'city':14,'factory':14,'hospital':25,'wasteland':25}

def award_xp(state, amount):
    state['xp']+=max(0,int(amount))
    while state['xp']>=xp_needed(state['level']):
        state['xp']-=xp_needed(state['level'])
        state['level']+=1
        state['level_ups']+=1
        state['hp']=max_hp(state)

def max_hp(state):
    return CLASSES[state['class']]['hp']+(state['level']-1)*3

def scavenge(state,rng,zone):
    if state['stamina']<5:return False
    state['stamina']-=5
    state['scavenges']+=1
    choices=scavenge_pool(zone)
    material=rng.choice(choices)
    qty=rng.randint(1,3)
    if material=='medkit':state['medkits']+=qty
    else:state['materials'][material]+=qty
    state['loot_items']+=qty
    state['hunger']+=2
    state['thirst']+=3
    if state['scavenges']==QUESTS['scavenge']['target']:
        reward=QUESTS['scavenge']['reward']
        state['caps']+=reward['caps'];state['quest_caps']+=reward['caps']
        award_xp(state,reward['xp'])
    if rng.random()<.14:
        # Server scavenge creates a battle at +2 stamina. Return to action
        # loop and account for real attack costs and health below.
        return 'ambush'
    award_xp(state,12)
    return True

def heal_if_needed(state):
    if state['hp']>=max_hp(state)*.6:return
    if state['medkits']<=0:
        recipe=RECIPES['medkit']['cost']
        if all(state['materials'][k]>=v for k,v in recipe.items()):
            for k,v in recipe.items():state['materials'][k]-=v
            state['medkits']+=1;state['crafted_medkits']+=1
    if state['medkits']<=0 and state['caps']>=SHOP_PRICES['medkit']:
        # A real player can buy medicine instead of taking endless deaths.
        state['caps']-=SHOP_PRICES['medkit']
        state['merchant_spend']+=SHOP_PRICES['medkit']
        state['medkits_bought']+=1
        state['medkits']+=1
    if state['medkits']>0:
        state['medkits']-=1;state['medkits_used']+=1
        healed=int(45*CLASSES[state['class']]['healing'])
        state['hp']=min(max_hp(state),state['hp']+healed)

def battle(state,rng,zone,*,ambush=False,taxed=True):
    if state['stamina']<2:return False
    state['stamina']-=2
    threat=LOCATIONS[zone]['threat']
    key=choose_enemy(threat,rng)
    enemy=ENEMIES[key]
    elite=choose_elite_modifier(threat,rng)
    enemy_hp=max(15,int((30+threat*18+rng.randint(0,20))*enemy['hp']))
    enemy_damage=max(2,int((3+threat*3)*enemy['damage']))
    if elite:
        enemy_hp=max(1,round(enemy_hp*1.35))
        enemy_damage=max(2,round(enemy_damage*1.12))
        state['elite_fights']+=1
    starting_hp=enemy_hp
    state['battles']+=1
    max_turns=50
    for turn in range(max_turns):
        heal_if_needed(state)
        if state['stamina']<2:
            state['fled_energy']+=1
            return False
        state['stamina']-=2
        weapon=BASIC_WEAPONS[zone]
        attack=max(1,int((7+state['level']*2+weapon)*CLASSES[state['class']]['power']))
        damage=max(1,int(attack*rng.uniform(.8,1.2)))
        if rng.random()>.94:damage=0
        elif rng.random()<CLASSES[state['class']]['crit']:damage*=2
        armor=min(.55,enemy['armor']+(.22 if elite=='armor' else 0))
        damage=max(1,round(damage*(1-armor))) if damage else 0
        enemy_hp=max(0,enemy_hp-damage)
        if enemy_hp<=0:
            state['wins']+=1
            xp=int((35+starting_hp*.3)*enemy['reward']*rng.uniform(.85,1.15))
            caps=int((rng.randint(9,32)+enemy_damage)*enemy['reward'])
            if elite:xp=round(xp*1.35);caps=round(caps*1.35)
            if key not in state['discovered']:
                state['discovered'].add(key);xp+=25;caps+=15
            state['gross_caps']+=caps
            if taxed:
                total=state['tax_carry']+caps
                tax,state['tax_carry']=divmod(total,100)
                state['tax_paid']+=tax
            else:tax=0
            state['caps']+=caps-tax
            award_xp(state,xp)
            if rng.random()<min(.98,.44*CLASSES[state['class']]['loot']):
                material=rng.choice(['wood','cloth','metal','food','water','medkit','wire'])
                if material=='medkit':state['medkits']+=1
                else:state['materials'][material]+=1
                state['loot_items']+=1
            if rng.random()<min(.30,.055+.023*threat+(.10 if elite else 0)):
                state['gear_drops']+=1
            if state['wins']==QUESTS['kills']['target']:
                reward=QUESTS['kills']['reward']
                state['caps']+=reward['caps'];state['quest_caps']+=reward['caps']
                award_xp(state,reward['xp'])
            return True
        raw=max(1,enemy_damage+rng.randint(-3,5))
        special=(turn+1)%3==0
        if special and enemy['trait'] in ('frenzy','acid','smash','howl','ambush'):
            raw=max(1,round(raw*{'frenzy':1.45,'acid':1.28,'smash':1.60,
                                  'howl':1.20,'ambush':1.36}[enemy['trait']]))
        if elite=='frenzy':raw=max(1,round(raw*1.18))
        # Mirror baseline class perks: thief dodge, assassin mitigation,
        # medic combat healing. Talent/equipment builds are excluded.
        if state['class']=='medic':
            state['hp']=min(max_hp(state),state['hp']+max(1,round(max_hp(state)*.05)))
        if rng.random()>=CLASSES[state['class']].get('dodge',0):
            raw=max(1,round(raw*(1-CLASSES[state['class']].get('mitigation',0))))
            state['hp']=max(0,state['hp']-raw)
        if special and enemy['trait'] in ('acid','howl'):
            state['stamina']=max(0,state['stamina']-(6 if enemy['trait']=='acid' else 4))
        if special and elite=='venom':
            state['stamina']=max(0,state['stamina']-8)
        if elite=='regen':enemy_hp=min(starting_hp,enemy_hp+max(1,round(starting_hp*.06)))
        if state['hp']==0:
            state['deaths']+=1
            lost=min(state['caps'],int(state['caps']*.2))
            state['caps']-=lost;state['death_losses']+=lost
            state['xp']=int(state['xp']*.7)
            # Uninsured deaths also remove 50% of unequipped, stackable supplies.
            all_supply=sum(state['materials'].values())+state['medkits']
            to_lose=int(all_supply*.5)
            for key in sorted(state['materials']):
                removed=min(state['materials'][key],to_lose)
                state['materials'][key]-=removed
                to_lose-=removed
            if to_lose:
                state['medkits']-=min(state['medkits'],to_lose)
            state['hp']=max(1,max_hp(state)//2)
            # Death returns to base and short cooldown; travel is not priced.
            return False
    state['fled_turn_limit']+=1
    return False

def simulate(zone,hero_class,days,actions,seed,taxed=True):
    if zone not in ZONES or hero_class not in CLASSES:
        raise ValueError('Unrecognised zone or class')
    rng=random.Random(seed)
    state={'class':hero_class,'level':LOCATIONS[zone]['min_level'],'xp':0,'level_ups':0,
           'caps':150,'gross_caps':0,'quest_caps':0,'death_losses':0,'merchant_spend':0,'medkits_bought':0,'tax_paid':0,
           'tax_carry':0,'stamina':200,'hp':0,'wins':0,'battles':0,'deaths':0,
           'scavenges':0,'medkits':2,'medkits_used':0,'crafted_medkits':0,
           'gear_drops':0,'loot_items':0,'elite_fights':0,'fled_energy':0,
           'fled_turn_limit':0,'discovered':set(),'materials':Counter({'wood':3}),
           'hunger':0,'thirst':0}
    state['hp']=max_hp(state)
    energy_waste=0
    for day in range(days):
        if day:
            # Regen in game.tick: STAMINA_REGEN_PER_TICK energy per 5 min. The 500
            # stamina cap discards overflow after an inactive day.
            before=state['stamina']
            state['stamina']=min(500,state['stamina']+DAILY_STAMINA_REGEN)
            energy_waste+=before+DAILY_STAMINA_REGEN-state['stamina']
            state['hp']=min(max_hp(state),state['hp']+24)
        state['caps']+=75
        state['stamina']=min(500,state['stamina']+80)
        state['materials']['food']+=1
        state['materials']['water']+=1
        award_xp(state,45)
        for _ in range(actions):
            if state['stamina']<7:break
            if rng.random()<.42:
                result=scavenge(state,rng,zone)
                if result=='ambush':battle(state,rng,zone,ambush=True,taxed=taxed)
            else:battle(state,rng,zone,taxed=taxed)
    return {'zone':zone,'class':hero_class,'days':days,'actions_per_day':actions,
            'initial_level':LOCATIONS[zone]['min_level'],'final_level':state['level'],
            'level_ups':state['level_ups'],
            'initial_caps':150,'final_caps':state['caps'],
            'net_caps':state['caps']-150,
            'gross_combat_caps':state['gross_caps'],'daily_caps':75*days,
            'quest_caps':state['quest_caps'],'territory_tax':state['tax_paid'],
            'death_losses':state['death_losses'],'merchant_spend':state['merchant_spend'],
             'medkits_bought':state['medkits_bought'],
            'fights':state['battles'],'wins':state['wins'],
            'deaths':state['deaths'],'scavenges':state['scavenges'],
            'medkits_used':state['medkits_used'],'medkits_crafted':state['crafted_medkits'],
            'medkits_left':state['medkits'],'materials_left':sum(state['materials'].values()),
            'loot_items':state['loot_items'],'gear_drops':state['gear_drops'],
            'elite_fights':state['elite_fights'],'stamina_unused':state['stamina'],
            'stamina_lost_to_cap':energy_waste,
            'incomplete_energy_fights':state['fled_energy']}

def aggregate(zone,hero_class,days,actions,runs,seed,taxed=True):
    results=[simulate(zone,hero_class,days,actions,seed+i*104729,taxed) for i in range(runs)]
    fields=('final_level','net_caps','gross_combat_caps','territory_tax','merchant_spend','medkits_bought',
            'death_losses','quest_caps','fights','wins','deaths','scavenges',
            'medkits_used','medkits_crafted','medkits_left','materials_left',
            'gear_drops','elite_fights','stamina_lost_to_cap')
    output={key+'_avg':round(sum(x[key] for x in results)/runs,2) for key in fields}
    output.update({'zone':zone,'class':hero_class,'days':days,
                   'actions_per_day':actions,'runs':runs,
                   'net_caps_min':min(x['net_caps'] for x in results),
                   'net_caps_max':max(x['net_caps'] for x in results),
                   'death_rate_per_fight':round(
                       sum(x['deaths'] for x in results)/max(1,sum(x['fights'] for x in results)),4)})
    return output

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs',type=int,default=60)
    parser.add_argument('--days',type=int,default=14)
    parser.add_argument('--actions',type=int,default=16)
    parser.add_argument('--seed',type=int,default=20261012)
    args=parser.parse_args(argv)
    if not 1<=args.runs<=RUNS_MAX:parser.error('--runs must be 1..2000')
    if not 1<=args.days<=DAYS_MAX:parser.error('--days must be 1..90')
    if not 1<=args.actions<=100:parser.error('--actions must be 1..100')
    scenarios=[('forest','soldier'),('forest','medic'),('forest','thief'),
               ('city','soldier'),('factory','soldier'),('wasteland','assassin')]
    return {'assumptions':{
        'nature':'Scenario model, NOT a live gameplay transcript or final balancing verdict.',
        'starting_gear':'Zone-appropriate common weapon; no talent bonuses or premium boosters.',
        'schedule':'Daily visit, +75 caps/+80 energy/+45 XP, regeneration between days, fixed actions/day.',
        'encounters':'42% scavenging, 58% combat, 14% scavenging ambushes, common body attacks.',
        'money':'Includes once-only quests, loss of caps/supplies on death, 1% territory tax, crafted and store-bought medkits.',
        'excluded':'Actual marketplace, rare gear effects, enemy AI other than named traits, PvP, additional world events, boss, hunger/thirst penalties, healing animations, card-selection time.'
    },'seed':args.seed,'scenarios':[
        aggregate(zone,hero,args.days,args.actions,args.runs,args.seed+i*100003)
        for i,(zone,hero) in enumerate(scenarios)]}

if __name__=='__main__':
    print(json.dumps(main(),ensure_ascii=False,indent=2))
