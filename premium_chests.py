"""Premium loot chest and seven-case prices.

All randomized rewards are disclosed as weighted odds before purchase. Premium
currency is earned through Telegram Stars top-ups and spent transactionally.
No premium chest or case is sourced from combat, crafting or caps purchases.
Legacy case items already owned remain usable, without confiscation.
"""
GEM_CASE_PRICES = {
    'scrap_case':40, 'field_case':55, 'hunter_case':90,
    'military_case':135, 'assault_case':200, 'relic_case':275,
    'shadow_case':360,
}

CHESTS = {
    'chest_common': {
        'name':'Обычный сундук','icon':'📦','price':50,'drops':3,
        'description':'1 коллекционная пушка + 2 запаса. 60% обычная, 35% необычная, 5% редкая.',
        'cases':{'scrap_case':65,'field_case':35},
        'rarity_weights':{'common':60,'uncommon':35,'rare':5},
        'supplies':[
            [('metal',3),('cloth',4),('wire',2),('rubber',2),('wood',5)],
            [('bandage',2),('medkit',1),('energy_bar',2),('water_filter',1),('field_dressing',3)],
        ],
    },
    'chest_rare':{
        'name':'Редкий сундук','icon':'🎁','price':150,'drops':4,
        'description':'1 гарантированно редкая или эпическая пушка + 3 полезных набора. 75% редкая, 25% эпическая.',
        'cases':{'hunter_case':55,'military_case':45},
        'rarity_weights':{'rare':75,'epic':25},
        'supplies':[
            [('medkit',3),('trauma_kit',1),('combat_meds',2),('adrenaline',1)],
            [('metal',8),('wire',7),('rubber',6),('cloth',9),('wood',11)],
            [('rare',1),('energy_cells',2),('isotonic',3),('military_ration',2)],
        ],
    },
    'chest_legendary':{
        'name':'Легендарный сундук','icon':'🏆','price':500,'drops':5,
        'description':'1 гарантированная эпическая+ пушка + 4 ценных набора. 30% легендарная.',
        'cases':{'relic_case':60,'shadow_case':40},
        'rarity_weights':{'epic':70,'legendary':30},
        'supplies':[
            [('rare',4),('rare',5),('rare',6)],
            [('combat_meds',3),('trauma_kit',3),('medkit',8)],
            [('metal',20),('wire',16),('rubber',15),('cloth',24)],
            [('energy_cells',4),('adrenaline',3),('stimulant',4),('military_ration',6)],
        ],
    }
}

EXTRA_SUPPLIES = {
    'field_dressing':{
        'name':'Походная повязка','icon':'🩹','type':'consumable',
        'desc':'Восстанавливает 18 HP','effect':{'hp':18},
        'recipe':{'qty':2,'cost':{'cloth':3,'wood':1}},'caps':32,
    },
    'painkillers':{
        'name':'Обезболивающее','icon':'💊','type':'consumable',
        'desc':'Восстанавливает 35 HP','effect':{'hp':35},
        'recipe':{'qty':1,'cost':{'cloth':2,'water':1}},'caps':48,
    },
    'energy_bar':{
        'name':'Энергобатончик','icon':'🍫','type':'consumable',
        'desc':'Голод −35, энергия +15','effect':{'hunger':35,'stamina':15},
        'recipe':{'qty':2,'cost':{'food':2,'cloth':1}},'caps':45,
    },
    'isotonic':{
        'name':'Изотоник','icon':'🧃','type':'consumable',
        'desc':'Жажда −55, энергия +20','effect':{'thirst':55,'stamina':20},
        'recipe':{'qty':1,'cost':{'water':2,'food':1}},'caps':65,
    },
    'combat_meds':{
        'name':'Боевые медикаменты','icon':'🧪','type':'consumable',
        'desc':'Восстанавливает 75 HP и 10 энергии','effect':{'hp':75,'stamina':10},
        'recipe':{'qty':1,'cost':{'cloth':5,'water':2,'rubber':1,'rare':1}},
    },
    'purified_water':{
        'name':'Стерильная вода','icon':'💦','type':'consumable',
        'desc':'Жажда −90','effect':{'thirst':90},
        'recipe':{'qty':2,'cost':{'water':3,'cloth':1}},'caps':40,
    },
    'energy_cells':{
        'name':'Энергоячейка','icon':'🔋','type':'consumable',
        'desc':'Восстанавливает 65 энергии','effect':{'stamina':65},
        'recipe':{'qty':1,'cost':{'wire':4,'rubber':2,'metal':3}},
    },
    'military_ration':{
        'name':'Армейский паёк','icon':'🍱','type':'consumable',
        'desc':'Голод −70, жажда −30','effect':{'hunger':70,'thirst':30},
        'recipe':{'qty':1,'cost':{'food':3,'water':1,'cloth':2}},
    },
}


