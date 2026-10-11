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
# Three interconnected talent paths for every survivor class. Existing learned IDs
# remain valid; duplicate IDs in the JSON list represent talent ranks (1..3).
# Each node defines a mechanically meaningful passive or an active combat skill.
TALENT_PATHS = {
 'medic': [
  ('ПОЛЕВАЯ МЕДИЦИНА','✚','Верни отряд с того света',[
   ('healer','Экстренная помощь','✚','Аптечки восстанавливают больше HP','healing',.18),
   ('antidote','Антидот','⌁','Сопротивление атакам заражённых','mitigation',.035),
   ('master','Второе дыхание','✹','Активный навык: восстановление HP во время боя','ability',1)]),
  ('ВЫЖИВАНИЕ','⛨','Проживи ещё один день',[
   ('regeneration','Регенерация','♥','Быстрее восстановление HP со временем','regen',2),
   ('energy','Стимулятор','ϟ','Восстановление энергии и экономия сил','energy',.12),
   ('guard','Защитный протокол','⬟','Меньше урона и крепче здоровье','armor',.035)]),
  ('САНИТАРНАЯ ЗАЧИСТКА','☣','Бей заражённых по слабым местам',[
   ('sterilize','Стерильный выстрел','⊕','Больше наносимого урона','power',.06),
   ('hematology','Анатомия','◉','Выше шанс критического удара','crit',.035),
   ('clean_sweep','Очистка зоны','⚔','Сильнее удары по мировому боссу','boss',.09)])],
 'soldier': [
  ('ОГНЕВАЯ МОЩЬ','⚔','Ни шагу назад',[
   ('aim','Меткая очередь','◎','Бонус к обычному урону','power',.065),
   ('double','Двойной выстрел','✹','Активный навык: залп повышенного урона','ability',1),
   ('sniper','Снайпер','⊕','Выше шанс критического удара','crit',.045)]),
  ('БАСТИОН','⛨','Стой даже когда все пали',[
   ('steadfast','Стойкость','⬟','Меньше получаемого урона','mitigation',.045),
   ('guard_post','Броня выжившего','♥','Дополнительный запас здоровья','health',10),
   ('master','Несокрушимый','♜','Ещё меньше получаемого урона','armor',.045)]),
  ('ТАКТИКА','⌖','Каждая пуля должна попасть',[
   ('care','Выдержка','ϟ','Быстрее восстанавливается энергия','energy',.12),
   ('suppression','Подавление','◉','Точнее удары по уязвимым зонам','accuracy',.03),
   ('commander','Командир','✧','Больше опыта за победы','xp',.06)])],
 'assassin': [
  ('КРОВАВЫЙ СЛЕД','⚔','Каждый удар может стать последним',[
   ('precision','Смертельная точность','◉','Выше шанс критического удара','crit',.045),
   ('bleeding','Добивающий удар','☠','Усиленный урон по раненой цели','execute',.12),
   ('master','Шквал клинков','✹','Активный навык: жестокий удар с критическим шансом','ability',1)]),
  ('ЯРОСТЬ','☣','Обрати боль в силу',[
   ('rage','Ярость','✦','Усиление всех атак','power',.075),
   ('vamp','Жажда крови','♥','Похищение здоровья при атаке','lifesteal',.035),
   ('bloodmoon','Кровавая луна','⚔','Выше урон мировому боссу','boss',.12)]),
  ('ТЕНЬ','◈','Враг не видит твоей руки',[
   ('speed','Скорость','↝','Шанс увернуться от вражеского удара','dodge',.045),
   ('veil','Покров ночи','⬟','Уменьшает получаемый урон','mitigation',.03),
   ('phantom','Призрак','ϟ','Экономит энергию в бою','energy',.12)])],
 'thief': [
  ('ПУТЬ ТЕНИ','◈','Будь там, где тебя не ждут',[
   ('dodge','Ловкий шаг','↝','Чаще уклоняешься от врагов','dodge',.05),
   ('silent','Без шума','ϟ','Восстанавливай энергию быстрее','energy',.15),
   ('master','Дымовая завеса','✹','Активный навык: удар из тени и уклонение','ability',1)]),
  ('ДОБЫЧА','⬡','Пустошь принадлежит находчивым',[
   ('loot','Мародёр','▣','Выше шанс добычи после победы','loot',.09),
   ('gold','Золотые руки','🪙','Больше крышек за победу','caps',.10),
   ('steal','Карманник','◇','Больше ресурсов при поиске припасов','scavenge',.25)]),
  ('НАЛЁТ','⚔','Бей первым и исчезай',[
   ('ambush','Удар из засады','⚔','Повышает наносимый урон','power',.06),
   ('backstab','Удар в спину','◉','Шанс критического удара','crit',.04),
   ('escape_artist','Неуловимый','⬟','Меньше урона от врага','mitigation',.04)])]
}

