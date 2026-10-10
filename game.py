import random, math
from datetime import timedelta
from sqlalchemy import select, func
from models import now, Player, ItemStack, Battle, WorldBoss, BossHit, QuestProgress, Territory

CLASSES = {
    'medic': {'name':'Врач','icon':'✚','subtitle':'Медик отряда','color':'#6dc7ba','bonus':'Лечение ×2 · регенерация','power':1.00,'healing':2.0,'loot':1.0,'crit':0.05,'hp':110},
    'soldier': {'name':'Коп','icon':'✦','subtitle':'Стальная дисциплина','color':'#8db4e2','bonus':'Урон ×1.15 · крепкая броня','power':1.15,'healing':1.0,'loot':1.0,'crit':0.08,'hp':125},
    'assassin': {'name':'Убийца','icon':'⚔','subtitle':'Бесшумная смерть','color':'#ec8d83','bonus':'Урон ×1.25 · шанс критического удара','power':1.25,'healing':0.7,'loot':1.0,'crit':0.20,'hp':95},
    'thief': {'name':'Вор','icon':'◈','subtitle':'Тень пустоши','color':'#d8b66f','bonus':'Добыча ×1.80 · уклонение','power':0.9,'healing':1.1,'loot':1.8,'crit':0.10,'hp':100},
}
SKILLS = {
    'medic': [('healer','Полевой врач','Сильнее аптечки'),('regeneration','Регенерация','Восстановление здоровья'),('energy','Стимулятор','Экономия выносливости'),('antidote','Антидот','Защита от яда'),('guard','Защита','Меньше входящего урона'),('master','Главврач','Особое мастерство')],
    'soldier': [('aim','Наводка','Точность и урон'),('steadfast','Стойкость','Меньше входящего урона'),('care','Уход','Ремонт'),('double','Двойной выстрел','Дополнительная атака'),('sniper','Снайпер','Критический урон'),('master','Командир','Особое мастерство')],
    'assassin': [('precision','Точность','Больше попаданий'),('rage','Ярость','Больше урон'),('bleeding','Кровожадность','Добивающий удар'),('vamp','Вампиризм','Лечение от ударов'),('speed','Скорость','Уклонение'),('master','Мастер клинка','Особое мастерство')],
    'thief': [('dodge','Уклонение','Меньше урона'),('loot','Добыча','Больше находок'),('gold','Золото','Больше крышек'),('steal','Кража','Небольшой шанс добычи'),('silent','Тихий шаг','Экономия энергии'),('master','Мастер тени','Особое мастерство')]
}
STATS = {'strength':'Сила','agility':'Ловкость','endurance':'Выносливость','accuracy':'Точность','regen':'Регенерация','luck':'Удача'}
ITEMS = {
    'knife': {'name':'Ржавый нож','icon':'🗡️','type':'weapon','power':7,'desc':'Оружие ближнего боя'},
    'pistol': {'name':'Пистолет «Сокол»','icon':'🔫','type':'weapon','power':14,'desc':'Надёжный в пустоши'},
    'rifle': {'name':'АК-47','icon':'🔫','type':'weapon','power':25,'desc':'Редкое штурмовое оружие'},
    'vest': {'name':'Бронежилет','icon':'🛡️','type':'armor','power':4,'desc':'Снижает получаемый урон'},
    'medkit': {'name':'Аптечка','icon':'🧰','type':'consumable','desc':'Восстановить 45 HP'},
    'food': {'name':'Консервы','icon':'🥫','type':'consumable','desc':'Снижает голод'},
    'water': {'name':'Чистая вода','icon':'💧','type':'consumable','desc':'Утолить жажду'},
    'wood': {'name':'Древесина','icon':'🪵','type':'material'},
    'metal': {'name':'Металлолом','icon':'⚙️','type':'material'},
    'cloth': {'name':'Ткань','icon':'🧵','type':'material'},
    'wire': {'name':'Проволока','icon':'🔌','type':'material'},
    'rubber': {'name':'Резина','icon':'🛞','type':'material'},
    'stone': {'name':'Камень','icon':'🪨','type':'material'},
    'rare': {'name':'Военный жетон','icon':'🏅','type':'material'}
}
LOCATIONS = {
    'base': {'name':'Убежище','icon':'⌂','min_level':1,'threat':0,'material':'none','desc':'Место, где безопасно даже после заката'},
    'forest': {'name':'Мёртвый лес','icon':'♣','min_level':1,'threat':1,'material':'wood','desc':'Туман, старые тропы и первые заражённые'},
    'city': {'name':'Забытый город','icon':'▥','min_level':5,'threat':3,'material':'cloth','desc':'Витрины разбиты, но в квартирах ещё есть припасы'},
    'factory': {'name':'Ржавый завод','icon':'⚙','min_level':15,'threat':4,'material':'metal','desc':'Станки, токсичные отходы, тяжёлые мутанты'},
    'hospital': {'name':'Пустая больница','icon':'✚','min_level':25,'threat':5,'material':'medkit','desc':'Ценная медицина и опасные коридоры'},
    'wasteland': {'name':'Красная пустошь','icon':'☢','min_level':40,'threat':5,'material':'rare','desc':'Город смерти. Здесь выживают легенды'},
}
RECIPES = {
    'medkit': {'qty':1,'cost':{'cloth':2,'wood':1}},
    'knife': {'qty':1,'cost':{'metal':2,'wood':2}},
    'pistol': {'qty':1,'cost':{'metal':8,'wire':2,'rubber':2}},
    'vest': {'qty':1,'cost':{'cloth':8,'metal':6}},
    'rifle': {'qty':1,'cost':{'metal':20,'wire':8,'rubber':6,'rare':2}},
}
QUESTS = {
    'kills':{'name':'Чистка периметра','description':'Победить 5 заражённых','target':5,'reward':{'caps':120,'xp':180}},
    'scavenge':{'name':'Собиратель','description':'Найти припасы 8 раз','target':8,'reward':{'caps':100,'xp':100}},
    'boss':{'name':'Охотник на чудовищ','description':'Нанести удар мировому боссу','target':1,'reward':{'caps':220,'xp':200}},
    'pvp':{'name':'Аренный боец','description':'Победить игрока в дуэли','target':1,'reward':{'caps':200,'xp':250}},
}
TERRITORIES = {'depot':'Склад снабжения','bridge':'Северный мост','tower':'Радиовышка','clinic':'Бункер медиков'}
ZOMBIES = [('Шатающийся','Обглоданный'),('Бегун','Бродяга'),('Кислотный мутант','Падальщик'),('Бронированный заражённый','Осквернитель'),('Заражённый исполин','Вожак')]

