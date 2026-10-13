"""Unique gear for ZOMBO v0.6; all gear rolls/economy happen server-side.

Uses a NEW table (gear_items). The original item stacks and player tables remain intact.
"""
import math
import random
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String, select, func
from sqlalchemy.orm import Session

from models import Base, Player, ItemStack, SessionLocal, now

RARITIES = {
    'common': {'name': 'Обычный', 'color': '#b2b7c0', 'mult': 1.00, 'rank': 0},
    'uncommon': {'name': 'Необычный', 'color': '#82cba0', 'mult': 1.25, 'rank': 1},
    'rare': {'name': 'Редкий', 'color': '#76aaff', 'mult': 1.55, 'rank': 2},
    'epic': {'name': 'Эпический', 'color': '#c28fff', 'mult': 1.95, 'rank': 3},
    'legendary': {'name': 'Легендарный', 'color': '#f3c777', 'mult': 2.50, 'rank': 4},
}
BASE_GEAR = {
    'knife': {'name': 'Нож выжившего', 'icon': '🗡', 'slot': 'weapon', 'power': 7, 'defense': 0, 'material': 'metal'},
    'pistol': {'name': 'Пистолет «Сокол»', 'icon': '🔫', 'slot': 'weapon', 'power': 14, 'defense': 0, 'material': 'metal'},
    'rifle': {'name': 'Автомат АК-47', 'icon': '🔫', 'slot': 'weapon', 'power': 25, 'defense': 0, 'material': 'metal'},
    'vest': {'name': 'Бронежилет пустоши', 'icon': '🛡', 'slot': 'armor', 'power': 0, 'defense': 4, 'material': 'cloth'},
}
BASE_GEAR.update({
  "bat": {
    "name": "Бита",
    "icon": "🏏",
    "slot": "weapon",
    "power": 6,
    "defense": 0,
    "material": "wood"
  },
  "crowbar": {
    "name": "Лом",
    "icon": "🔧",
    "slot": "weapon",
    "power": 11,
    "defense": 0,
    "material": "metal"
  },
  "axe": {
    "name": "Топор",
    "icon": "🪓",
    "slot": "weapon",
    "power": 15,
    "defense": 0,
    "material": "metal"
  },
  "machete": {
    "name": "Мачете",
    "icon": "🗡️",
    "slot": "weapon",
    "power": 18,
    "defense": 0,
    "material": "metal"
  },
  "revolver": {
    "name": "Револьвер",
    "icon": "🔫",
    "slot": "weapon",
    "power": 20,
    "defense": 0,
    "material": "metal"
  },
  "crossbow": {
    "name": "Арбалет",
    "icon": "🏹",
    "slot": "weapon",
    "power": 23,
    "defense": 0,
    "material": "wood"
  },
  "smg": {
    "name": "Пистолет-пулемёт",
    "icon": "🔫",
    "slot": "weapon",
    "power": 26,
    "defense": 0,
    "material": "metal"
  },
  "shotgun": {
    "name": "Дробовик",
    "icon": "🔫",
    "slot": "weapon",
    "power": 29,
    "defense": 0,
    "material": "metal"
  },
  "sniper": {
    "name": "Снайперская винтовка",
    "icon": "🎯",
    "slot": "weapon",
    "power": 40,
    "defense": 0,
    "material": "metal"
  },
  "spear": {
    "name": "Копьё",
    "icon": "🔱",
    "slot": "weapon",
    "power": 13,
    "defense": 0,
    "material": "wood"
  },
  "hunting_bow": {
    "name": "Охотничий лук",
    "icon": "🏹",
    "slot": "weapon",
    "power": 18,
    "defense": 0,
    "material": "wood"
  },
  "chainsaw": {
    "name": "Бензопила",
    "icon": "⚙️",
    "slot": "weapon",
    "power": 36,
    "defense": 0,
    "material": "metal"
  },
  "light_coat": {
    "name": "Защитный плащ",
    "icon": "🧥",
    "slot": "armor",
    "power": 0,
    "defense": 2,
    "material": "cloth"
  },
  "padded_armor": {
    "name": "Усиленная куртка",
    "icon": "🛡️",
    "slot": "armor",
    "power": 0,
    "defense": 3,
    "material": "cloth"
  },
  "riot_armor": {
    "name": "Броня спецназа",
    "icon": "🛡️",
    "slot": "armor",
    "power": 0,
    "defense": 8,
    "material": "metal"
  },
  "hazmat_armor": {
    "name": "Костюм химзащиты",
    "icon": "☣️",
    "slot": "armor",
    "power": 0,
    "defense": 7,
    "material": "rubber"
  },
  "exosuit": {
    "name": "Экзоскелет",
    "icon": "🤖",
    "slot": "armor",
    "power": 0,
    "defense": 14,
    "material": "metal"
  },
  "leather_armor": {
    "name": "Кожаный жилет",
    "icon": "🧥",
    "slot": "armor",
    "power": 0,
    "defense": 5,
    "material": "cloth"
  },
  "hardened_vest": {
    "name": "Укреплённый бронежилет",
    "icon": "🛡️",
    "slot": "armor",
    "power": 0,
    "defense": 6,
    "material": "metal"
  },
  "tactical_armor": {
    "name": "Тактическая броня",
    "icon": "🛡️",
    "slot": "armor",
    "power": 0,
    "defense": 10,
    "material": "metal"
  }
})
MAX_GEAR=80
MAX_UPGRADE=10