SKILL_TREES = {}
for _klass, _branches in TALENT_PATHS.items():
    SKILL_TREES[_klass] = []
    for _index, (_title, _icon, _desc, _nodes) in enumerate(_branches):
        _previous = None
        _items = []
        for _tier, (_key, _name, _node_icon, _hint, _effect, _rate) in enumerate(_nodes):
            _items.append({'key':_key,'name':_name,'icon':_node_icon,'description':_hint,'effect':_effect,
                           'per_rank':_rate,'tier':_tier+1,'max_rank':3,'min_level':(1,5,12)[_tier],
                           'requires':_previous,'required_rank':(0,1,2)[_tier],
                           'kind':'active' if _effect=='ability' else 'passive'})
            _previous = _key
        SKILL_TREES[_klass].append({'id':str(_index),'name':_title,'icon':_icon,'description':_desc,'nodes':_items})

# In-game intelligence: tactical counterplay rather than purely cosmetic mob labels.
ENEMY_TACTICS = {
    'walker':'Слабый противник. Целься в голову, чтобы быстрее закончить бой.',
    'crawler':'Скрытный противник. Перед выпадом выгоднее защищаться.',
    'runner':'Каждая третья атака — рывок. Встречай его в защите.',
    'howler':'Вопль крадёт энергию. Защитная стойка блокирует истощение.',
    'spitter':'Кислота сжигает энергию. Перед плевком встань в защиту.',
    'stalker':'Атакует из тени. Защита ослабляет его внезапный удар.',
    'armored':'Костяная броня снижает урон. Удары в голову лучше пробивают защиту.',
    'brute':'Сокрушительный удар очень опасен. Используй защиту на третьем ходу.',
    'toxic':'Ядовитая вспышка отнимает силы. Блокируй её защитой.',
    'reaper':'Элитный противник. Пережидай усиленные атаки в защите.',
}

def record_enemy(p, key, defeated=False):
    """Persist an enemy sighting/kill in existing JSON stats, without a DB migration."""
    if key not in ENEMIES:
        return False
    stats = dict(p.stats or {})
    codex = dict(stats.get('_enemy_codex') or {})
    entry = dict(codex.get(key) or {})
    first = defeated and not entry.get('kills', 0)
    entry['seen'] = max(1, int(entry.get('seen', 0)))
    if defeated:
        entry['kills'] = min(1000000, max(0, int(entry.get('kills', 0))) + 1)
    codex[key] = entry
    stats['_enemy_codex'] = codex
    p.stats = stats
    return first

def talent_node(klass, key):
    return next((n for branch in SKILL_TREES.get(klass,[]) for n in branch['nodes'] if n['key']==key),None)

def talent_rank(p,key):
    return min(3,(p.skills or []).count(key))

def talent_bonus(p,effect):
    return sum(n['per_rank']*talent_rank(p,n['key']) for path in SKILL_TREES.get(p.hero_class,[]) for n in path['nodes'] if n['effect']==effect)