def aware(dt):
    if not dt: return None
    from datetime import timezone
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def max_hp(p): return CLASSES.get(p.hero_class,{}).get('hp',100) + p.stats.get('endurance',0)*5 + (p.level-1)*3

def xp_needed(level): return int(150*level**1.75+300*level)

def spend_stamina(p, cost):
    tick(p)
    if p.stamina < cost: raise ValueError(f'Не хватает выносливости. Нужно {cost} ⚡')
    p.stamina -= cost

def tick(p):
    current=now()
    elapsed=max(0,(current-aware(p.last_tick or current)).total_seconds())
    regen=int(elapsed//300)*(4 if p.vip_until and aware(p.vip_until)>current else 2)
    if regen>0:
        p.stamina=min(500,p.stamina+regen)
        p.hp=min(max_hp(p),p.hp+int(elapsed//3600)*(1+p.stats.get('regen',0)))
        p.last_tick=current

def gain_xp(p, amount):
    if p.vip_until and aware(p.vip_until)>now():amount=int(amount*1.2)
    if p.xp_boost_until and aware(p.xp_boost_until)>now():amount*=2
    p.xp+=amount
    leveled=0
    while p.xp>=xp_needed(p.level) and leveled<100:
        p.xp-=xp_needed(p.level)
        p.level+=1;p.stat_points+=1
        if p.level%5==0:p.skill_points+=1
        p.hp=max_hp(p)
        leveled+=1
    return leveled

def item_count(db,pid,key):
    x=db.scalar(select(ItemStack).where(ItemStack.player_id==pid, ItemStack.item_key==key, ItemStack.equipped==False))
    return x.quantity if x else 0

def give_item(db,pid,key,qty=1):
    if key not in ITEMS or qty<=0: raise ValueError('Неизвестный предмет')
    stack=db.scalar(select(ItemStack).where(ItemStack.player_id==pid, ItemStack.item_key==key, ItemStack.equipped==False).with_for_update())
    if stack:stack.quantity+=qty
    else:db.add(ItemStack(player_id=pid,item_key=key,quantity=qty,equipped=False))

def take_item(db,pid,key,qty=1):
    if qty<=0 or item_count(db,pid,key)<qty:raise ValueError('Недостаточно предметов')
    stack=db.scalar(select(ItemStack).where(ItemStack.player_id==pid,ItemStack.item_key==key,ItemStack.equipped==False).with_for_update())
    stack.quantity-=qty
    if stack.quantity==0:db.delete(stack)

def progress(db,pid,code,qty=1):
    q=db.scalar(select(QuestProgress).where(QuestProgress.player_id==pid,QuestProgress.code==code).with_for_update())
    if not q:
        q=QuestProgress(player_id=pid,code=code,amount=0)
        db.add(q)
    q.amount+=qty

def player_view(db,p):
    tick(p)
    inv=db.scalars(select(ItemStack).where(ItemStack.player_id==p.id).order_by(ItemStack.equipped.desc(),ItemStack.item_key)).all()
    battle=db.scalar(select(Battle).where(Battle.player_id==p.id))
    return {'id':p.id,'name':p.name,'username':p.username,'class':p.hero_class,'level':p.level,'xp':p.xp,'xp_next':xp_needed(p.level),
        'stats':p.stats,'skills':p.skills,'stat_points':p.stat_points,'skill_points':p.skill_points,
        'hp':p.hp,'max_hp':max_hp(p),'stamina':p.stamina,'max_stamina':500,'hunger':p.hunger,'thirst':p.thirst,'caps':p.caps,
        'zombo':p.zombo,'location':p.location,'kills':p.kills,'rating':p.rating,'karma':p.karma,'clan_id':p.clan_id,'pvp_wins':p.pvp_wins,
        'last_daily':p.last_daily,'vip_until':aware(p.vip_until).isoformat() if p.vip_until else None,'xp_boost_until':aware(p.xp_boost_until).isoformat() if p.xp_boost_until else None,'loot_boost_until':aware(p.loot_boost_until).isoformat() if p.loot_boost_until else None,'battle':battle_view(battle),'inventory':[{'key':i.item_key,'qty':i.quantity,'equipped':i.equipped,**ITEMS[i.item_key]} for i in inv if i.item_key in ITEMS]}

def battle_view(b):
    if not b:return None
    return {'id':b.id,'enemy':b.enemy,'hp':b.enemy_hp,'max_hp':b.enemy_max_hp,'turn':b.turn,'log':b.log[-5:]}

def attack_power(db,p):
    weapon=db.scalar(select(ItemStack).where(ItemStack.player_id==p.id,ItemStack.equipped==True,ItemStack.item_key.in_(['knife','pistol','rifle'])))
    w=ITEMS[weapon.item_key]['power'] if weapon else 3
    cls=CLASSES.get(p.hero_class,CLASSES['soldier'])
    return int((7+p.level*2+p.stats.get('strength',0)*2+w)*cls['power']*(1+.08*len(p.skills)))

def combat_round(db,p,b,action,zone='body'):
    if action not in ['attack','medkit','flee','defend']: raise ValueError('Неизвестное действие')
    if action=='flee':
        db.delete(b)
        return {'finished':True,'won':False,'fled':True,'message':'Удалось ускользнуть от заражённого'}
    if action=='medkit':
        take_item(db,p.id,'medkit')
        heal=int(45*CLASSES[p.hero_class]['healing'])
        p.hp=min(max_hp(p),p.hp+heal)
        msg=f'Использована аптечка: +{heal} HP'
    elif action=='defend':msg='Защитная стойка: урон противника уменьшен'
    else:
        if zone not in ('head','body','legs'):raise ValueError('Неверная зона')
        spend_stamina(p,2)
        d=max(1,int(attack_power(db,p)*{'head':1.5,'body':1.0,'legs':0.7}[zone]*random.uniform(.8,1.2)))
        chance={'head':.68,'body':.94,'legs':.99}[zone] +p.stats.get('accuracy',0)*.005
        if random.random()>min(.99,chance):d=0
        crit=random.random()<min(.6,CLASSES[p.hero_class]['crit']+p.stats.get('agility',0)*.004)
        if crit:d*=2
        b.enemy_hp=max(0,b.enemy_hp-d)
        msg=f"{('КРИТ! ' if crit and d else '')}Удар {dict(head='в голову',body='в тело',legs='по ногам')[zone]}: {d} урона"
    if b.enemy_hp<=0:
        p.kills+=1
        xp=int((35+b.enemy_max_hp*.3)*random.uniform(.85,1.15));caps=random.randint(9,32)+b.enemy_damage
        xp_levels=gain_xp(p,xp)
        p.caps+=caps
        loot=[]
        loot_bonus=2 if p.loot_boost_until and aware(p.loot_boost_until)>now() else 1
        if random.random()<min(.95,.44*CLASSES[p.hero_class]['loot']*loot_bonus):
            pool=['wood','cloth','metal','food','water','medkit','wire']
            key=random.choice(pool);give_item(db,p.id,key);loot.append(key)
            progress(db,p.id,'scavenge')
        progress(db,p.id,'kills')
        db.delete(b)
        return {'finished':True,'won':True,'message':f'Победа! +{xp} XP, +{caps} крышек'+(' · Новый уровень!' if xp_levels else ''),'loot':loot}
    defense=db.scalar(select(ItemStack).where(ItemStack.player_id==p.id,ItemStack.equipped==True,ItemStack.item_key=='vest'))
    received=max(1,b.enemy_damage+random.randint(-3,5)- (4 if defense else 0)- (8 if action=='defend' else 0))
    p.hp=max(0,p.hp-received)
    b.turn+=1;b.log=[*(b.log or [])[-5:],msg,f'{b.enemy} наносит {received} урона']
    if p.hp==0:
        p.hp=max(1,max_hp(p)//2)
        loss=min(p.caps,int(p.caps*.2))
        p.caps-=loss
        p.xp=int(p.xp*.7)
        p.location='base'
        p.cooldown=now()+timedelta(seconds=30)
        db.delete(b)
        return {'finished':True,'won':False,'message':f'Ты погибла в пустоши. Потеряно {loss} крышек и часть опыта'}
    return {'finished':False,'message':msg,'battle':battle_view(b)}

def spawn_battle(db,p):
    if p.location=='base':raise ValueError('Сначала отправься в локацию')
    if db.scalar(select(Battle).where(Battle.player_id==p.id)):
        raise ValueError('Сначала закончи текущий бой')
    if p.hp < 1:raise ValueError('Нужно восстановить здоровье')
    spend_stamina(p,2)
    threat=LOCATIONS[p.location]['threat']
    enemy=random.choice(ZOMBIES[max(0,threat-2):min(5,threat+1)])
    hp=30+threat*18+random.randint(0,20)
    b=Battle(player_id=p.id, enemy=random.choice(enemy),enemy_hp=hp,enemy_max_hp=hp,enemy_damage=3+threat*3,log=['Вдалеке слышен хрип...'])
    db.add(b);db.flush()
    return battle_view(b)

def boss_sync(db):
    b=db.get(WorldBoss,1)
    if not b:
        b=WorldBoss(id=1,name='Гниющий колосс',hp=500000,max_hp=500000,spawn_at=now())
        db.add(b);db.flush()
    elif now()-aware(b.spawn_at)>timedelta(days=3):
        b.spawn_at=now();b.hp=b.max_hp
    return b