class GearItem(Base):
    __tablename__='gear_items'
    id=Column(Integer,primary_key=True,autoincrement=True)
    player_id=Column(BigInteger,nullable=False,index=True)
    base_key=Column(String(32),nullable=False)
    rarity=Column(String(16),nullable=False,default='common')
    level=Column(Integer,nullable=False,default=0)
    equipped=Column(Boolean,nullable=False,default=False)
    source=Column(String(20),nullable=False,default='drop')
    obtained_at=Column(DateTime(timezone=True),default=now)


def roll_rarity(threat=1, minimum='common', rng=None):
    """Rarity floor and zone-adjusted weights; server controls RNG."""
    rng=rng or random
    threat=max(1,min(5,int(threat)))
    weights=[max(32,77-threat*7),17+threat*2,6+threat*2,1+threat,1+max(0,threat-3)]
    names=list(RARITIES)
    choice=rng.choices(names,weights=weights,k=1)[0]
    if minimum not in RARITIES:raise ValueError('Неизвестная минимальная редкость')
    return names[max(names.index(choice),names.index(minimum))]


def base_for_threat(threat=1,rng=None):
    rng=rng or random
    threat=max(1,min(5,int(threat)))
    options=['knife','vest']+(['pistol'] if threat>=2 else [])+(['rifle'] if threat>=4 else [])
    return rng.choice(options)


def create_gear(db:Session,player_id:int,base_key:str,rarity='common',source='drop'):
    if base_key not in BASE_GEAR:raise ValueError('Неизвестная экипировка')
    if rarity not in RARITIES:raise ValueError('Неизвестная редкость')
    # Count includes all owned copies; hard limit prevents unbounded drops and DB growth.
    count=db.scalar(select(func.count(GearItem.id)).where(GearItem.player_id==player_id)) or 0
    if count>=MAX_GEAR:raise ValueError('Склад экипировки заполнен (80 предметов)')
    item=GearItem(player_id=player_id,base_key=base_key,rarity=rarity,level=0,equipped=False,source=source)
    db.add(item)
    db.flush()
    return item


def roll_drop(db:Session,player_id:int,threat=1,minimum='common',rng=None):
    rng=rng or random
    return create_gear(db,player_id,base_for_threat(threat,rng),roll_rarity(threat,minimum,rng),'drop')


def gear_values(item:GearItem):
    base=BASE_GEAR[item.base_key]
    mult=RARITIES[item.rarity]['mult']
    # Higher ranks provide clear progression, without fractional player stats.
    increase=1+item.level*.12
    return {'power':int(round(base['power']*mult*increase)),
            'defense':int(round(base['defense']*mult*increase))}


def gear_view(item:GearItem):
    desc=BASE_GEAR[item.base_key]
    rarity=RARITIES[item.rarity]
    return {'id':item.id,'key':item.base_key,'name':desc['name'],'icon':desc['icon'],
            'slot':desc['slot'],'rarity':item.rarity,'rarity_name':rarity['name'],
            'color':rarity['color'],'rarity_rank':rarity['rank'],'level':item.level,
            'max_level':MAX_UPGRADE,'equipped':item.equipped,'source':item.source,
            **gear_values(item), 'upgrade_cost':upgrade_cost(item) if item.level<MAX_UPGRADE else None}


def gear_list(db:Session,player_id:int):
    return [gear_view(x) for x in db.scalars(select(GearItem).where(GearItem.player_id==player_id).order_by(GearItem.equipped.desc(),GearItem.id.desc())).all()]


def gear_stats(db:Session,player_id:int):
    equipped=db.scalars(select(GearItem).where(GearItem.player_id==player_id,GearItem.equipped==True)).all()
    power=max((gear_values(g)['power'] for g in equipped if BASE_GEAR[g.base_key]['slot']=='weapon'),default=0)
    defense=max((gear_values(g)['defense'] for g in equipped if BASE_GEAR[g.base_key]['slot']=='armor'),default=0)
    return {'power':power,'defense':defense}


def upgrade_cost(item:GearItem):
    rarity_rank=RARITIES[item.rarity]['rank']
    next_level=item.level+1
    return {'caps':int(35+25*next_level*(1+rarity_rank*.42)),
            'material':BASE_GEAR[item.base_key]['material'],
            'qty':int(2+math.ceil(next_level/2)+rarity_rank),
            'rare': 1 if next_level in (5,8,10) else 0}


