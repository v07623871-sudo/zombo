import os, hmac, hashlib, json, random, re, secrets, logging
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl
import httpx
from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import Session
from models import (Base, engine, SessionLocal, now, Player, ItemStack, Battle, Clan, Territory,
                    MarketLot, WorldBoss, BossHit, QuestProgress, PvPMatch, Payment)
from game import (CLASSES, SKILLS, STATS, ITEMS, LOCATIONS, RECIPES, QUESTS, TERRITORIES,
                  aware, max_hp, gain_xp, give_item, take_item, item_count, tick, spend_stamina,
                  player_view, battle_view, combat_round, spawn_battle, attack_power, progress, boss_sync)

logging.basicConfig(level=logging.INFO)
logger=logging.getLogger('zombo')
# Prevent httpx from writing secret Telegram bot tokens embedded in request URLs.
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
BOT_TOKEN=os.getenv('BOT_TOKEN','')
PUBLIC_URL=os.getenv('PUBLIC_URL','').rstrip('/')
SECRET=os.getenv('TELEGRAM_WEBHOOK_SECRET','')
DEMO=os.getenv('DEMO_MODE','0')=='1'
ADMIN_IDS={int(x) for x in os.getenv('ADMIN_IDS','').split(',') if x.strip().isdigit()}

async def telegram_api(method, payload):
    if not BOT_TOKEN: return {'ok':False,'error':'no token'}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r=await client.post(f'https://api.telegram.org/bot{BOT_TOKEN}/{method}',json=payload)
            if r.status_code>=400:logger.error('Telegram %s error %s',method,r.status_code)
            return r.json()
    except Exception:
        logger.exception('Telegram request failed')
        return {'ok':False}

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal.begin() as db:
        for key in TERRITORIES:
            if not db.get(Territory,key):db.add(Territory(id=key))
    if BOT_TOKEN and PUBLIC_URL and SECRET:
        result=await telegram_api('setWebhook',{'url':f'{PUBLIC_URL}/telegram/webhook','secret_token':SECRET,'allowed_updates':['message','pre_checkout_query']})
        logger.info('Webhook configured: %s',bool(result.get('ok')))
        await telegram_api('setChatMenuButton',{'menu_button':{'type':'web_app','text':'Открыть ZOMBO','web_app':{'url':PUBLIC_URL}}})
        await telegram_api('setMyCommands',{'commands':[{'command':'start','description':'Начать игру'},{'command':'profile','description':'Персонаж'},{'command':'daily','description':'Ежедневная награда'},{'command':'help','description':'Как играть'}]})
    yield

app=FastAPI(title='ZOMBO · After the Fall',version='0.1.0',lifespan=lifespan)
app.mount('/static', StaticFiles(directory=os.path.join(os.path.dirname(__file__),'static')),name='static')

@app.get('/health')
def health():return {'status':'ok','game':'ZOMBO','version':'0.1.0'}

@app.get('/')
def home():return FileResponse(os.path.join(os.path.dirname(__file__),'static','index.html'))

@app.middleware('http')
async def secure_headers(request, call_next):
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    response.headers['Cache-Control']='no-store' if request.url.path.startswith('/api/') else 'public, max-age=180'
    return response

@app.exception_handler(ValueError)
async def value_error(_req, exc):return JSONResponse({'detail':str(exc)},status_code=400)

def identify(header):
    if not header:raise HTTPException(401,'Открой игру через Telegram')
    if DEMO and header.startswith('demo:'):
        raw=header[5:]
        if not raw.isdigit():raise HTTPException(401,'Неверный тестовый ID')
        return {'id':int(raw),'first_name':'Исследователь','username':'demo'}
    if not header.startswith('tma '):raise HTTPException(401,'Необходимо открыть Mini App в Telegram')
    if not BOT_TOKEN:raise HTTPException(503,'Бот ещё не настроен')
    pairs=dict(parse_qsl(header[4:],keep_blank_values=True))
    sent=pairs.pop('hash',None)
    if not sent:raise HTTPException(401,'Нет подписи Telegram')
    check='\n'.join(f'{k}={v}' for k,v in sorted(pairs.items()))
    key=hmac.new(b'WebAppData',BOT_TOKEN.encode(),hashlib.sha256).digest()
    expected=hmac.new(key,check.encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sent,expected):raise HTTPException(401,'Неверная подпись Telegram')
    try:
        auth_date=int(pairs.get('auth_date','0'))
        if not 0<=int(now().timestamp())-auth_date<=86400:raise ValueError()
        user=json.loads(pairs['user'])
        if not isinstance(user.get('id'),int):raise ValueError()
        return user
    except (KeyError,ValueError,TypeError,json.JSONDecodeError):raise HTTPException(401,'Устаревшая авторизация. Перезапусти игру')

