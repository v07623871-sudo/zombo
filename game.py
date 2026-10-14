import random, math
from datetime import timedelta, datetime
from sqlalchemy import select, func
from models import now, Player, ItemStack, Battle, WorldBoss, BossHit, QuestProgress, Territory
from armory_content import NEW_ITEM_DESCRIPTIONS, NEW_RECIPES, CASES
from premium_chests import EXTRA_SUPPLIES, CHESTS
from legendary_ammo import AMMO_KEY, AMMO_ITEM, AMMO_RECIPE, AMMO_SHOP_PRICE, spend_legendary_round, ammo_message

CLASSES = {
    'medic': {'name':'Врач','icon':'✚','subtitle':'Медик отряда','color':'#6dc7ba','bonus':'Лечение ×2 · регенерация 5% HP/ход','power':1.00,'healing':2.0,'loot':1.0,'crit':0.05,'hp':110},
    'soldier': {'name':'Коп','icon':'✦','subtitle':'Стальная дисциплина','color':'#8db4e2','bonus':'Урон ×1.15 · крепкая броня','power':1.15,'healing':1.0,'loot':1.0,'crit':0.08,'hp':125},
    'assassin': {'name':'Убийца','icon':'⚔','subtitle':'Бесшумная смерть','color':'#ec8d83','bonus':'Урон ×1.25 · крит · −10% входящего урона','power':1.25,'healing':0.7,'loot':1.0,'crit':0.18,'hp':95,'mitigation':.10},
    'thief': {'name':'Вор','icon':'◈','subtitle':'Тень пустоши','color':'#d8b66f','bonus':'Добыча ×1.80 · +25% уклонения','power':0.9,'healing':1.1,'loot':1.8,'crit':0.10,'hp':100,'dodge':.25},
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
# Workshop content: 35 new recipes plus 5 originals = 40 usable crafts.
ITEMS.update({
  "bat": {
    "name": "Бита",
    "icon": "🏏",
    "type": "weapon",
    "power": 6,
    "desc": "Оружие: +6 урона"
  },
  "crowbar": {
    "name": "Лом",
    "icon": "🔧",
    "type": "weapon",
    "power": 11,
    "desc": "Оружие: +11 урона"
  },
  "axe": {
    "name": "Топор",
    "icon": "🪓",
    "type": "weapon",
    "power": 15,
    "desc": "Оружие: +15 урона"
  },
  "machete": {
    "name": "Мачете",
    "icon": "🗡️",
    "type": "weapon",
    "power": 18,
    "desc": "Оружие: +18 урона"
  },
  "revolver": {
    "name": "Револьвер",
    "icon": "🔫",
    "type": "weapon",
    "power": 20,
    "desc": "Оружие: +20 урона"
  },
  "crossbow": {
    "name": "Арбалет",
    "icon": "🏹",
    "type": "weapon",
    "power": 23,
    "desc": "Оружие: +23 урона"
  },
  "smg": {
    "name": "Пистолет-пулемёт",
    "icon": "🔫",
    "type": "weapon",
    "power": 26,
    "desc": "Оружие: +26 урона"
  },
  "shotgun": {
    "name": "Дробовик",
    "icon": "🔫",
    "type": "weapon",
    "power": 29,
    "desc": "Оружие: +29 урона"
  },
  "sniper": {
    "name": "Снайперская винтовка",
    "icon": "🎯",
    "type": "weapon",
    "power": 40,
    "desc": "Оружие: +40 урона"
  },
  "spear": {
    "name": "Копьё",
    "icon": "🔱",
    "type": "weapon",
    "power": 13,
    "desc": "Оружие: +13 урона"
  },
  "hunting_bow": {
    "name": "Охотничий лук",
    "icon": "🏹",
    "type": "weapon",
    "power": 18,
    "desc": "Оружие: +18 урона"
  },
  "chainsaw": {
    "name": "Бензопила",
    "icon": "⚙️",
    "type": "weapon",
    "power": 36,
    "desc": "Оружие: +36 урона"
  },
  "light_coat": {
    "name": "Защитный плащ",
    "icon": "🧥",
    "type": "armor",
    "power": 2,
    "desc": "Броня: +2 защиты"
  },
  "padded_armor": {
    "name": "Усиленная куртка",
    "icon": "🛡️",
    "type": "armor",
    "power": 3,
    "desc": "Броня: +3 защиты"
  },
  "riot_armor": {
    "name": "Броня спецназа",
    "icon": "🛡️",
    "type": "armor",
    "power": 8,
    "desc": "Броня: +8 защиты"
  },
  "hazmat_armor": {
    "name": "Костюм химзащиты",
    "icon": "☣️",
    "type": "armor",
    "power": 7,
    "desc": "Броня: +7 защиты"
  },
  "exosuit": {
    "name": "Экзоскелет",
    "icon": "🤖",
    "type": "armor",
    "power": 14,
    "desc": "Броня: +14 защиты"
  },
  "leather_armor": {
    "name": "Кожаный жилет",
    "icon": "🧥",
    "type": "armor",
    "power": 5,
    "desc": "Броня: +5 защиты"
  },
  "hardened_vest": {
    "name": "Укреплённый бронежилет",
    "icon": "🛡️",
    "type": "armor",
    "power": 6,
    "desc": "Броня: +6 защиты"
  },
  "tactical_armor": {
    "name": "Тактическая броня",
    "icon": "🛡️",
    "type": "armor",
    "power": 10,
    "desc": "Броня: +10 защиты"
  },
  "bandage": {
    "name": "Бинт",
    "icon": "🩹",
    "type": "consumable",
    "desc": "Восстанавливает 22 HP"
  },
  "trauma_kit": {
    "name": "Военная аптечка",
    "icon": "🧰",
    "type": "consumable",
    "desc": "Восстанавливает 100 HP"
  },
  "stimulant": {
    "name": "Стимулятор",
    "icon": "💉",
    "type": "consumable",
    "desc": "Восстанавливает 45 энергии"
  },
  "adrenaline": {
    "name": "Адреналин",
    "icon": "⚡",
    "type": "consumable",
    "desc": "Восстанавливает 90 энергии и 10 HP"
  },
  "ration": {
    "name": "Полевой паёк",
    "icon": "🥫",
    "type": "consumable",
    "desc": "Снижает голод на 60 и жажду на 35"
  },
  "electrolyte": {
    "name": "Электролит",
    "icon": "🧃",
    "type": "consumable",
    "desc": "Снижает жажду на 55, +15 энергии"
  },
  "sealed_ration": {
    "name": "Запаянный рацион",
    "icon": "🍲",
    "type": "consumable",
    "desc": "Снижает голод на 80"
  },
  "water_filter": {
    "name": "Фильтрованная вода",
    "icon": "💧",
    "type": "consumable",
    "desc": "Снижает жажду на 75"
  }
})
CONSUMABLE_EFFECTS = {
  "medkit": {
    "hp": 45
  },
  "food": {
    "hunger": 40
  },
  "water": {
    "thirst": 45
  },
  "bandage": {
    "hp": 22
  },
  "trauma_kit": {
    "hp": 100
  },
  "stimulant": {
    "stamina": 45
  },
  "adrenaline": {
    "stamina": 90,
    "hp": 10
  },
  "ration": {
    "hunger": 60,
    "thirst": 35
  },
  "electrolyte": {
    "thirst": 55,
    "stamina": 15
  },
  "sealed_ration": {
    "hunger": 80
  },
  "water_filter": {
    "thirst": 75
  }
}

ITEMS[AMMO_KEY]=AMMO_ITEM
ITEMS.update(NEW_ITEM_DESCRIPTIONS)
ITEMS.update({key:{'name':data['name'],'icon':data['icon'],'type':'case',
                   'desc':data['desc']} for key,data in CASES.items()})
ITEMS.update({key:{'name':data['name'],'icon':data['icon'],'type':'chest',
                   'desc':data['description']} for key,data in CHESTS.items()})
ITEMS.update({key:{'name':data['name'],'icon':data['icon'],'type':data['type'],
                   'desc':data['desc']} for key,data in EXTRA_SUPPLIES.items()})

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
SHOP_PRICES = {'medkit':55,'food':25,'water':20,'knife':80,'vest':300,'pistol':420}
STAMINA_REGEN_PER_TICK = 5  # 5 / 5 min ≈ 60/hour; a usable free-player economy.

RECIPES.update({
  "bat": {
    "qty": 1,
    "cost": {
      "wood": 5,
      "cloth": 1
    }
  },
  "crowbar": {
    "qty": 1,
    "cost": {
      "metal": 5,
      "wood": 2
    }
  },
  "axe": {
    "qty": 1,
    "cost": {
      "metal": 9,
      "wood": 5
    }
  },
  "machete": {
    "qty": 1,
    "cost": {
      "metal": 10,
      "cloth": 5
    }
  },
  "revolver": {
    "qty": 1,
    "cost": {
      "metal": 14,
      "wire": 4,
      "rubber": 2
    }
  },
  "crossbow": {
    "qty": 1,
    "cost": {
      "wood": 12,
      "wire": 7,
      "cloth": 6
    }
  },
  "smg": {
    "qty": 1,
    "cost": {
      "metal": 22,
      "wire": 14,
      "rubber": 8
    }
  },
  "shotgun": {
    "qty": 1,
    "cost": {
      "metal": 26,
      "wood": 8,
      "wire": 8,
      "rubber": 4
    }
  },
  "sniper": {
    "qty": 1,
    "cost": {
      "metal": 45,
      "wire": 22,
      "rubber": 10,
      "rare": 3
    }
  },
  "spear": {
    "qty": 1,
    "cost": {
      "wood": 12,
      "metal": 5
    }
  },
  "hunting_bow": {
    "qty": 1,
    "cost": {
      "wood": 10,
      "cloth": 6,
      "wire": 4
    }
  },
  "chainsaw": {
    "qty": 1,
    "cost": {
      "metal": 30,
      "rubber": 14,
      "wire": 20,
      "rare": 2
    }
  },
  "light_coat": {
    "qty": 1,
    "cost": {
      "cloth": 8,
      "rubber": 2
    }
  },
  "padded_armor": {
    "qty": 1,
    "cost": {
      "cloth": 10,
      "metal": 5
    }
  },
  "riot_armor": {
    "qty": 1,
    "cost": {
      "metal": 22,
      "cloth": 16,
      "rubber": 7
    }
  },
  "hazmat_armor": {
    "qty": 1,
    "cost": {
      "rubber": 18,
      "cloth": 15,
      "wire": 8,
      "rare": 1
    }
  },
  "exosuit": {
    "qty": 1,
    "cost": {
      "metal": 50,
      "wire": 35,
      "rubber": 20,
      "rare": 6
    }
  },
  "leather_armor": {
    "qty": 1,
    "cost": {
      "cloth": 10,
      "rubber": 8
    }
  },
  "hardened_vest": {
    "qty": 1,
    "cost": {
      "metal": 14,
      "cloth": 8
    }
  },
  "tactical_armor": {
    "qty": 1,
    "cost": {
      "metal": 32,
      "cloth": 16,
      "rubber": 10,
      "rare": 2
    }
  },
  "bandage": {
    "qty": 1,
    "cost": {
      "cloth": 2
    }
  },
  "trauma_kit": {
    "qty": 1,
    "cost": {
      "cloth": 6,
      "rubber": 2,
      "rare": 1
    }
  },
  "stimulant": {
    "qty": 1,
    "cost": {
      "food": 1,
      "water": 1,
      "wire": 1
    }
  },
  "adrenaline": {
    "qty": 1,
    "cost": {
      "medkit": 1,
      "food": 1,
      "rubber": 1,
      "rare": 1
    }
  },
  "ration": {
    "qty": 1,
    "cost": {
      "food": 2,
      "water": 1,
      "cloth": 1
    }
  },
  "electrolyte": {
    "qty": 1,
    "cost": {
      "water": 1,
      "food": 1,
      "metal": 1
    }
  },
  "sealed_ration": {
    "qty": 1,
    "cost": {
      "food": 3,
      "cloth": 2,
      "wood": 1
    }
  },
  "water_filter": {
    "qty": 1,
    "cost": {
      "water": 1,
      "cloth": 1,
      "metal": 1
    }
  },
  "bandage_bundle": {
    "name": "Набор бинтов",
    "output": "bandage",
    "qty": 4,
    "cost": {
      "cloth": 7
    }
  },
  "medkit_bundle": {
    "name": "Медицинская коробка",
    "output": "medkit",
    "qty": 3,
    "cost": {
      "cloth": 5,
      "wood": 3
    }
  },
  "ration_bundle": {
    "name": "Паёк для отряда",
    "output": "ration",
    "qty": 3,
    "cost": {
      "food": 5,
      "water": 3,
      "cloth": 3
    }
  },
  "stimulant_bundle": {
    "name": "Стимуляторы для отряда",
    "output": "stimulant",
    "qty": 3,
    "cost": {
      "food": 3,
      "water": 3,
      "wire": 2
    }
  },
  "electrolyte_bundle": {
    "name": "Электролиты для отряда",
    "output": "electrolyte",
    "qty": 3,
    "cost": {
      "water": 3,
      "food": 3,
      "metal": 2
    }
  },
  "water_filter_bundle": {
    "name": "Фильтры для отряда",
    "output": "water_filter",
    "qty": 3,
    "cost": {
      "water": 3,
      "cloth": 2,
      "metal": 3
    }
  },
  "sealed_ration_bundle": {
    "name": "Склад сухпайков",
    "output": "sealed_ration",
    "qty": 3,
    "cost": {
      "food": 8,
      "cloth": 6,
      "wood": 3
    }
  }
})

RECIPES[AMMO_KEY]=AMMO_RECIPE
SHOP_PRICES[AMMO_KEY]=AMMO_SHOP_PRICE
RECIPES.update(NEW_RECIPES)
RECIPES.update({key:data['recipe'] for key,data in EXTRA_SUPPLIES.items()})
SHOP_PRICES.update({key:data['caps'] for key,data in EXTRA_SUPPLIES.items() if 'caps' in data})
CONSUMABLE_EFFECTS.update({key:data['effect'] for key,data in EXTRA_SUPPLIES.items()})

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

# An elite roll is stored in Battle.log for the entire fight. Old battles have
# no marker and keep their original rules; no column or asset migration is needed.
ELITE_MODIFIERS = {
    'armor': {'name':'Костяная броня','hint':'Дополнительная защита; целься в голову или ноги.'},
    'frenzy': {'name':'Бешенство','hint':'Каждый ответный удар заражённого сильнее.'},
    'venom': {'name':'Яд','hint':'Каждый третий удар отнимает энергию. Защита спасает от яда.'},
    'regen': {'name':'Регенерация','hint':'Восстанавливает здоровье после своего хода.'},
}

def choose_elite_modifier(threat, rng=None):
    rng = rng or random
    if threat < 2 or rng.random() >= min(.09, .03 + threat * .01):
        return None
    return rng.choice(tuple(ELITE_MODIFIERS))

def elite_modifier(b):
    for entry in b.log or []:
        if entry.startswith('!elite:'):
            key = entry[7:]
            return key if key in ELITE_MODIFIERS else None
    return None

def choose_enemy(threat, rng=None):
    rng = rng or random
    # Avoid fighting upper-tier enemies in early zones.
    eligible = [(key, data) for key, data in ENEMIES.items() if data['min_threat'] <= threat and data['tier'] <= min(5, threat + 1)]
    weights = [max(1, 6-abs(data['tier'] - threat)*2) for _, data in eligible]
    return rng.choices([key for key, _ in eligible], weights=weights, k=1)[0]

def enemy_info(kind):
    key = kind.split(':',1)[1] if kind.startswith('zombie:') else 'walker'
    return (key if key in ENEMIES else 'walker'), ENEMIES.get(key, ENEMIES['walker'])


# Six permanent companions. Saved in Player.stats JSON, no schema migration.
PETS = {
    'wolf': {'name':'Волк','icon':'🐺','bonus':'power','per_level':.025,'ability':'Укус'},
    'dog': {'name':'Пёс','icon':'🐕','bonus':'dodge','per_level':.020,'ability':'Заслон'},
    'cat': {'name':'Кот','icon':'🐈','bonus':'loot','per_level':.025,'ability':'Кража'},
    'eagle': {'name':'Орёл','icon':'🦅','bonus':'crit','per_level':.012,'ability':'Метка'},
    'boar': {'name':'Кабан','icon':'🐗','bonus':'mitigation','per_level':.015,'ability':'Таран'},
    'raven': {'name':'Ворон','icon':'🐦‍⬛','bonus':'rare','per_level':.007,'ability':'Удача'},
}


def pet_status(p):
    data=(p.stats or {}).get('_pet')
    if not isinstance(data,dict) or data.get('key') not in PETS:return None
    level=max(1,min(10,int(data.get('level',1))))
    return {'key':data['key'],'level':level,'xp':max(0,int(data.get('xp',0))),
            'xp_next':level*5 if level<10 else 0,**PETS[data['key']]}


def pet_bonus(p,effect):
    pet=pet_status(p)
    return pet['per_level']*pet['level'] if pet and pet['bonus']==effect else 0


def pet_victory(p):
    """A victory develops an existing companion and cannot exceed level 10."""
    pet=pet_status(p)
    if not pet or pet['level']>=10:return
    level=pet['level'];xp=pet['xp']+1
    if xp>=level*5:
        xp-=level*5;level+=1
    data=dict(p.stats or {})
    data['_pet']={'key':pet['key'],'level':level,'xp':xp}
    p.stats=data


def pet_try_find(p):
    """0.5% companion find on the first eligible won PvE battle."""
    if pet_status(p) or random.random()>=.005:return None
    key=random.choice(tuple(PETS))
    data=dict(p.stats or {})
    data['_pet']={'key':key,'level':1,'xp':0}
    p.stats=data
    return key


def pet_combat_action(db,p,b):
    """One manual companion action per encounter; the enemy retaliates normally."""
    pet=pet_status(p)
    if not pet:raise ValueError('Сначала найди питомца')
    if any(entry=='!pet:used' for entry in (b.log or [])):
        raise ValueError('Питомец уже помог в этом бою')
    spend_stamina(p,3)
    b.log=[*(b.log or []),'!pet:used']
    key,level=pet['key'],pet['level']
    damage=0;extra_dodge=0
    msg=pet['icon']+' '+pet['ability']+': '
    if key in ('wolf','boar','eagle'):
        mult={'wolf':.85,'boar':.65,'eagle':.50}[key]
        damage=max(1,round(attack_power(db,p)*mult*(1+level*.05)))
        b.enemy_hp=max(0,b.enemy_hp-damage)
        msg+=f'{damage} урона'
        if key=='boar':extra_dodge=.35
    elif key=='dog':
        healed=min(max_hp(p)-p.hp,10+level*4)
        p.hp+=healed;extra_dodge=.4
        msg+=f'+{healed} HP и заслон'
    elif key=='cat':
        material=random.choice(['wood','metal','cloth','wire','rubber'])
        b.log=[*(b.log or []),'!pet:loot:'+material]
        msg+='найден '+ITEMS[material]['name']+' (заберёшь после победы)'
    else:  # Raven: guaranteed one useful supply rather than unlimited currency.
        material=random.choice(['medkit','water','food','wire'])
        b.log=[*(b.log or []),'!pet:loot:'+material]
        msg+='найден '+ITEMS[material]['name']+' (заберёшь после победы)'
    return msg,extra_dodge


def aware(dt):
    if not dt: return None
    from datetime import timezone
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def max_hp(p): return CLASSES.get(p.hero_class,{}).get('hp',100) + p.stats.get('endurance',0)*5 + (p.level-1)*3 + int(talent_bonus(p,'health'))

def xp_needed(level): return int(150*level**1.75+300*level)

def scavenge_pool(location):
    """Provide rubber, wire and stone in high-threat areas for advanced crafts."""
    loc=LOCATIONS[location]
    pool=[loc['material']]*2+['cloth','food','water','wood','metal']
    if loc['threat']>=3:pool+=['wire','rubber']
    if loc['threat']>=4:pool+=['wire','rubber','stone']
    if loc['threat']>=5:pool+=['rare']
    return pool


def spend_stamina(p, cost):
    tick(p)
    actual=max(1,round(cost*(1-min(.55,talent_bonus(p,'energy')*.45))))
    if p.stamina < actual: raise ValueError(f'Не хватает выносливости. Нужно {actual} ⚡')
    p.stamina -= actual

def tick(p):
    """Regenerate energy every full 5 min and HP every full hour.

    Both clocks keep leftover seconds, including through frequent requests.
    Health uses a separate persisted JSON timestamp so its hourly progress is
    not reset by the five-minute stamina clock. VIP is credited only for
    five-minute intervals actually completed before its expiry.
    """
    current=now()
    last_energy=aware(p.last_tick or current)
    elapsed=max(0,(current-last_energy).total_seconds())
    stamina_ticks=int(elapsed//300)
    if stamina_ticks:
        vip_ticks=0
        if p.vip_until:
            until=aware(p.vip_until)
            vip_ticks=min(stamina_ticks,max(0,int((until-last_energy).total_seconds()//300)))
        units=STAMINA_REGEN_PER_TICK*(stamina_ticks+vip_ticks)
        recovered=max(0,int(units*(1+talent_bonus(p,'energy'))))
        p.stamina=min(500,p.stamina+recovered)
        p.last_tick=last_energy+timedelta(minutes=5*stamina_ticks)
    # Initialize the HP clock *once*, before a subsequent stamina tick could
    # move last_tick. This also upgrades existing characters in place.
    values=dict(p.stats or {})
    try:
        hp_clock=aware(datetime.fromisoformat(values['_hp_regen_at']))
    except (ValueError,KeyError,TypeError):
        hp_clock=last_energy
    hours=int(max(0,(current-hp_clock).total_seconds())//3600)
    if hours:
        per_hour=max(0,1+int(values.get('regen',0))+int(talent_bonus(p,'regen')))
        p.hp=min(max_hp(p),p.hp+hours*per_hour)
        hp_clock+=timedelta(hours=hours)
    # Preserve the marker even if no full hour has elapsed. Otherwise repeated
    # 5-minute polls would keep restarting the first hour.
    stamp=hp_clock.isoformat()
    if values.get('_hp_regen_at')!=stamp:
        values['_hp_regen_at']=stamp
        p.stats=values

def insurance_active(p, *, at=None):
    """Whether purchased one-day protection still covers this character."""
    raw=(p.stats or {}).get('_insurance_until')
    if not isinstance(raw,str):return False
    try:return aware(datetime.fromisoformat(raw))>(at or now())
    except ValueError:return False


def death_penalty(db,p):
    """Apply the documented death sink once, within the fight transaction.

    Ordinary non-equipped supplies are at risk; premium boxes, equipped
    weapons and unique gear are protected to avoid deleting paid assets.
    """
    protected=insurance_active(p)
    caps_percent=.05 if protected else .20
    xp_percent=.10 if protected else .30
    items_percent=.10 if protected else .50
    lost_caps=min(p.caps,int(max(0,p.caps)*caps_percent))
    lost_xp=int(max(0,p.xp)*xp_percent)
    p.caps-=lost_caps
    p.xp=max(0,p.xp-lost_xp)
    # An unopened case/chest was bought for Zombo. Losing it through
    # ordinary PvE death would erase paid goods before they can be opened.
    # Unique GearItem is already protected because it is not ItemStack.
    premium_keys=set(CASES)|set(CHESTS)
    stacks=list(db.scalars(select(ItemStack).where(
        ItemStack.player_id==p.id,ItemStack.equipped.is_(False),
        ItemStack.item_key.notin_(premium_keys))
        .order_by(ItemStack.item_key,ItemStack.id).with_for_update()))
    at_risk=sum(max(0,s.quantity) for s in stacks)
    left=int(at_risk*items_percent)
    removed=0
    for stack in stacks:
        if not left:break
        count=min(left,max(0,stack.quantity))
        if not count:continue
        left-=count
        removed+=count
        if count==stack.quantity:db.delete(stack)
        else:stack.quantity-=count
    return {'caps':lost_caps,'xp':lost_xp,'items':removed,'insured':protected}


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
    # SessionLocal has autoflush=False: a prior grant in this same transaction
    # can still be pending and is invisible to SELECT. Reuse its ORM object
    # instead of inserting a second row and violating unique_inventory_stack.
    stack=next((x for x in db.new if isinstance(x,ItemStack)
                and x.player_id==pid and x.item_key==key and not x.equipped),None)
    if stack is None:
        stack=db.scalar(select(ItemStack).where(ItemStack.player_id==pid,
                         ItemStack.item_key==key,ItemStack.equipped==False).with_for_update())
    if stack:stack.quantity+=qty
    else:db.add(ItemStack(player_id=pid,item_key=key,quantity=qty,equipped=False))

def take_item(db,pid,key,qty=1):
    if qty<=0:raise ValueError('Недостаточно предметов')
    stack=db.scalar(select(ItemStack).where(ItemStack.player_id==pid,ItemStack.item_key==key,ItemStack.equipped==False).with_for_update())
    if not stack or stack.quantity<qty:raise ValueError('Недостаточно предметов')
    stack.quantity-=qty
    if stack.quantity==0:db.delete(stack)

def progress(db,pid,code,qty=1):
    q=db.scalar(select(QuestProgress).where(QuestProgress.player_id==pid,QuestProgress.code==code).with_for_update())
    if not q:
        q=QuestProgress(player_id=pid,code=code,amount=0)
        db.add(q)
    q.amount+=qty
    # Server-side clan objectives advance only after a real, committed game event.
    from clan_missions import record_clan_progress
    record_clan_progress(db,pid,code,qty)

def player_view(db,p):
    from gear import gear_list,gear_stats
    tick(p)
    inv=db.scalars(select(ItemStack).where(ItemStack.player_id==p.id).order_by(ItemStack.equipped.desc(),ItemStack.item_key)).all()
    battle=db.scalar(select(Battle).where(Battle.player_id==p.id))
    from pvp_rating import league
    return {'id':p.id,'name':p.name,'username':p.username,'class':p.hero_class,'level':p.level,'xp':p.xp,'xp_next':xp_needed(p.level),'league':league(p.rating),
        'stats':p.stats,'skills':p.skills,'stat_points':p.stat_points,'skill_points':p.skill_points,
        'talent_ranks':{n['key']:talent_rank(p,n['key']) for br in SKILL_TREES.get(p.hero_class,[]) for n in br['nodes']},
        'talent_bonuses':talent_bonuses(p),'talent_spent':len(p.skills or []),
        'talent_reset_cost':talent_reset_cost(p),
        'pet':pet_status(p),
        'enemy_codex':(p.stats or {}).get('_enemy_codex',{}),
        'gear':gear_list(db,p.id),'gear_stats':gear_stats(db,p.id),
        'hp':p.hp,'max_hp':max_hp(p),'stamina':p.stamina,'max_stamina':500,'hunger':p.hunger,'thirst':p.thirst,'caps':p.caps,
        'zombo':p.zombo,'location':p.location,'kills':p.kills,'rating':p.rating,'karma':p.karma,'clan_id':p.clan_id,'pvp_wins':p.pvp_wins,
        'last_daily':p.last_daily,'vip_until':aware(p.vip_until).isoformat() if p.vip_until else None,'xp_boost_until':aware(p.xp_boost_until).isoformat() if p.xp_boost_until else None,'loot_boost_until':aware(p.loot_boost_until).isoformat() if p.loot_boost_until else None,'battle':battle_view(battle),'inventory':[{'key':i.item_key,'qty':i.quantity,'equipped':i.equipped,**ITEMS[i.item_key]} for i in inv if i.item_key in ITEMS]}

def battle_view(b):
    if not b:return None
    public_log=[v for v in (b.log or []) if not v.startswith(('!ability:', '!elite:', '!pet:'))]
    used={}
    for v in (b.log or []):
        if v.startswith('!ability:'):
            try:
                _,key,turn=v.split(':');used[key]=int(turn)
            except (ValueError,TypeError):pass
    key, enemy = enemy_info(b.kind)
    elite=elite_modifier(b)
    return {'id':b.id,'enemy':b.enemy,'enemy_id':key,'enemy_type':enemy['family'],'trait':enemy['trait'],'skill':enemy['skill'],'tier':enemy['tier'],'lore':enemy['lore'],'hp':b.enemy_hp,'max_hp':b.enemy_max_hp,'turn':b.turn,
            'elite':{'key':elite,**ELITE_MODIFIERS[elite]} if elite else None,
            'log':public_log[-6:],'pet_available':not any(x=='!pet:used' for x in (b.log or [])),'incoming_special':(enemy['trait'] not in ('none','armor') or elite=='venom') and (b.turn+1)%3==0,
            'elite_warning':(enemy['skill']+' + ядовитый укус' if enemy['trait'] not in ('none','armor') else 'Ядовитый укус') if elite=='venom' and (b.turn+1)%3==0 else None,
            'tactics':ENEMY_TACTICS[key],'ability_cooldowns':{key:max(0,3-(b.turn-turn)) for key,turn in used.items()}}

def attack_power(db,p,*,ammo_status='normal'):
    weapon=db.scalar(select(ItemStack).where(ItemStack.player_id==p.id,ItemStack.equipped==True,ItemStack.item_key.in_(['knife','pistol','rifle'])))
    w=ITEMS[weapon.item_key]['power'] if weapon else 3
    from gear import gear_stats
    # An empty legendary gun falls back to the survivor's baseline melee hit.
    # Only attacks that actually spend a round gain the legendary gun bonus.
    w=(3 if ammo_status=='empty' else (gear_stats(db,p.id)['power'] or w))
    cls=CLASSES.get(p.hero_class,CLASSES['soldier'])
    return max(1,int((7+p.level*2+p.stats.get('strength',0)*2+w)*cls['power']*(1+talent_bonus(p,'power')+pet_bonus(p,'power'))))

def combat_round(db,p,b,action,zone='body'):
    from gear import wear_equipped
    if action not in ('attack','medkit','flee','defend','skill','pet'):raise ValueError('Неизвестное действие')
    elite=elite_modifier(b)
    if action=='flee':
        spend_stamina(p,2)
        db.delete(b)
        return {'finished':True,'won':False,'fled':True,'message':'Удалось ускользнуть от заражённого'}
    extra_dodge=0
    if action=='medkit':
        take_item(db,p.id,'medkit')
        heal=int(45*CLASSES[p.hero_class]['healing']*(1+talent_bonus(p,'healing')))
        p.hp=min(max_hp(p),p.hp+heal)
        msg=f'Использована аптечка: +{heal} HP'
    elif action=='pet':msg,extra_dodge=pet_combat_action(db,p,b)
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
        accuracy={'head':.68,'body':.94,'legs':.99}.get(zone,.96)+min(.25,max(0,p.stats.get('accuracy',0))*.005)+talent_bonus(p,'accuracy')
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
        ammo_status=spend_legendary_round(db,p.id)
        d=max(1,int(attack_power(db,p,ammo_status=ammo_status)*damage_multiplier*random.uniform(.8,1.2)))
        if random.random()>min(.99,accuracy):d=0
        crit=random.random()<min(.75,CLASSES[p.hero_class]['crit']+p.stats.get('agility',0)*.004+p.stats.get('luck',0)*.003+talent_bonus(p,'crit')+pet_bonus(p,'crit')+(0.13 if action=='skill' and p.hero_class=='assassin' else 0))
        if crit:d*=2
        if b.enemy_hp<=b.enemy_max_hp*.35:d=int(d*(1+talent_bonus(p,'execute')))
        enemy_key, enemy = enemy_info(b.kind)
        plating_amount=min(.55,enemy['armor']+(.22 if elite=='armor' else 0))
        if plating_amount and d:
            # Headshots exploit gaps in bone plating; legs are easier to reach.
            plating = plating_amount * (.45 if zone=='head' else .75 if zone=='legs' else 1.0)
            d=max(1,round(d*(1-plating)))
        b.enemy_hp=max(0,b.enemy_hp-d)
        wear_equipped(db,p.id,'weapon',1)
        if d and talent_bonus(p,'lifesteal'):
            leech=max(1,int(d*talent_bonus(p,'lifesteal')))
            p.hp=min(max_hp(p),p.hp+leech)
        if action=='attack':msg+=f"Удар {dict(head='в голову',body='в тело',legs='по ногам')[zone]}"
        msg+=f": {d} урона"+(' · КРИТ!' if crit and d else '')+ammo_message(ammo_status)
    if b.enemy_hp<=0:
        pet_victory(p)
        new_pet=pet_try_find(p)
        enemy_key, enemy = enemy_info(b.kind)
        p.kills+=1
        first_discovery=record_enemy(p,enemy_key,defeated=True)
        xp=int((35+b.enemy_max_hp*.3)*enemy['reward']*random.uniform(.85,1.15))
        caps=int((random.randint(9,32)+b.enemy_damage)*enemy['reward']*(1+talent_bonus(p,'caps')))
        if elite:
            xp=round(xp*1.35)
            caps=round(caps*1.35)
        if first_discovery:
            xp+=25
            caps+=15
        from world_events import record_action as record_world_action
        world_horde=record_world_action(db,p,'horde')
        if world_horde:
            xp+=max(1,xp//5)
            caps+=max(1,caps//5)
        xp_levels=gain_xp(p,xp)
        # Territorial tribute comes from the zombie reward, not from thin air.
        from clan_wars import zombie_tax
        territorial_tax=zombie_tax(db,p,caps)
        p.caps+=caps-territorial_tax
        loot=[]
        # A companion's supply is earned by surviving the encounter; fleeing
        # or dying must not mint free items. Persist pending loot in the
        # battle's server-side log until this transactional victory payout.
        pending=next((line.rsplit(':',1)[-1] for line in (b.log or [])
                      if line.startswith('!pet:loot:')),None)
        if pending in ITEMS:
            give_item(db,p.id,pending,1)
            loot.append(pending)
        loot_bonus=2 if p.loot_boost_until and aware(p.loot_boost_until)>now() else 1
        if random.random()<min(.98,.44*CLASSES[p.hero_class]['loot']*loot_bonus+talent_bonus(p,'loot')+pet_bonus(p,'loot')):
            pool=['wood','cloth','metal','food','water','medkit','wire']
            key=random.choice(pool);give_item(db,p.id,key);loot.append(key)
            progress(db,p.id,'scavenge')
        # High-threat areas provide a modest free source of legendary ammo.
        if threat_level := LOCATIONS.get(p.location,{}).get('threat',1):
            if threat_level>=4 and random.random()<(.07 if threat_level==4 else .12):
                give_item(db,p.id,AMMO_KEY,2)
                loot.extend([AMMO_KEY,AMMO_KEY])
        # Premium cases/chests cannot be earned through PvE.
        # Give independent, low-cost supplies instead so loot stays lively.
        bonus_threat=LOCATIONS.get(p.location,{}).get('threat',1)
        if random.random()<.035+.012*bonus_threat:
            pool=['field_dressing','painkillers','energy_bar','isotonic',
                  'purified_water']+(['energy_cells','military_ration'] if bonus_threat>=3 else [])
            found_supply=random.choice(pool)
            give_item(db,p.id,found_supply)
            loot.append(found_supply)
        # Individually rolled rarity/level gear enters a separate persistent collection.
        from gear import roll_drop,gear_view
        rare_drop=None
        threat=LOCATIONS.get(p.location,{}).get('threat',1)
        if random.random()<min(.30,.055+.023*threat+(.10 if elite else 0)+max(0,p.stats.get('luck',0))*.01+pet_bonus(p,'rare')):
            try:
                rare_drop=gear_view(roll_drop(db,p.id,threat,minimum='uncommon' if elite else 'common'))
            except ValueError:pass  # A full gear locker must never cancel a won battle.
        progress(db,p.id,'kills')
        db.delete(b)
        return {'finished':True,'won':True,'message':f'Победа! +{xp} XP, +{caps-territorial_tax} крышек'+(' · Элитная цель' if elite else '')+(f' · Налог территории: {territorial_tax}' if territorial_tax else '')+(' · Новый уровень!' if xp_levels else '')+(' · Новый вид в бестиарии: +25 XP, +15 крышек' if first_discovery else '')+(' · Найдена экипировка: '+rare_drop['rarity_name']+' '+rare_drop['name'] if rare_drop else ''),'gear_drop':rare_drop,'loot':loot,'tax':territorial_tax,'new_species':first_discovery,'elite':elite,'pet_found':new_pet}
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
    if elite=='frenzy':raw=max(1,round(raw*1.18))
    if p.hero_class=='medic':
        # Baseline class perk: 5% max HP restored during a combat turn.
        healed=min(max_hp(p)-p.hp,max(1,round(max_hp(p)*.05)))
        p.hp+=healed
        if healed:msg+=f' · +{healed} HP (регенерация врача)'
    evade_chance=min(.7,CLASSES[p.hero_class].get('dodge',0)+max(0,p.stats.get('agility',0))*.005+talent_bonus(p,'dodge')+pet_bonus(p,'dodge')+extra_dodge)
    evaded=random.random()<evade_chance
    received=0 if evaded else max(1,round(raw*(1-min(.70,CLASSES[p.hero_class].get('mitigation',0)+pet_bonus(p,'mitigation')+talent_bonus(p,'mitigation')+talent_bonus(p,'armor')))))
    p.hp=max(0,p.hp-received)
    if received:wear_equipped(db,p.id,'armor',1)
    drained=0
    if special and not evaded and action!='defend' and enemy['trait'] in ('acid','howl'):
        drained=min(p.stamina,6 if enemy['trait']=='acid' else 4)
        p.stamina-=drained
    base_drained=drained
    poison=0
    if special and elite=='venom' and not evaded and action!='defend':
        poison=min(p.stamina,8)
        p.stamina-=poison
    b.turn+=1
    if special and enemy['trait'] not in ('none','armor'):
        msg+=' · '+enemy['skill']+'!'
        if action=='defend':msg+=' · Успешный блок'
        if base_drained:msg+=f' · −{base_drained} энергии'
    if special and elite=='venom':
        msg+=' · Ядовитый укус'+(' отражён' if action=='defend' or evaded else f': −{poison} энергии')
    if elite=='regen' and b.enemy_hp>0:
        healed=min(b.enemy_max_hp-b.enemy_hp,max(1,round(b.enemy_max_hp*.06)))
        b.enemy_hp+=healed
        if healed:msg+=f' · Регенерация: +{healed} HP'
    # Keep one-shot pet markers outside the rotating public combat history.
    # Otherwise a long battle evicts !pet:used and allows endless replays.
    pet_markers=[line for line in (b.log or []) if line.startswith('!pet:')]
    history=[line for line in (b.log or [])
             if not line.startswith(('!elite:','!pet:'))]
    b.log=([f'!elite:{elite}'] if elite else [])+pet_markers[:2]+history[-18:]+[
        msg,('↝ Уклонение! Урон не получен' if evaded else f'{b.enemy} наносит {received} урона')]
    if p.hp==0:
        p.hp=max(1,max_hp(p)//2)
        losses=death_penalty(db,p)
        p.location='base'
        p.cooldown=now()+timedelta(seconds=30)
        db.delete(b)
        return {'finished':True,'won':False,'losses':losses,
                'message':f'Ты погибла в пустоши. Потери: {losses["caps"]} крышек, '
                          f'{losses["xp"]} XP и {losses["items"]} припасов.'
                          + (' Страховка сработала!' if losses['insured'] else '')}
    return {'finished':False,'message':msg,'battle':battle_view(b)}

def spawn_battle(db,p):
    if p.location=='base':raise ValueError('Сначала отправься в локацию')
    if db.scalar(select(Battle).where(Battle.player_id==p.id)):
        raise ValueError('Сначала закончи текущий бой')
    if p.hp < 1:raise ValueError('Нужно восстановить здоровье')
    spend_stamina(p,2)
    threat=LOCATIONS[p.location]['threat']
    key=choose_enemy(threat)
    elite=choose_elite_modifier(threat)
    enemy=ENEMIES[key]
    hp=max(15,int((30+threat*18+random.randint(0,20))*enemy['hp']))
    damage=max(2,int((3+threat*3)*enemy['damage']))
    from world_events import active_event
    if active_event(db,p.location,'horde'):
        hp=max(1,round(hp*1.25))
        damage=max(2,round(damage*1.15))
    if elite:
        hp=max(1,round(hp*1.35))
        damage=max(2,round(damage*1.12))
    log=([f'!elite:{elite}'] if elite else [])+['Вдалеке слышен хрип...']
    b=Battle(player_id=p.id,kind='zombie:'+key,enemy=('Элитный ' if elite else '')+enemy['name'],enemy_hp=hp,enemy_max_hp=hp,enemy_damage=damage,log=log)
    db.add(b);db.flush()
    record_enemy(p,key)
    return battle_view(b)

WORLD_BOSS_ROTATION = (
    {'name':'Гниющий колосс','max_hp':500_000,
     'hint':'Массивный заражённый, обрушивающий укрепления.',
     'attack_name':'Костяной удар','attack_kind':'smash','attack_damage':7,
     'mechanic':'Каждый третий удар — сокрушительный.'},
    {'name':'Матерь заражённых','max_hp':1_500_000,
     'hint':'Призывает рой и пожирает целые отряды.',
     'attack_name':'Налёт роя','attack_kind':'swarm','attack_damage':11,
     'mechanic':'Каждый третий удар выжигает 4 энергии.'},
    {'name':'Токсичный исполин','max_hp':3_000_000,
     'hint':'Его тело отравило целый город.',
     'attack_name':'Ядовитый плевок','attack_kind':'venom','attack_damage':15,
     'mechanic':'Каждый третий удар забирает 8 энергии и усиливает жажду.'},
    {'name':'Радиоактивный левиафан','max_hp':6_000_000,
     'hint':'Тяжёлое заражение и радиационная броня.',
     'attack_name':'Радиационный импульс','attack_kind':'radiation','attack_damage':19,
     'mechanic':'Каждый третий удар отнимает энергию, добавляет голод и жажду.'},
    {'name':'Жнец пустоши','max_hp':10_000_000,
     'hint':'Вершина пищевой цепи пустоши.',
     'attack_name':'Казнь','attack_kind':'execute','attack_damage':25,
     'mechanic':'Сильнее бьёт по раненым; каждый третий удар особенно опасен.'},
)


def _award_boss_cycle(db,old_spawn):
    """Grant the top contributor one rolled legendary gear item, exactly once.

    Called only while the sole WorldBoss row is locked and before its timestamp
    advances. Any retries after transaction commit see the new timestamp.
    """
    from gear import create_gear
    from models import Player
    previous=str(int(aware(old_spawn).timestamp()))
    leaders=db.execute(select(BossHit.player_id,func.sum(BossHit.damage))
        .where(BossHit.spawn_at==previous)
        .group_by(BossHit.player_id)
        .order_by(func.sum(BossHit.damage).desc(),BossHit.player_id.asc())
        .limit(1)).all()
    if not leaders or int(leaders[0][1] or 0)<=0:return None
    pid=leaders[0][0]
    winner=db.scalar(select(Player).where(Player.id==pid).with_for_update())
    if not winner:return None
    try:
        create_gear(db,pid,'rifle',rarity='legendary',source='boss')
        result='легендарная винтовка'
    except ValueError:
        # Full item locker: reward non-equippable material instead of silently
        # discarding the whole cycle's top contributor prize.
        give_item(db,pid,'rare',8)
        result='8 военных жетонов (хранилище переполнено)'
    from notifications import queue_notification
    queue_notification(db,pid,f'worldboss:{previous}:top1','raids','world_boss_top1',
       f'🏆 Ты заняла 1-е место по урону мировому боссу! Награда: {result}.')
    return pid


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
        # Only a defeated boss pays a legendary. Without this gate, one low-
        # damage hit per cycle can mint top-tier gear indefinitely.
        if b.hp<=0:
            _award_boss_cycle(db,b.spawn_at)
        # Continue the five-boss loop while preserving the established
        # single-row schema and earlier boss hit history.
        index=next((i for i,config in enumerate(WORLD_BOSS_ROTATION)
                    if config['name']==b.name),0)
        successor=WORLD_BOSS_ROTATION[(index+1)%len(WORLD_BOSS_ROTATION)]
        b.name=successor['name']
        b.max_hp=successor['max_hp']
        b.hp=successor['max_hp']
        # BossHit identifies cycles by epoch second. After manual/test
        # rotations in the same second, reusing it would mix old damage,
        # pay wrong leaders and incorrectly enforce the hit cooldown.
        cycle_start=stamp
        while db.scalar(select(BossHit.id).where(
                BossHit.spawn_at==str(int(cycle_start.timestamp()))).limit(1)):
            cycle_start+=timedelta(seconds=1)
        b.spawn_at=cycle_start
    return b