def _owned_locked(db,player_id,item_id):
    item=db.scalar(select(GearItem).where(GearItem.id==item_id,GearItem.player_id==player_id).with_for_update())
    if not item:raise ValueError('Предмет не найден в твоём рюкзаке')
    return item


def equip_gear(db:Session,player_id,item_id):
    item=_owned_locked(db,player_id,item_id)
    if item.equipped:raise ValueError('Предмет уже экипирован')
    slot=BASE_GEAR[item.base_key]['slot']
    for old in db.scalars(select(GearItem).where(GearItem.player_id==player_id,GearItem.equipped==True).with_for_update()).all():
        if BASE_GEAR[old.base_key]['slot']==slot:old.equipped=False
    # Remove legacy equipped stack of the same slot; return it to the backpack.
    legacy=db.scalars(select(ItemStack).where(ItemStack.player_id==player_id,ItemStack.equipped==True).with_for_update()).all()
    for old in legacy:
        if old.item_key not in BASE_GEAR or BASE_GEAR[old.item_key]['slot']!=slot:continue
        old.equipped=False
        free=db.scalar(select(ItemStack).where(ItemStack.player_id==player_id,ItemStack.item_key==old.item_key,ItemStack.equipped==False,ItemStack.id!=old.id))
        if free:free.quantity+=old.quantity;db.delete(old)
    item.equipped=True
    return item


def unequip_gear(db,player_id,item_id):
    item=_owned_locked(db,player_id,item_id)
    if not item.equipped:raise ValueError('Предмет не экипирован')
    item.equipped=False
    return item


def upgrade_gear(db:Session,player:Player,item_id:int):
    from game import item_count,take_item
    item=_owned_locked(db,player.id,item_id)
    if item.level>=MAX_UPGRADE:raise ValueError('Максимальный уровень улучшения +10')
    cost=upgrade_cost(item)
    if player.caps<cost['caps']:raise ValueError('Не хватает крышек для улучшения')
    if item_count(db,player.id,cost['material'])<cost['qty']:raise ValueError('Недостаточно материалов')
    if cost['rare'] and item_count(db,player.id,'rare')<cost['rare']:raise ValueError('Не хватает военных жетонов')
    player.caps-=cost['caps']
    take_item(db,player.id,cost['material'],cost['qty'])
    if cost['rare']:take_item(db,player.id,'rare',cost['rare'])
    item.level+=1
    return item


def dismantle_gear(db:Session,player_id,item_id):
    from game import give_item
    item=_owned_locked(db,player_id,item_id)
    if item.equipped:raise ValueError('Сними экипировку перед разбором')
    rank=RARITIES[item.rarity]['rank']
    # Salvage is intentionally below crafting cost: no material-printing exploits.
    qty=min(5,1+rank+item.level//4)
    material=BASE_GEAR[item.base_key]['material']
    give_item(db,player_id,material,qty)
    if rank>=3:give_item(db,player_id,'rare',1)
    db.delete(item)
    return {'material':material,'quantity':qty,'rare':1 if rank>=3 else 0}


def install_gear(app,with_player,ready):
    router=APIRouter(prefix='/api/gear',tags=['Gear'])
    class IdBody(BaseModel):id:int=Field(gt=0,le=9223372036854775807)
    def session():
        db=SessionLocal()
        try:yield db
        finally:db.close()

    @router.get('')
    def list_items(request:Request,db:Session=Depends(session)):
        with db.begin():
            p=with_player(request,db);ready(p)
            return {'items':gear_list(db,p.id),'stats':gear_stats(db,p.id),'rarities':RARITIES,'capacity':MAX_GEAR}

    @router.post('/equip')
    def equip(body:IdBody,request:Request,db:Session=Depends(session)):
        with db.begin():
            p=with_player(request,db);ready(p)
            item=equip_gear(db,p.id,body.id)
            return {'message':f'Экипировано: {BASE_GEAR[item.base_key]["name"]} ({RARITIES[item.rarity]["name"]})'}

    @router.post('/unequip')
    def unequip(body:IdBody,request:Request,db:Session=Depends(session)):
        with db.begin():
            p=with_player(request,db);ready(p)
            item=unequip_gear(db,p.id,body.id)
            return {'message':f'Снято: {BASE_GEAR[item.base_key]["name"]}'}

    @router.post('/upgrade')
    def upgrade(body:IdBody,request:Request,db:Session=Depends(session)):
        with db.begin():
            p=with_player(request,db);ready(p)
            item=upgrade_gear(db,p,body.id)
            return {'message':f'Улучшено: {BASE_GEAR[item.base_key]["name"]} +{item.level}','item':gear_view(item)}

    @router.post('/dismantle')
    def dismantle(body:IdBody,request:Request,db:Session=Depends(session)):
        with db.begin():
            p=with_player(request,db);ready(p)
            loot=dismantle_gear(db,p.id,body.id)
            return {'message':f'Экипировка разобрана: +{loot["quantity"]} материалов','loot':loot}

    app.include_router(router)
