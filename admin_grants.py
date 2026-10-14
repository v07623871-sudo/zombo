"""Full admin reward catalog and strictly validated, auditable grant implementation."""
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select

from game import ITEMS, PETS, aware, gain_xp, give_item, item_count
from gear import BASE_GEAR, RARITIES, MAX_GEAR, GearItem, create_gear
from models import now


GIFT_BOOSTS={
    'vip_7':{'name':'VIP на 7 дней','days':7,'type':'vip'},
    'vip_14':{'name':'VIP на 14 дней','days':14,'type':'vip'},
    'vip_30':{'name':'VIP на 30 дней','days':30,'type':'vip'},
    'xp_day':{'name':'×2 опыт на 24 часа','days':1,'type':'xp'},
    'loot_day':{'name':'×2 добыча на 24 часа','days':1,'type':'loot'},
    'insurance_day':{'name':'Страховка на 24 часа','days':1,'type':'insurance'},
}


def gift_catalog():
    """Derive selectors from live loot/gear data; no hardcoded five-resource list."""
    return {
        'currencies':{
            'caps':{'name':'🪙 Крышки'},'zombo':{'name':'💎 Zombo (ручная выдача)'},
            'xp':{'name':'✦ XP'}},
        'items':{key:{
            'key':key,'name':meta['name'],'icon':meta.get('icon','📦'),
            'type':meta.get('type','material')}
            for key,meta in ITEMS.items()
            if key not in BASE_GEAR or key in ('knife','vest','pistol','rifle')},
        'gear':{key:{'key':key,'name':meta['name'],'icon':meta['icon'],
                     'slot':meta['slot'],'exclusive':bool(meta.get('exclusive'))}
                for key,meta in BASE_GEAR.items()},
        'pets':{key:{'key':key,'name':meta['name'],'icon':meta['icon']}
                for key,meta in PETS.items()},
        'premium':GIFT_BOOSTS,
        'rarities':{key:meta['name'] for key,meta in RARITIES.items()},
        'max_gear':MAX_GEAR,
    }


def grant_to_player(db,p,*,kind,key,amount=1,rarity='common',level=0):
    """Called inside an admin-only transaction, with target Player row locked.

    Does not create a Telegram Stars Payment, so manual donor currency is
    distinct from actual paid invoices in reports and audit logs.
    """
    catalog=gift_catalog()
    if kind=='currency':
        if key not in catalog['currencies']:raise HTTPException(400,'Неизвестная валюта')
        if key=='xp':
            before=f'LVL {p.level}, XP {p.xp}'
            gain_xp(p,amount)
            after=f'LVL {p.level}, XP {p.xp}'
        else:
            before=int(getattr(p,key) or 0)
            after=before+amount
            if after>2_000_000_000:raise HTTPException(400,'Лимит баланса превышен')
            setattr(p,key,after)
        return {'field':f'currency:{key}','before':before,'after':after}
    if kind=='item':
        if key not in catalog['items']:
            raise HTTPException(400,'Предмет отсутствует в каталоге инвентаря')
        if amount>10000:raise HTTPException(400,'Максимум 10000 предметов за раз')
        before=item_count(db,p.id,key)
        after=before+amount
        if after>1_000_000:raise HTTPException(400,'Переполнение инвентаря')
        give_item(db,p.id,key,amount)
        return {'field':f'item:{key}','before':before,'after':after}
    if kind=='gear':
        if key not in BASE_GEAR or rarity not in RARITIES:
            raise HTTPException(400,'Нет такой экипировки или редкости')
        if amount>10:raise HTTPException(400,'Максимум 10 экземпляров за раз')
        before=db.scalar(select(func.count()).select_from(GearItem)
                         .where(GearItem.player_id==p.id)) or 0
        if before+amount>MAX_GEAR:
            raise HTTPException(400,'Арсенал заполнен')
        ids=[]
        for _ in range(amount):
            entry=create_gear(db,p.id,key,rarity,source='admin')
            entry.level=level
            db.flush()
            ids.append(entry.id)
        return {'field':f'gear:{key}','before':before,'after':before+amount,
                'gear_ids':ids}
    if kind=='pet':
        if key not in PETS:raise HTTPException(400,'Неизвестный питомец')
        if amount!=1:raise HTTPException(400,'Питомец выдаётся по одному')
        current=(p.stats or {}).get('_pet')
        before=current.get('key','нет') if isinstance(current,dict) else 'нет'
        stats=dict(p.stats or {})
        stats['_pet']={'key':key,'level':max(1,level or 1),'xp':0}
        p.stats=stats
        return {'field':'pet','before':before,'after':key}
    if kind=='premium':
        choice=GIFT_BOOSTS.get(key)
        if choice is None:raise HTTPException(400,'Нет такого VIP/бонуса')
        if amount!=1:raise HTTPException(400,'VIP выдаётся по одному')
        if choice['type']=='insurance':
            from game import insurance_active
            flags=dict(p.stats or {})
            try:
                old_end=datetime.fromisoformat(flags['_insurance_until']) if insurance_active(p) else None
            except (KeyError,TypeError,ValueError):old_end=None
            before=flags.get('_insurance_until','нет')
            start=max(now(),aware(old_end)) if old_end else now()
            after=(start+timedelta(days=choice['days'])).isoformat()
            flags['_insurance_until']=after
            p.stats=flags
        else:
            field={'vip':'vip_until','xp':'xp_boost_until',
                   'loot':'loot_boost_until'}[choice['type']]
            old_end=getattr(p,field)
            before=old_end.isoformat() if old_end else 'нет'
            start=max(now(),aware(old_end)) if old_end else now()
            new_end=start+timedelta(days=choice['days'])
            setattr(p,field,new_end)
            after=new_end.isoformat()
        return {'field':f'premium:{key}','before':before,'after':after}
    raise HTTPException(400,'Неизвестный вид выдачи')
