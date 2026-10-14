"""Legendary firearm ammunition with a bounded, free-to-play supply path.

Legacy equipment, melee weapons and lower-rarity guns retain the existing
combat rules. A legendary firearm consumes 1 round per attack attempt; without
one, its ranged bonus is unavailable but the player may still attack unarmed.
No Stars purchase is required to make ammunition.
"""
from sqlalchemy import select

AMMO_KEY='legendary_ammo'
AMMO_ITEM={'name':'Легендарные патроны','icon':'✧','type':'material',
           'desc':'1 патрон на выстрел легендарной пушки. Без патронов — только базовая атака.'}
AMMO_RECIPE={'qty':5,'cost':{'metal':5,'wire':3,'rare':1}}
AMMO_SHOP_PRICE=85
STARTER_LEGENDARY_ROUNDS=12
# Bows use arrows, chainsaws and melee weapons do not fire cartridges.
NON_FIREARMS=frozenset({
    'knife','bat','crowbar','axe','machete','spear','chainsaw',
    'crossbow','hunting_bow','compound_bow','hunter_nomad',
})


def is_firearm(base_key):
    from gear import BASE_GEAR
    return (base_key in BASE_GEAR and
            BASE_GEAR[base_key]['slot']=='weapon' and
            BASE_GEAR[base_key]['power']>0 and
            base_key not in NON_FIREARMS)


def equipped_legendary_firearm(db,player_id):
    from gear import GearItem
    found=list(db.scalars(select(GearItem).where(
        GearItem.player_id==player_id,GearItem.equipped.is_(True))))
    for candidate in db.identity_map.values():
        if (isinstance(candidate,GearItem) and candidate.player_id==player_id
                and candidate.equipped and candidate not in found):
            found.append(candidate)
    return next((item for item in found if item.equipped and
                 item.rarity=='legendary' and is_firearm(item.base_key)),None)


def spend_legendary_round(db,player_id):
    """Call once per player attack attempt while holding their Player row lock.

    Returns 'spent' if 1 cartridge was consumed, 'empty' if legendary ammo was
    needed but missing, and 'normal' for other weapons. All within action txn.
    """
    if equipped_legendary_firearm(db,player_id) is None:return 'normal'
    from game import item_count,take_item
    if item_count(db,player_id,AMMO_KEY)<1:return 'empty'
    take_item(db,player_id,AMMO_KEY,1)
    return 'spent'


def ammo_message(status):
    return (' · ✧ Легендарный патрон' if status=='spent' else
            ' · Нет легендарных патронов: атака без бонуса пушки'
            if status=='empty' else '')