def db_session():
    with SessionLocal() as db:
        yield db

def get_player(authorization: str=Header(default=''),db:Session=Depends(db_session)):
    user=identify(authorization)
    pid=int(user['id'])
    p=db.scalar(select(Player).where(Player.id==pid).with_for_update())
    if not p:
        name=' '.join(filter(None,[user.get('first_name'),user.get('last_name')]))[:90] or 'Выживший'
        p=Player(id=pid,name=name,username=user.get('username','')[:90],stats={'strength':0,'agility':0,'endurance':0,'accuracy':0,'regen':0,'luck':0},skills=[])
        db.add(p);db.flush()
        for key,qty in [('knife',1),('medkit',2),('food',2),('water',2),('wood',3)]:give_item(db,p.id,key,qty)
    if p.banned:raise HTTPException(403,'Учётная запись заблокирована')
    if p.frozen:raise HTTPException(403,'Персонаж временно заморожен')
    tick(p)
    db.commit()
    return p

def with_player(request:Request, db: Session):
    user=identify(request.headers.get('authorization',''))
    p=db.scalar(select(Player).where(Player.id==int(user['id'])).with_for_update())
    if not p:
        name=' '.join(filter(None,[user.get('first_name'),user.get('last_name')]))[:90] or 'Выживший'
        p=Player(id=int(user['id']),name=name,username=user.get('username','')[:90],stats={k:0 for k in STATS},skills=[])
        db.add(p);db.flush()
        for key,qty in [('knife',1),('medkit',2),('food',2),('water',2),('wood',3)]:give_item(db,p.id,key,qty)
    if p.banned or p.frozen:raise HTTPException(403,'Персонаж заблокирован')
    tick(p)
    return p

@app.get('/api/config')
def config():return {'classes':CLASSES,'skills':SKILLS,'stats':STATS,'items':ITEMS,'locations':LOCATIONS,'recipes':RECIPES,'quests':QUESTS,'territory_names':TERRITORIES}

@app.get('/api/me')
def me(request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db)
        return player_view(db,p)

class Choice(BaseModel):
    key: str = Field(min_length=1,max_length=55)

@app.post('/api/class')
def choose_class(body:Choice,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db)
        if p.hero_class:raise ValueError('Класс выбирается один раз')
        if body.key not in CLASSES:raise ValueError('Неизвестный класс')
        p.hero_class=body.key;p.hp=max_hp(p)
        return {'message':f'Твой класс — {CLASSES[body.key]["name"]}','me':player_view(db,p)}

def ready(p):
    if not p.hero_class:raise ValueError('Сначала выбери класс')
    if p.cooldown and aware(p.cooldown)>now():raise ValueError('Персонаж восстанавливается после смерти')