def talent_bonuses(p):
    return {metric:round(talent_bonus(p,metric),3) for metric in ('power','crit','mitigation','armor','health','healing','regen','energy','boss','accuracy','xp','loot','caps','scavenge','execute','lifesteal','dodge')}

def talent_reset_cost(p):
    # First reset is complimentary so the player can learn the system.
    if not p.stats.get('_talent_resets',0):return 0
    return 100+25*len(p.skills or [])

def migrate_talents(p):
    # No database migration needed: remember conversion in existing JSON stats field.
    if not p.hero_class or p.stats.get('_talent_v2'):return
    old_grants=p.level//5
    new_grants=2+p.level//2+p.level//5
    p.skill_points+=(new_grants-old_grants)
    p.stats={**p.stats,'_talent_v2':1}

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
# Versioned enemy keys are stored inside the existing Battle.kind column (no database migration).
# Traits change actual combat and are not merely cosmetic labels.
ENEMIES = {
    'walker': {'name':'Шатун','tier':1,'min_threat':1,'family':'Заражённый','trait':'none','skill':'Медленный удар','hp':.80,'damage':.8,'reward':.90,'armor':0,'color':'#91a59a','lore':'Первый сигнал заражения. Медленный, но неумолимый.'},
    'crawler': {'name':'Ползун','tier':1,'min_threat':1,'family':'Заражённый','trait':'ambush','skill':'Выпад снизу','hp':.70,'damage':1.,'reward':1.,'armor':0,'color':'#ac9275','lore':'Передвигается бесшумно по земле и бросается на ноги.'},
    'runner': {'name':'Бегун','tier':2,'min_threat':1,'family':'Быстрый','trait':'frenzy','skill':'Бешеный рывок','hp':.80,'damage':1.22,'reward':1.15,'armor':0,'color':'#ce9b78','lore':'Слышит шаги издалека. Опасен на короткой дистанции.'},
    'howler': {'name':'Крикун','tier':2,'min_threat':2,'family':'Особый','trait':'howl','skill':'Заражённый вопль','hp':.95,'damage':1.07,'reward':1.25,'armor':0,'color':'#b2a0bd','lore':'Его визг пробирает до костей.'},
    'spitter': {'name':'Плевун','tier':3,'min_threat':3,'family':'Мутант','trait':'acid','skill':'Кислотный плевок','hp':1.10,'damage':1.10,'reward':1.5,'armor':0,'color':'#99ba70','lore':'Выплёвывает едкую жидкость на расстоянии.'},
    'stalker': {'name':'Следопыт','tier':3,'min_threat':3,'family':'Особый','trait':'ambush','skill':'Атака из тени','hp':1.05,'damage':1.2,'reward':1.55,'armor':0,'color':'#8597b1','lore':'Преследует жертву, пока та не теряет бдительность.'},
    'armored': {'name':'Броненосец','tier':4,'min_threat':4,'family':'Тяжёлый','trait':'armor','skill':'Броневой удар','hp':1.40,'damage':.98,'reward':1.80,'armor':.25,'color':'#a9a69a','lore':'Костяные наросты служат почти непробиваемой бронёй.'},
    'brute': {'name':'Громила','tier':4,'min_threat':4,'family':'Тяжёлый','trait':'smash','skill':'Сокрушительный удар','hp':1.65,'damage':1.30,'reward':1.95,'armor':.09,'color':'#b88d79','lore':'Гигантский мутант, способный проломить укрепления.'},
    'toxic': {'name':'Токсик','tier':5,'min_threat':5,'family':'Мутант','trait':'acid','skill':'Ядовитая вспышка','hp':1.25,'damage':1.45,'reward':2.20,'armor':.10,'color':'#c7bb76','lore':'Плоть пропитана химикатами красной пустоши.'},
    'reaper': {'name':'Жнец','tier':5,'min_threat':5,'family':'Элита','trait':'frenzy','skill':'Последняя охота','hp':1.80,'damage':1.60,'reward':2.80,'armor':.17,'color':'#d17e7d','lore':'Выжил там, где погибли даже мутанты.'},
}