def chest_catalog():
    return [{
        'key':key, 'name':meta['name'],'icon':meta['icon'],
        'price':meta['price'],'drops':meta['drops'],
        'desc':meta['description'],'rarity_weights':meta['rarity_weights'],
        'case_weights':meta['cases'],
        'guarantee':'Одна коллекционная пушка + предметы для выживания',
    } for key,meta in CHESTS.items()]


def validate_premium_catalog(cases):
    if set(GEM_CASE_PRICES)!=set(cases):
        raise ValueError('Все семь кейсов должны продаваться только за Zombo')
    if len(CHESTS)!=3 or sorted(x['drops'] for x in CHESTS.values())!=[3,4,5]:
        raise ValueError('Неверное количество сундуков и наград')
    if sorted(x['price'] for x in CHESTS.values())!=[50,150,500]:
        raise ValueError('Неверные цены сундуков')
    for key,entry in CHESTS.items():
        if sum(entry['rarity_weights'].values())!=100 or sum(entry['cases'].values())!=100:
            raise ValueError(f'Неверные проценты: {key}')
        if entry['drops']!=1+len(entry['supplies']):
            raise ValueError(f'Сундук {key} не выдаёт обещанное количество дропов')
        if not set(entry['cases'])<=set(cases):
            raise ValueError('Неизвестный пул кейса')
        if any(not pool or any(qty<=0 for item,qty in pool)
               for pool in entry['supplies']):
            raise ValueError('Пустые награды')
    # The normal player has viable progression without a premium purchase;
    # box effects only use existing item/equipment systems.


def open_paid_chest(db,player_id,key,rng=None):
    """Redeem one owned premium chest in the caller's existing transaction.

    One exclusive weapon plus precisely 2/3/4 independently selected supply
    stacks. The ORM transaction automatically rolls back if the locker is full,
    the chest is missing, or a grant fails. Never creates or credits gems.
    """
    import random
    from armory_content import CASE_POOLS
    from gear import create_gear, gear_view
    from legendary_ammo import AMMO_KEY, STARTER_LEGENDARY_ROUNDS, is_firearm
    from game import give_item, take_item
    if key not in CHESTS:raise ValueError('Неизвестный премиум-сундук')
    rng=rng or random
    cfg=CHESTS[key]
    case=rng.choices(tuple(cfg['cases']),
                     weights=tuple(cfg['cases'].values()),k=1)[0]
    base=rng.choice(CASE_POOLS[case])
    rarity=rng.choices(tuple(cfg['rarity_weights']),
                       weights=tuple(cfg['rarity_weights'].values()),k=1)[0]
    # A chest already paid for must never be lost on a full weapons locker.
    gear=create_gear(db,player_id,base,rarity,'premium_chest')
    rewards=[{'kind':'gear','key':base,'qty':1,'name':gear_view(gear)['name'],
              'rarity':rarity,'gear':gear_view(gear)}]
    for index,pool in enumerate(cfg['supplies']):
        item,qty=rng.choice(pool)
        if (rarity=='legendary' and is_firearm(base) and
                index==len(cfg['supplies'])-1):
            # Guaranteed matching ammo within the advertised five reward slots.
            item,qty=AMMO_KEY,STARTER_LEGENDARY_ROUNDS
        give_item(db,player_id,item,qty)
        rewards.append({'kind':'item','key':item,'qty':qty})
    take_item(db,player_id,key,1)
    assert len(rewards)==cfg['drops']
    return rewards


validate_premium_catalog({
    'scrap_case':{},'field_case':{},'hunter_case':{},
    'military_case':{},'assault_case':{},'relic_case':{},'shadow_case':{},
})