@app.post('/api/stat')
def upgrade_stat(body:Choice,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        if body.key not in STATS:raise ValueError('Неверная характеристика')
        if p.stat_points<1:raise ValueError('Нет очков характеристик')
        x=dict(p.stats);x[body.key]+=1;p.stats=x;p.stat_points-=1
        if body.key=='endurance':p.hp+=5
        return {'message':f'{STATS[body.key]} улучшена'}

@app.post('/api/skill')
def upgrade_skill(body:Choice,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        tree=[x[0] for x in SKILLS[p.hero_class]]
        if body.key not in tree:raise ValueError('Это умение не твоего класса')
        if p.skill_points<1:raise ValueError('Нет очков навыков')
        idx=tree.index(body.key)
        if body.key in p.skills:raise ValueError('Уже открыто')
        if idx and tree[idx-1] not in p.skills:raise ValueError('Сначала изучи предыдущий навык')
        p.skills=[*p.skills,body.key];p.skill_points-=1
        return {'message':'Навык изучен'}

@app.post('/api/travel')
def travel(body:Choice,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        loc=LOCATIONS.get(body.key)
        if not loc:raise ValueError('Нет такой локации')
        if db.scalar(select(Battle).where(Battle.player_id==p.id)):raise ValueError('Нельзя уходить во время боя')
        if p.level<loc['min_level']:raise ValueError(f'Доступ с {loc["min_level"]} уровня')
        if p.location!=body.key:
            if body.key!='base':spend_stamina(p,3)
            p.location=body.key
        return {'message':f'Ты прибыла: {loc["name"]}'}

@app.post('/api/scavenge')
def scavenge(request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        if p.location=='base':raise ValueError('На базе нет ресурсов для поиска')
        if db.scalar(select(Battle).where(Battle.player_id==p.id)):raise ValueError('В бою нельзя искать припасы')
        spend_stamina(p,5)
        loc=LOCATIONS[p.location]
        key=random.choice([loc['material'],loc['material'],'cloth','food','water','wood','metal'])
        qty=random.randint(1,3)
        give_item(db,p.id,key,qty);progress(db,p.id,'scavenge')
        p.hunger=min(100,p.hunger+2);p.thirst=min(100,p.thirst+3)
        if random.random()<.14:
            spawn_battle(db,p)
            return {'message':f'Найдено: {ITEMS[key]["name"]} ×{qty}. Но шум привлёк заражённого!','battle':True}
        gain_xp(p,12)
        return {'message':f'Найдено: {ITEMS[key]["name"]} ×{qty}. +12 XP','battle':False}

@app.post('/api/combat/start')
def fight_start(request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        b=spawn_battle(db,p)
        return {'message':'Заражённый приближается!','battle':b}

class Action(BaseModel):
    action:str = Field(max_length=30)
    zone:str='body'

@app.post('/api/combat/turn')
def fight_turn(body:Action,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        b=db.scalar(select(Battle).where(Battle.player_id==p.id).with_for_update())
        if not b:raise ValueError('Сейчас нет активного боя')
        return combat_round(db,p,b,body.action,body.zone)

class ItemAction(BaseModel):
    key:str=Field(max_length=55)
    qty:int=Field(default=1,ge=1,le=100)

@app.post('/api/item/use')
def use_item(body:ItemAction,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        if body.key not in ['food','water','medkit']:raise ValueError('Нельзя использовать предмет')
        if body.qty!=1:raise ValueError('Используй по одному')
        take_item(db,p.id,body.key)
        if body.key=='medkit':p.hp=min(max_hp(p),p.hp+int(45*CLASSES[p.hero_class]['healing']))
        if body.key=='food':p.hunger=max(0,p.hunger-40)
        if body.key=='water':p.thirst=max(0,p.thirst-45)
        return {'message':f'Использовано: {ITEMS[body.key]["name"]}'}

@app.post('/api/item/equip')
def equip(body:Choice,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        item=ITEMS.get(body.key)
        if not item or item.get('type') not in ('armor','weapon'):raise ValueError('Не экипировка')
        if item_count(db,p.id,body.key)<1:raise ValueError('Нет такого предмета')
        equipped=db.scalar(select(ItemStack).where(ItemStack.player_id==p.id,ItemStack.equipped==True,ItemStack.item_key==body.key))
        if equipped:raise ValueError('Уже экипировано')
        for equipped in db.scalars(select(ItemStack).where(ItemStack.player_id==p.id,ItemStack.equipped==True)).all():
            if ITEMS[equipped.item_key].get('type')==item['type']:
                equipped.equipped=False
                free=db.scalar(select(ItemStack).where(ItemStack.player_id==p.id,ItemStack.item_key==equipped.item_key,ItemStack.equipped==False))
                if free:free.quantity+=equipped.quantity;db.delete(equipped)
        take_item(db,p.id,body.key)
        db.add(ItemStack(player_id=p.id,item_key=body.key,quantity=1,equipped=True))
        return {'message':f'Экипировано: {item["name"]}'}

@app.post('/api/craft')
def craft(body:Choice,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        recipe=RECIPES.get(body.key)
        if not recipe:raise ValueError('Нет такого рецепта')
        for k,q in recipe['cost'].items():
            if item_count(db,p.id,k)<q:raise ValueError('Не хватает: '+ITEMS[k]['name'])
        for k,q in recipe['cost'].items():take_item(db,p.id,k,q)
        give_item(db,p.id,body.key,recipe['qty'])
        return {'message':'Создано: '+ITEMS[body.key]['name']}

@app.post('/api/daily')
def daily(request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        today=now().strftime('%Y-%m-%d')
        if p.last_daily==today:raise ValueError('Награда уже получена сегодня')
        p.last_daily=today;p.caps+=75;p.stamina=min(500,p.stamina+80)
        give_item(db,p.id,'food',1);give_item(db,p.id,'water',1)
        gain_xp(p,45)
        return {'message':'Ежедневный набор: +75 крышек, +80 энергии, еда, вода и +45 XP'}

@app.get('/api/quests')
def quests(request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db)
        have={q.code:q for q in db.scalars(select(QuestProgress).where(QuestProgress.player_id==p.id))}
        return [{'code':k,**v,'amount':have[k].amount if k in have else 0,'claimed':have[k].claimed if k in have else False} for k,v in QUESTS.items()]

@app.post('/api/quest/claim')
def quest_claim(body:Choice,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        definition=QUESTS.get(body.key)
        if not definition:raise ValueError('Неизвестное задание')
        q=db.scalar(select(QuestProgress).where(QuestProgress.player_id==p.id,QuestProgress.code==body.key).with_for_update())
        if not q or q.amount<definition['target'] or q.claimed:raise ValueError('Награда пока недоступна')
        q.claimed=True;p.caps+=definition['reward']['caps'];gain_xp(p,definition['reward']['xp'])
        return {'message':'Задание завершено. Награда получена!'}

@app.get('/api/leaderboard')
def leaderboard(db:Session=Depends(db_session)):
    q=select(Player).where(Player.hero_class.isnot(None)).order_by(Player.level.desc(),Player.xp.desc()).limit(30)
    return [{'id':x.id,'name':x.name,'level':x.level,'class':x.hero_class,'rating':x.rating,'kills':x.kills} for x in db.scalars(q)]

@app.get('/api/boss')
def world_boss(db:Session=Depends(db_session)):
    with db.begin():
        b=boss_sync(db)
        hits=db.execute(select(BossHit.player_id,func.sum(BossHit.damage)).where(BossHit.spawn_at==str(int(aware(b.spawn_at).timestamp()))).group_by(BossHit.player_id).order_by(func.sum(BossHit.damage).desc()).limit(10)).all()
        ids=[x[0] for x in hits];names={x.id:x.name for x in db.scalars(select(Player).where(Player.id.in_(ids)))}
        return {'name':b.name,'hp':b.hp,'max_hp':b.max_hp,'spawn_at':str(int(aware(b.spawn_at).timestamp())),'ends_at':(aware(b.spawn_at)+timedelta(days=3)).isoformat(),
            'top':[{'name':names.get(pid,'Выживший'),'damage':dmg} for pid,dmg in hits]}

@app.post('/api/boss/hit')
def boss_hit(request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p);spend_stamina(p,5)
        b=db.scalar(select(WorldBoss).where(WorldBoss.id==1).with_for_update()) or boss_sync(db)
        if b.hp<=0:raise ValueError('Босс уже повержен. Жди нового цикла')
        entry=db.scalar(select(BossHit).where(BossHit.player_id==p.id,BossHit.spawn_at==str(int(aware(b.spawn_at).timestamp()))).with_for_update())
        if entry and (now()-aware(entry.last_hit)).total_seconds()<30:raise ValueError('Повторная атака через 30 секунд')
        damage=max(1,attack_power(db,p)*random.randint(3,5))
        damage=min(damage,b.hp)
        b.hp-=damage
        if entry:entry.damage+=damage;entry.last_hit=now()
        else:db.add(BossHit(player_id=p.id,spawn_at=str(int(aware(b.spawn_at).timestamp())),damage=damage))
        gain_xp(p,50);progress(db,p.id,'boss')
        return {'message':f'Колосс получил {damage} урона! +50 XP','damage':damage,'hp':b.hp}

class ClanCreate(BaseModel):
    name:str=Field(min_length=3,max_length=30)

@app.get('/api/clans')
def clans(request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db)
        cs=db.scalars(select(Clan).order_by(Clan.level.desc(),Clan.treasury.desc()).limit(30)).all()
        return {'mine':p.clan_id,'list':[{'id':c.id,'name':c.name,'level':c.level,'treasury':c.treasury,
          'members':db.scalar(select(func.count()).select_from(Player).where(Player.clan_id==c.id))} for c in cs]}

@app.post('/api/clans/create')
def clan_create(body:ClanCreate,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        if p.clan_id:raise ValueError('Ты уже состоишь в клане')
        if p.caps<250:raise ValueError('Создание клана стоит 250 крышек')
        name=body.name.strip()
        if not re.fullmatch(r'[\wА-Яа-яЁё -]{3,30}',name):raise ValueError('Допустимы только буквы, цифры, пробелы и дефис')
        if db.scalar(select(Clan).where(func.lower(Clan.name)==name.lower())):raise ValueError('Такой клан уже существует')
        p.caps-=250
        c=Clan(name=name,leader_id=p.id);db.add(c);db.flush();p.clan_id=c.id
        return {'message':f'Клан «{name}» основан!', 'id':c.id}

class IdBody(BaseModel):id:int=Field(gt=0)

@app.post('/api/clans/join')
def clan_join(body:IdBody,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        if p.clan_id:raise ValueError('Сначала выйди из текущего клана')
        c=db.scalar(select(Clan).where(Clan.id==body.id).with_for_update())
        if not c:raise ValueError('Клан не найден')
        count=db.scalar(select(func.count()).select_from(Player).where(Player.clan_id==c.id))
        if count>=25:raise ValueError('Клан заполнен')
        p.clan_id=c.id
        return {'message':'Ты вступила в клан '+c.name}

@app.post('/api/clans/leave')
def clan_leave(request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db)
        if not p.clan_id:raise ValueError('Нет клана')
        c=db.scalar(select(Clan).where(Clan.id==p.clan_id).with_for_update())
        members=db.scalars(select(Player).where(Player.clan_id==p.clan_id,Player.id!=p.id).order_by(Player.level.desc())).all()
        if c and c.leader_id==p.id:
            if members:c.leader_id=members[0].id
            else:
                for t in db.scalars(select(Territory).where(Territory.clan_id==c.id)):t.clan_id=None
                db.delete(c)
        p.clan_id=None
        return {'message':'Ты покинула клан'}

class Amount(BaseModel):amount:int=Field(ge=1,le=1000000)

@app.post('/api/clans/donate')
def clan_donate(body:Amount,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        if not p.clan_id:raise ValueError('Нет клана')
        if p.caps<body.amount:raise ValueError('Не хватает крышек')
        c=db.scalar(select(Clan).where(Clan.id==p.clan_id).with_for_update())
        p.caps-=body.amount;c.treasury+=body.amount
        return {'message':f'{body.amount} крышек передано в казну'}

@app.get('/api/territories')
def territories(db:Session=Depends(db_session)):
    ts=db.scalars(select(Territory)).all()
    ids={t.clan_id for t in ts if t.clan_id}
    names={c.id:c.name for c in db.scalars(select(Clan).where(Clan.id.in_(ids)))}
    return [{'id':t.id,'name':TERRITORIES[t.id],'owner':names.get(t.clan_id,'Заражённые'),'clan_id':t.clan_id,'strength':t.strength,
             'next_attack':aware(t.next_attack).isoformat() if t.next_attack else None} for t in ts]

@app.post('/api/territories/attack')
def attack_territory(body:Choice,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        if not p.clan_id:raise ValueError('Войны доступны только кланам')
        t=db.scalar(select(Territory).where(Territory.id==body.key).with_for_update())
        if not t:raise ValueError('Нет такой территории')
        if t.clan_id==p.clan_id:raise ValueError('Это ваша территория')
        if t.next_attack and aware(t.next_attack)>now():raise ValueError('Территория под защитой после нападения')
        spend_stamina(p,40)
        c=db.scalar(select(Clan).where(Clan.id==p.clan_id).with_for_update())
        strength=attack_power(db,p)+random.randint(0,30)+(c.level-1)*10
        t.next_attack=now()+timedelta(minutes=30)
        if strength>=t.strength:
            t.clan_id=c.id;t.strength=min(600,int(strength*1.2));p.caps+=90
            return {'message':f'Территория «{TERRITORIES[t.id]}» захвачена кланом! +90 крышек'}
        t.strength=max(1,t.strength-int(strength*.55))
        return {'message':f'Атака отбита. Оборона ослаблена до {t.strength}'}

@app.get('/api/market')
def market(db:Session=Depends(db_session)):
    ls=db.scalars(select(MarketLot).where(MarketLot.active==True).order_by(MarketLot.id.desc()).limit(50)).all()
    ids={x.seller_id for x in ls};players={p.id:p.name for p in db.scalars(select(Player).where(Player.id.in_(ids)))}
    return [{'id':x.id,'seller':players.get(x.seller_id,'Выживший'),'seller_id':x.seller_id,'offer':x.offered_key,'qty':x.offered_qty,'want':x.wanted_key,'want_qty':x.wanted_qty} for x in ls]

class LotRequest(BaseModel):
    offer:str=Field(max_length=55)
    qty:int=Field(ge=1,le=100)
    want:str=Field(max_length=55)
    want_qty:int=Field(ge=1,le=100)

@app.post('/api/market/create')
def market_create(body:LotRequest,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        if body.offer not in ITEMS or body.want not in ITEMS or body.offer==body.want:raise ValueError('Некорректные предметы')
        if db.scalar(select(func.count()).select_from(MarketLot).where(MarketLot.seller_id==p.id,MarketLot.active==True))>=5:raise ValueError('Максимум 5 активных лотов')
        take_item(db,p.id,body.offer,body.qty)
        lot=MarketLot(seller_id=p.id,offered_key=body.offer,offered_qty=body.qty,wanted_key=body.want,wanted_qty=body.want_qty)
        db.add(lot)
        return {'message':'Лот размещён. Предметы зарезервированы'}

@app.post('/api/market/buy')
def market_buy(body:IdBody,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        lot=db.scalar(select(MarketLot).where(MarketLot.id==body.id).with_for_update())
        if not lot or not lot.active:raise ValueError('Лот недоступен')
        if lot.seller_id==p.id:raise ValueError('Нельзя покупать свой лот')
        take_item(db,p.id,lot.wanted_key,lot.wanted_qty)
        give_item(db,lot.seller_id,lot.wanted_key,lot.wanted_qty)
        give_item(db,p.id,lot.offered_key,lot.offered_qty)
        lot.active=False
        return {'message':'Сделка завершена, предметы отправлены обоим игрокам'}

@app.post('/api/market/cancel')
def market_cancel(body:IdBody,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db)
        lot=db.scalar(select(MarketLot).where(MarketLot.id==body.id).with_for_update())
        if not lot or not lot.active or lot.seller_id!=p.id:raise ValueError('Это не твой лот')
        lot.active=False;give_item(db,p.id,lot.offered_key,lot.offered_qty)
        return {'message':'Лот снят, предметы возвращены'}

@app.get('/api/pvp')
def pvp_list(request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db)
        match=db.scalar(select(PvPMatch).where(or_(PvPMatch.challenger_id==p.id,PvPMatch.defender_id==p.id),PvPMatch.state.in_(['pending','active'])).order_by(PvPMatch.id.desc()))
        top=db.scalars(select(Player).where(Player.id!=p.id,Player.hero_class.isnot(None)).order_by(Player.rating.desc()).limit(20)).all()
        return {'match':pvp_view(db,match) if match else None,'players':[{'id':x.id,'name':x.name,'level':x.level,'rating':x.rating} for x in top]}

def pvp_view(db,m):
    if not m:return None
    names={p.id:p.name for p in db.scalars(select(Player).where(Player.id.in_([m.challenger_id,m.defender_id])))}
    return {'id':m.id,'state':m.state,'challenger':{'id':m.challenger_id,'name':names.get(m.challenger_id,'Игрок'),'hp':m.hp_a},
            'defender':{'id':m.defender_id,'name':names.get(m.defender_id,'Игрок'),'hp':m.hp_b},'current_id':m.current_id,'log':m.log[-8:], 'updated_at':aware(m.updated_at).isoformat()}

class PlayerId(BaseModel):player_id:int=Field(gt=0)

@app.post('/api/pvp/challenge')
def pvp_challenge(body:PlayerId,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        if body.player_id==p.id:raise ValueError('Нельзя вызвать себя')
        other=db.get(Player,body.player_id)
        if not other or not other.hero_class:raise ValueError('Игрок не найден')
        pending=db.scalar(select(PvPMatch).where(or_(PvPMatch.challenger_id.in_([p.id,other.id]),PvPMatch.defender_id.in_([p.id,other.id])),PvPMatch.state.in_(['pending','active'])))
        if pending:raise ValueError('Один из игроков уже участвует в дуэли')
        spend_stamina(p,10)
        m=PvPMatch(challenger_id=p.id,defender_id=other.id,hp_a=max_hp(p),hp_b=max_hp(other),log=[f'{p.name} вызывает {other.name} на дуэль'])
        db.add(m)
        return {'message':'Вызов отправлен. Соперник увидит его на арене'}

class PvPDecision(BaseModel):id:int=Field(gt=0);action:str=Field(max_length=20)

@app.post('/api/pvp/act')
def pvp_act(body:PvPDecision,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        m=db.scalar(select(PvPMatch).where(PvPMatch.id==body.id).with_for_update())
        if not m or p.id not in (m.challenger_id,m.defender_id):raise ValueError('Нет такой дуэли')
        if m.state=='pending':
            if body.action=='cancel' and p.id==m.challenger_id:m.state='cancelled';return {'message':'Вызов отозван'}
            if body.action not in ('accept','decline') or p.id!=m.defender_id:raise ValueError('Ожидается решение соперника')
            if body.action=='decline':m.state='declined';return {'message':'Вызов отклонён'}
            m.state='active';m.current_id=m.challenger_id;m.updated_at=now()
            return {'message':'Дуэль началась! Первый ход за инициатором'}
        if m.state!='active':raise ValueError('Дуэль завершена')
        if body.action=='surrender':
            winner_id=m.defender_id if p.id==m.challenger_id else m.challenger_id
        else:
            if m.current_id!=p.id:raise ValueError('Сейчас ход соперника')
            if body.action not in ('attack','defend'):raise ValueError('Выбери атаку или защиту')
            if now()-aware(m.updated_at)>timedelta(minutes=5):
                winner_id=m.defender_id if p.id==m.challenger_id else m.challenger_id
            else:
                target=db.get(Player,m.defender_id if p.id==m.challenger_id else m.challenger_id)
                damage=max(1,int(attack_power(db,p)*random.uniform(.55,1.0))) if body.action=='attack' else 0
                if p.id==m.challenger_id:
                    m.hp_b=max(0,m.hp_b-damage);dead=m.hp_b==0
                else:
                    m.hp_a=max(0,m.hp_a-damage);dead=m.hp_a==0
                m.log=[*(m.log or [])[-12:],f'{p.name}: {"атака" if damage else "защита"} — {damage} урона']
                m.current_id=target.id;m.updated_at=now()
                if not dead:return {'message':f'Ход выполнен: {damage} урона'}
                winner_id=p.id
        winner=db.get(Player,winner_id);loser=db.get(Player,m.challenger_id if winner_id==m.defender_id else m.defender_id)
        winner.rating+=25;loser.rating=max(0,loser.rating-20);winner.pvp_wins+=1
        winner.caps+=35;gain_xp(winner,80);progress(db,winner.id,'pvp')
        m.state='finished';m.current_id=None;m.updated_at=now()
        m.log=[*(m.log or []),f'{winner.name} побеждает в дуэли!'][-12:]
        return {'message':f'Дуэль завершена. Победитель: {winner.name}'}

SHOP={'medkit':{'caps':55},'food':{'caps':25},'water':{'caps':20},'knife':{'caps':80},'vest':{'caps':300},'pistol':{'caps':420}}

@app.get('/api/shop')
def shop():return [{'key':k,'price':v['caps'],**ITEMS[k]} for k,v in SHOP.items()]

@app.post('/api/shop/buy')
def shop_buy(body:Choice,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        if body.key not in SHOP:raise ValueError('Нет такого товара')
        cost=SHOP[body.key]['caps']
        if p.caps<cost:raise ValueError('Недостаточно крышек')
        p.caps-=cost;give_item(db,p.id,body.key)
        return {'message':f'Куплено: {ITEMS[body.key]["name"]}'}

# Monetization: real Telegram Stars invoices, delivery only on authenticated successful_payment updates.
STAR_OFFERS={'zombo_100':(100,100),'zombo_550':(500,550),'zombo_1800':(1500,1800),'zombo_6500':(5000,6500)}

PREMIUM_OFFERS={
    'vip_7':{'name':'VIP на 7 дней','price':250,'days':7,'kind':'vip','desc':'Ускоренная энергия и +20% XP'},
    'vip_14':{'name':'VIP на 14 дней','price':450,'days':14,'kind':'vip','desc':'Ускоренная энергия и +20% XP'},
    'vip_30':{'name':'VIP на 30 дней','price':800,'days':30,'kind':'vip','desc':'Ускоренная энергия и +20% XP'},
    'xp_day':{'name':'×2 опыт на 24 часа','price':100,'days':1,'kind':'xp','desc':'Ускоренная прокачка'},
    'loot_day':{'name':'×2 шанс добычи на 24 часа','price':100,'days':1,'kind':'loot','desc':'Больше находок в PvE'},
}

@app.get('/api/premium')
def premium_catalog():return [{'key':k,**v} for k,v in PREMIUM_OFFERS.items()]

@app.post('/api/premium/buy')
def premium_buy(body:Choice,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        offer=PREMIUM_OFFERS.get(body.key)
        if not offer:raise ValueError('Нет такого улучшения')
        if p.zombo<offer['price']:raise ValueError('Недостаточно Zombo')
        p.zombo-=offer['price']
        field={'vip':'vip_until','xp':'xp_boost_until','loot':'loot_boost_until'}[offer['kind']]
        end=getattr(p,field)
        start=max(now(),aware(end)) if end else now()
        setattr(p,field,start+timedelta(days=offer['days']))
        return {'message':f'Активировано: {offer["name"]}'}

@app.get('/api/stars')
def stars_offers():return [{'key':k,'stars':s,'zombo':z} for k,(s,z) in STAR_OFFERS.items()]

@app.post('/api/stars/invoice')
async def invoice(body:Choice,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        if body.key not in STAR_OFFERS:raise ValueError('Нет такого набора')
        stars,zombo=STAR_OFFERS[body.key]
        # Signed payload binds the invoice to the buyer and exact product.
        payload=f'{p.id}:{body.key}:{secrets.token_hex(10)}'
        result=await telegram_api('createInvoiceLink',{'title':f'{zombo} Zombo','description':'Премиум-валюта для ZOMBO',
            'payload':payload,'currency':'XTR','prices':[{'label':f'{zombo} Zombo','amount':stars}]})
        if not result.get('ok'):raise HTTPException(502,'Не удалось сформировать счёт Telegram Stars')
        return {'url':result['result']}

@app.post('/telegram/webhook')
async def webhook(request:Request):
    if not SECRET or request.headers.get('x-telegram-bot-api-secret-token')!=SECRET:raise HTTPException(403,'Forbidden')
    data=await request.json()
    if 'pre_checkout_query' in data:
        q=data['pre_checkout_query'];valid=False
        try:
            pid,key,_=q['invoice_payload'].split(':',2)
            valid=(int(pid)==q['from']['id'] and key in STAR_OFFERS and q['currency']=='XTR' and STAR_OFFERS[key][0]==q['total_amount'])
        except (ValueError,KeyError):pass
        await telegram_api('answerPreCheckoutQuery',{'pre_checkout_query_id':q['id'],'ok':valid,'error_message':'Ошибка данных заказа' if not valid else None})
    msg=data.get('message')
    if not msg:return {'ok':True}
    chat_id=msg.get('chat',{}).get('id');user=msg.get('from',{})
    if not chat_id or not user:return {'ok':True}
    if 'successful_payment' in msg:
        payment=msg['successful_payment']
        try:
            pid,key,_=payment['invoice_payload'].split(':',2)
            if int(pid)==user['id'] and payment['currency']=='XTR' and key in STAR_OFFERS and payment['total_amount']==STAR_OFFERS[key][0]:
                charge_id=payment['telegram_payment_charge_id']
                with SessionLocal.begin() as db:
                    if not db.get(Payment,charge_id):
                        p=db.get(Player,int(pid))
                        if p:
                            p.zombo+=STAR_OFFERS[key][1]
                            db.add(Payment(id=charge_id,player_id=p.id,stars=payment['total_amount'],zombo=STAR_OFFERS[key][1]))
                await telegram_api('sendMessage',{'chat_id':chat_id,'text':'💎 Покупка успешно зачислена! Открой ZOMBO и проверь баланс.'})
        except Exception:logger.exception('payment processing error')
        return {'ok':True}
    text=(msg.get('text') or '').split('@')[0].strip().split(' ')[0]
    if text in ('/start','/help','/profile','/daily'):
        if text=='/daily':
            with SessionLocal.begin() as db:
                p=db.get(Player,int(user['id']))
                if not p or not p.hero_class:reply='Сначала создай персонажа в игре.'
                elif p.last_daily==now().strftime('%Y-%m-%d'):reply='Сегодняшний набор уже получен. Возвращайся завтра!'
                else:
                    p.last_daily=now().strftime('%Y-%m-%d');p.caps+=75;p.stamina=min(500,p.stamina+80)
                    give_item(db,p.id,'food');give_item(db,p.id,'water');gain_xp(p,45)
                    reply='🎁 +75 крышек, +80 энергии, еда, вода и +45 XP!'
        elif text=='/profile':
            with SessionLocal() as db:
                p=db.get(Player,int(user['id']))
                reply=f'🧟 {p.name}\nУровень {p.level} · {CLASSES.get(p.hero_class,{}).get("name","Новичок")}\n❤️ {p.hp}/{max_hp(p)} · ⚡ {p.stamina}/500\nКрышки: {p.caps}' if p else 'Открой игру, чтобы создать персонажа.'
        else:reply='🧟 ZOMBO: After the Fall\nВыбирай класс, исследуй пустошь, сражайся с зомби и захватывай территории вместе с кланом.'
        message={'chat_id':chat_id,'text':reply}
        if PUBLIC_URL:message['reply_markup']={'inline_keyboard':[[{'text':'🎮 Открыть ZOMBO','web_app':{'url':PUBLIC_URL}}]]}
        await telegram_api('sendMessage',message)
    return {'ok':True}

@app.get('/api/admin/summary')
def admin_summary(request:Request,db:Session=Depends(db_session)):
    pid=identify(request.headers.get('authorization',''))['id']
    if pid not in ADMIN_IDS:raise HTTPException(403,'Только администратор')
    return {'players':db.scalar(select(func.count()).select_from(Player)), 'clans':db.scalar(select(func.count()).select_from(Clan)),
            'battles':db.scalar(select(func.count()).select_from(Battle)),'lots':db.scalar(select(func.count()).select_from(MarketLot).where(MarketLot.active==True))}