def choose_enemy(threat, rng=None):
    rng = rng or random
    # Avoid fighting upper-tier enemies in early zones.
    eligible = [(key, data) for key, data in ENEMIES.items() if data['min_threat'] <= threat and data['tier'] <= min(5, threat + 1)]
    weights = [max(1, 6-abs(data['tier'] - threat)*2) for _, data in eligible]
    return rng.choices([key for key, _ in eligible], weights=weights, k=1)[0]

def enemy_info(kind):
    key = kind.split(':',1)[1] if kind.startswith('zombie:') else 'walker'
    return (key if key in ENEMIES else 'walker'), ENEMIES.get(key, ENEMIES['walker'])


def aware(dt):
    if not dt: return None
    from datetime import timezone
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def max_hp(p): return CLASSES.get(p.hero_class,{}).get('hp',100) + p.stats.get('endurance',0)*5 + (p.level-1)*3 + int(talent_bonus(p,'health'))

def xp_needed(level): return int(150*level**1.75+300*level)

def spend_stamina(p, cost):
    tick(p)
    actual=max(1,round(cost*(1-min(.55,talent_bonus(p,'energy')*.45))))
    if p.stamina < actual: raise ValueError(f'Не хватает выносливости. Нужно {actual} ⚡')
    p.stamina -= actual

def tick(p):
    current=now()
    elapsed=max(0,(current-aware(p.last_tick or current)).total_seconds())
    regen=int(elapsed//300)*(4 if p.vip_until and aware(p.vip_until)>current else 2)
    regen=int(regen*(1+talent_bonus(p,'energy')))
    if regen>0:
        p.stamina=min(500,p.stamina+regen)
        p.hp=min(max_hp(p),p.hp+int(elapsed//3600)*(1+p.stats.get('regen',0)+int(talent_bonus(p,'regen'))))
        p.last_tick=current

def gain_xp(p, amount):
    if p.vip_until and aware(p.vip_until)>now():amount=int(amount*1.2)
    if p.xp_boost_until and aware(p.xp_boost_until)>now():amount*=2
    amount=int(amount*(1+talent_bonus(p,'xp')))
    p.xp+=amount
    leveled=0
    while p.xp>=xp_needed(p.level) and leveled<100:
        p.xp-=xp_needed(p.level)
        p.level+=1;p.stat_points+=1
        if p.level%2==0:p.skill_points+=1
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
    from gear import gear_list,gear_stats
    tick(p)
    inv=db.scalars(select(ItemStack).where(ItemStack.player_id==p.id).order_by(ItemStack.equipped.desc(),ItemStack.item_key)).all()
    battle=db.scalar(select(Battle).where(Battle.player_id==p.id))
    return {'id':p.id,'name':p.name,'username':p.username,'class':p.hero_class,'level':p.level,'xp':p.xp,'xp_next':xp_needed(p.level),
        'stats':p.stats,'skills':p.skills,'stat_points':p.stat_points,'skill_points':p.skill_points,
        'talent_ranks':{n['key']:talent_rank(p,n['key']) for br in SKILL_TREES.get(p.hero_class,[]) for n in br['nodes']},
        'talent_bonuses':talent_bonuses(p),'talent_spent':len(p.skills or []),
        'talent_reset_cost':talent_reset_cost(p),
        'enemy_codex':(p.stats or {}).get('_enemy_codex',{}),
        'gear':gear_list(db,p.id),'gear_stats':gear_stats(db,p.id),
        'hp':p.hp,'max_hp':max_hp(p),'stamina':p.stamina,'max_stamina':500,'hunger':p.hunger,'thirst':p.thirst,'caps':p.caps,
        'zombo':p.zombo,'location':p.location,'kills':p.kills,'rating':p.rating,'karma':p.karma,'clan_id':p.clan_id,'pvp_wins':p.pvp_wins,
        'last_daily':p.last_daily,'vip_until':aware(p.vip_until).isoformat() if p.vip_until else None,'xp_boost_until':aware(p.xp_boost_until).isoformat() if p.xp_boost_until else None,'loot_boost_until':aware(p.loot_boost_until).isoformat() if p.loot_boost_until else None,'battle':battle_view(battle),'inventory':[{'key':i.item_key,'qty':i.quantity,'equipped':i.equipped,**ITEMS[i.item_key]} for i in inv if i.item_key in ITEMS]}

def battle_view(b):
    if not b:return None
    public_log=[v for v in (b.log or []) if not v.startswith('!ability:')]
    used={}
    for v in (b.log or []):
        if v.startswith('!ability:'):
            try:
                _,key,turn=v.split(':');used[key]=int(turn)
            except (ValueError,TypeError):pass
    key, enemy = enemy_info(b.kind)
    return {'id':b.id,'enemy':b.enemy,'enemy_id':key,'enemy_type':enemy['family'],'trait':enemy['trait'],'skill':enemy['skill'],'tier':enemy['tier'],'lore':enemy['lore'],'hp':b.enemy_hp,'max_hp':b.enemy_max_hp,'turn':b.turn,
            'log':public_log[-6:],'incoming_special':enemy['trait'] not in ('none','armor') and (b.turn+1)%3==0,
            'tactics':ENEMY_TACTICS[key],'ability_cooldowns':{key:max(0,3-(b.turn-turn)) for key,turn in used.items()}}

def attack_power(db,p):
    weapon=db.scalar(select(ItemStack).where(ItemStack.player_id==p.id,ItemStack.equipped==True,ItemStack.item_key.in_(['knife','pistol','rifle'])))
    w=ITEMS[weapon.item_key]['power'] if weapon else 3
    from gear import gear_stats
    w=gear_stats(db,p.id)['power'] or w
    cls=CLASSES.get(p.hero_class,CLASSES['soldier'])
    return max(1,int((7+p.level*2+p.stats.get('strength',0)*2+w)*cls['power']*(1+talent_bonus(p,'power'))))

def combat_round(db,p,b,action,zone='body'):
    if action not in ('attack','medkit','flee','defend','skill'):raise ValueError('Неизвестное действие')
    if action=='flee':
        db.delete(b)
        return {'finished':True,'won':False,'fled':True,'message':'Удалось ускользнуть от заражённого'}
    extra_dodge=0
    if action=='medkit':
        take_item(db,p.id,'medkit')
        heal=int(45*CLASSES[p.hero_class]['healing']*(1+talent_bonus(p,'healing')))
        p.hp=min(max_hp(p),p.hp+heal)
        msg=f'Использована аптечка: +{heal} HP'
    elif action=='defend':msg='Защитная стойка: урон противника уменьшен'
    else:
        if action=='skill':
            node=talent_node(p.hero_class,zone)
            if not node or node['kind']!='active' or not talent_rank(p,zone):raise ValueError('Активный навык не изучен')
            for entry in b.log or []:
                if entry.startswith(f'!ability:{zone}:'):
                    try:old_turn=int(entry.rsplit(':',1)[-1])
                    except ValueError:continue
                    if b.turn-old_turn<3:raise ValueError(f'Навык восстанавливается: {3-(b.turn-old_turn)} ход.')
            spend_stamina(p,6)
            b.log=[*(b.log or []),'!ability:'+zone+':'+str(b.turn)]
            rank=talent_rank(p,zone)
        else:
            if zone not in ('head','body','legs'):raise ValueError('Неверная зона')
            spend_stamina(p,2)
            rank=0
        accuracy={'head':.68,'body':.94,'legs':.99}.get(zone,.96)+p.stats.get('accuracy',0)*.005+talent_bonus(p,'accuracy')
        damage_multiplier={'head':1.5,'body':1.0,'legs':.7}.get(zone,1.0)
        if action=='skill':
            if p.hero_class=='medic':
                heal=int((36+rank*18)*(1+talent_bonus(p,'healing')))
                p.hp=min(max_hp(p),p.hp+heal)
                damage_multiplier=.65
                extra_dodge=.08
                msg=f'✚ Второе дыхание: +{heal} HP. '
            elif p.hero_class=='soldier':
                damage_multiplier=1.65+rank*.3
                msg='⚔ Двойной выстрел! '
            elif p.hero_class=='assassin':
                damage_multiplier=1.75+rank*.30
                msg='☠ Шквал клинков! '
            else:
                damage_multiplier=1.0+rank*.25
                extra_dodge=.5+rank*.08
                msg='◈ Дымовая завеса! '
        else:msg=''
        d=max(1,int(attack_power(db,p)*damage_multiplier*random.uniform(.8,1.2)))
        if random.random()>min(.99,accuracy):d=0
        crit=random.random()<min(.75,CLASSES[p.hero_class]['crit']+p.stats.get('agility',0)*.004+talent_bonus(p,'crit')+(0.13 if action=='skill' and p.hero_class=='assassin' else 0))
        if crit:d*=2
        if b.enemy_hp<=b.enemy_max_hp*.35:d=int(d*(1+talent_bonus(p,'execute')))
        enemy_key, enemy = enemy_info(b.kind)
        if enemy['armor'] and d:
            # Headshots exploit gaps in bone plating; legs are easier to reach.
            plating = enemy['armor'] * (.45 if zone=='head' else .75 if zone=='legs' else 1.0)
            d=max(1,round(d*(1-plating)))
        b.enemy_hp=max(0,b.enemy_hp-d)
        if d and talent_bonus(p,'lifesteal'):
            leech=max(1,int(d*talent_bonus(p,'lifesteal')))
            p.hp=min(max_hp(p),p.hp+leech)
        if action=='attack':msg+=f"Удар {dict(head='в голову',body='в тело',legs='по ногам')[zone]}"
        msg+=f": {d} урона"+(' · КРИТ!' if crit and d else '')
    if b.enemy_hp<=0:
        enemy_key, enemy = enemy_info(b.kind)
        p.kills+=1
        first_discovery=record_enemy(p,enemy_key,defeated=True)
        xp=int((35+b.enemy_max_hp*.3)*enemy['reward']*random.uniform(.85,1.15))
        caps=int((random.randint(9,32)+b.enemy_damage)*enemy['reward']*(1+talent_bonus(p,'caps')))
        if first_discovery:
            xp+=25
            caps+=15
        xp_levels=gain_xp(p,xp)
        # Territorial tribute comes from the zombie reward, not from thin air.
        from clan_wars import zombie_tax
        territorial_tax=zombie_tax(db,p,caps)
        p.caps+=caps-territorial_tax
        loot=[]
        loot_bonus=2 if p.loot_boost_until and aware(p.loot_boost_until)>now() else 1
        if random.random()<min(.98,.44*CLASSES[p.hero_class]['loot']*loot_bonus+talent_bonus(p,'loot')):
            pool=['wood','cloth','metal','food','water','medkit','wire']
            key=random.choice(pool);give_item(db,p.id,key);loot.append(key)
            progress(db,p.id,'scavenge')
        # Individually rolled rarity/level gear enters a separate persistent collection.
        from gear import roll_drop,gear_view
        rare_drop=None
        threat=LOCATIONS.get(p.location,{}).get('threat',1)
        if random.random()<min(.20,.055+.023*threat):
            try:
                rare_drop=gear_view(roll_drop(db,p.id,threat))
            except ValueError:pass  # A full gear locker must never cancel a won battle.
        progress(db,p.id,'kills')
        db.delete(b)
        return {'finished':True,'won':True,'message':f'Победа! +{xp} XP, +{caps-territorial_tax} крышек'+(f' · Налог территории: {territorial_tax}' if territorial_tax else '')+(' · Новый уровень!' if xp_levels else '')+(' · Новый вид в бестиарии: +25 XP, +15 крышек' if first_discovery else '')+(' · Найдена экипировка: '+rare_drop['rarity_name']+' '+rare_drop['name'] if rare_drop else ''),'gear_drop':rare_drop,'loot':loot,'tax':territorial_tax,'new_species':first_discovery}
    enemy_key, enemy = enemy_info(b.kind)
    defense=db.scalar(select(ItemStack).where(ItemStack.player_id==p.id,ItemStack.equipped==True,ItemStack.item_key=='vest'))
    from gear import gear_stats
    extra_defense=gear_stats(db,p.id)['defense']
    raw=max(1,b.enemy_damage+random.randint(-3,5)-(4 if defense else 0)-extra_defense-(8 if action=='defend' else 0))
    # Every third attack applies the enemy's distinctive attack pattern.
    special = (b.turn+1) % 3 == 0
    if special and enemy['trait'] in ('frenzy','acid','smash','howl','ambush'):
        raw=max(1,round(raw*{'frenzy':1.45,'acid':1.28,'smash':1.60,'howl':1.20,'ambush':1.36}[enemy['trait']]))
        # Defending in the telegraphed turn halves the special's raw damage.
        if action=='defend':raw=max(1,raw//2)
    evade_chance=min(.7,talent_bonus(p,'dodge')+extra_dodge)
    evaded=random.random()<evade_chance
    received=0 if evaded else max(1,round(raw*(1-min(.70,talent_bonus(p,'mitigation')+talent_bonus(p,'armor')))))
    p.hp=max(0,p.hp-received)
    drained=0
    if special and not evaded and action!='defend' and enemy['trait'] in ('acid','howl'):
        drained=min(p.stamina,6 if enemy['trait']=='acid' else 4)
        p.stamina-=drained
    b.turn+=1
    if special and enemy['trait'] not in ('none','armor'):
        msg+=' · '+enemy['skill']+'!'
        if action=='defend':msg+=' · Успешный блок'
        if drained:msg+=f' · −{drained} энергии'
    b.log=[*(b.log or [])[-20:],msg,('↝ Уклонение! Урон не получен' if evaded else f'{b.enemy} наносит {received} урона')]
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
    key=choose_enemy(threat)
    enemy=ENEMIES[key]
    hp=max(15,int((30+threat*18+random.randint(0,20))*enemy['hp']))
    damage=max(2,int((3+threat*3)*enemy['damage']))
    b=Battle(player_id=p.id,kind='zombie:'+key,enemy=enemy['name'],enemy_hp=hp,enemy_max_hp=hp,enemy_damage=damage,log=['Вдалеке слышен хрип...'])
    db.add(b);db.flush()
    record_enemy(p,key)
    return battle_view(b)

def boss_sync(db):
    b=db.scalar(select(WorldBoss).where(WorldBoss.id==1).with_for_update())
    if not b:
        # Multiple workers may receive the first request together. Insert one
        # row and then lock it, rather than letting a duplicate insert fail.
        dialect=db.get_bind().dialect.name
        if dialect=='postgresql':
            from sqlalchemy.dialects.postgresql import insert
        elif dialect=='sqlite':
            from sqlalchemy.dialects.sqlite import insert
        else:
            raise RuntimeError('World boss requires PostgreSQL or SQLite')
        db.execute(insert(WorldBoss).values(id=1,name='Гниющий колосс',hp=500000,
                    max_hp=500000,spawn_at=now()).on_conflict_do_nothing(index_elements=['id']))
        b=db.scalar(select(WorldBoss).where(WorldBoss.id==1).with_for_update())
    stamp=now()
    if stamp-aware(b.spawn_at)>timedelta(days=3):
        b.spawn_at=stamp;b.hp=b.max_hp
    return b
