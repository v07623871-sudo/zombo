import os, hmac, hashlib, json, random, re, secrets, logging, asyncio
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from security import ApiQuota, TelegramReceipt, TooManyActions, enforce_quota, claim_update, finish_update, prune_update_receipts
from encounters import install_encounters, pending_encounter
from world_events import install_world_events, record_action as record_world_action
from notifications import (install_notifications, claim_batch, complete_delivery,
                           cleanup as cleanup_notifications)
from urllib.parse import parse_qsl
import httpx
from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_, and_, text
from sqlalchemy.orm import Session
from pvp_rating import league, settle_rated_duel, daily_remaining, DAILY_REWARDED_DUELS
from models import (Base, engine, SessionLocal, now, Player, ItemStack, Battle, Clan, Territory, tag_resource_operation,
                    MarketLot, WorldBoss, BossHit, QuestProgress, PvPMatch, Payment, StarInvoice, PaymentReview, ClanOfficer, TerritoryTax, TerritoryWar, WarFighter)
from game import (ENEMIES, CLASSES, SKILLS, SKILL_TREES, talent_node, talent_rank, talent_bonus, talent_reset_cost, migrate_talents, STATS, ITEMS, LOCATIONS, RECIPES, QUESTS, TERRITORIES,
                  aware, max_hp, gain_xp, give_item, take_item, item_count, tick, spend_stamina,
                  player_view, battle_view, combat_round, spawn_battle, attack_power, progress, boss_sync, WORLD_BOSS_ROTATION, SHOP_PRICES, CONSUMABLE_EFFECTS, scavenge_pool, PETS, pet_status)

from clan_wars import (WAR_TIMEZONE, LOCATION_TERRITORY, MIN_BID, phase, next_war_date, war_date_for_bid,
    can_command, bid as place_bid, appoint as appoint_warlord, roster as set_roster, war_action,
    war_view, refresh_world, zombie_tax, collect_tax, settle_war, local)

logging.basicConfig(level=logging.INFO)
# HTTPX INFO logs include Telegram token in the request URL.
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logger=logging.getLogger('zombo')
BOT_TOKEN=os.getenv('BOT_TOKEN','')
PUBLIC_URL=os.getenv('PUBLIC_URL','').rstrip('/')
SECRET=os.getenv('TELEGRAM_WEBHOOK_SECRET','')
# Demo identities are accepted only on a local instance without a configured bot.
DEMO=(os.getenv('DEMO_MODE','0')=='1' and not BOT_TOKEN and
      (not PUBLIC_URL or re.match(r'^https?://(localhost|127\.0\.0\.1)(:\d+)?$', PUBLIC_URL) is not None))
ADMIN_IDS={int(x) for x in os.getenv('ADMIN_IDS','').split(',') if x.strip().isdigit()}
ACCEPT_LEGACY_STAR_INVOICES=os.getenv('ACCEPT_LEGACY_STAR_INVOICES','1')=='1'

async def telegram_api(method, payload):
    if not BOT_TOKEN: return {'ok':False,'error':'no token'}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r=await client.post(f'https://api.telegram.org/bot{BOT_TOKEN}/{method}',json=payload)
            if r.status_code>=400:logger.error('Telegram %s error %s',method,r.status_code)
            return r.json()
    except Exception as exc:
        logger.error('Telegram %s transport error: %s',method,type(exc).__name__)
        return {'ok':False}

@asynccontextmanager
async def lifespan(app: FastAPI):
    if engine.dialect.name == 'postgresql' and not DEMO:
        # Never recreate a missing live table on startup and hide lost data.
        from scripts.migrate import status as migration_status
        with engine.connect() as connection:
            plan = migration_status(connection)
        if plan['pending_tables'] or plan['pending_versions']:
            raise RuntimeError('Database schema is not migrated; run python scripts/migrate.py before starting ZOMBO')
    else:
        Base.metadata.create_all(bind=engine)
    with SessionLocal.begin() as db:
        for key in TERRITORIES:
            if not db.get(Territory,key): db.add(Territory(id=key))
            if not db.get(TerritoryTax,key): db.add(TerritoryTax(territory_id=key, last_collection=now()))
    if BOT_TOKEN and PUBLIC_URL and SECRET:
        result=await telegram_api('setWebhook',{'url':f'{PUBLIC_URL}/telegram/webhook','secret_token':SECRET,'allowed_updates':['message','pre_checkout_query']})
        logger.info('Webhook configured: %s',bool(result.get('ok')))
        await telegram_api('setChatMenuButton',{'menu_button':{'type':'web_app','text':'Открыть ZOMBO','web_app':{'url':PUBLIC_URL}}})
        await telegram_api('setMyCommands',{'commands':[
            {'command':'start','description':'Начать игру'},
            {'command':'profile','description':'Персонаж'},
            {'command':'daily','description':'Ежедневная награда'},
            {'command':'top','description':'Рейтинг: уровень, зомби, PvP'},
            {'command':'quests','description':'Задания и прогресс'},
            {'command':'boss','description':'Мировой босс'},
            {'command':'raid','description':'Мой рейд'},
            {'command':'expedition','description':'Дальняя экспедиция'},
            {'command':'help','description':'Список команд'},
            {'command':'id','description':'Мой Telegram ID'},
            {'command':'admin','description':'Проверить доступ администратора'},
            {'command':'enemies','description':'Бестиарий'},
            {'command':'clan','description':'Клановые войны'},
            {'command':'map','description':'Где я?'},
            {'command':'skills','description':'Прокачка'},
            {'command':'story','description':'Сюжетная кампания'},
            {'command':'bag','description':'Рюкзак'}]})
    loop = asyncio.create_task(_war_clock_loop())
    try:
        yield
    finally:
        loop.cancel()
        try: await loop
        except asyncio.CancelledError: pass

async def _war_clock_loop():
    # Database timestamps + row locks make scheduled work durable/idempotent.
    while True:
        try:
            await asyncio.to_thread(_war_clock_tick)
            if BOT_TOKEN:
                await _deliver_notifications()
        except Exception:
            logger.exception('Clan war and territorial tax scheduler failed')
        await asyncio.sleep(25)

async def _deliver_notifications():
    """Sending is outside game transactions. Failures are retried asynchronously."""
    for job in await asyncio.to_thread(claim_batch):
        payload = {'chat_id': job['player_id'], 'text': job['message']}
        if PUBLIC_URL:
            payload['reply_markup'] = {'inline_keyboard': [[
                {'text': '🎮 Открыть ZOMBO', 'web_app': {'url': PUBLIC_URL}}]]}
        try:
            result = await telegram_api('sendMessage', payload)
        except Exception:
            logger.exception('Notification sender failed')
            result = {'ok': False}
        await asyncio.to_thread(complete_delivery, job['id'], job['lease'], result)


def _war_clock_tick():
    with SessionLocal.begin() as session:
        from clan_missions import settle_seasons
        settle_seasons(session)
        refresh_world(session)
        expire_sales(session)
        prune_update_receipts(session)
        cleanup_notifications(session)

APP_VERSION='0.41.0'
app=FastAPI(title='ZOMBO · After the Fall',version=APP_VERSION,lifespan=lifespan)
app.mount('/static', StaticFiles(directory=os.path.join(os.path.dirname(__file__),'static')),name='static')

@app.get('/health')
def health():return {'status':'ok','game':'ZOMBO','version':APP_VERSION}

@app.get('/ready')
def readiness():
    try:
        with SessionLocal() as db:
            db.execute(text('SELECT 1'))
    except Exception:
        raise HTTPException(503,'Database unavailable')
    return {'status':'ready'}

@app.get('/')
def home():return FileResponse(os.path.join(os.path.dirname(__file__),'static','index.html'))

@app.middleware('http')
async def secure_headers(request, call_next):
    if request.method == 'POST' and request.url.path.startswith('/api/'):
        # Only signed Telegram users are charged; anonymous malformed requests
        # still receive their ordinary authentication failure from the endpoint.
        auth = request.headers.get('authorization', '')
        try:
            pid = identify(auth)['id']
        except HTTPException:
            pid = None
        if pid is not None:
            economic = request.url.path.startswith(('/api/market/', '/api/gear-market/',
                        '/api/shop/', '/api/cases/', '/api/chests/', '/api/stars/', '/api/premium/', '/api/admin/',
                        '/api/clans/donate', '/api/territories/bid'))
            try:
                # Commit throttle counters even when a request is denied.
                with SessionLocal.begin() as quota_db:
                    enforce_quota(quota_db, pid, 'write', limit=180)
                    if economic:
                        enforce_quota(quota_db, pid, 'economy', limit=30)
            except TooManyActions as exc:
                return JSONResponse({'detail':str(exc)}, status_code=429,
                                    headers={'Retry-After':str(exc.retry_after)})
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
        if not raw.isdigit() or not 0<int(raw)<=9223372036854775807:
            raise HTTPException(401,'Неверный тестовый ID')
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
    tag_resource_operation(db, f'{request.method}:{request.url.path}')
    user=identify(request.headers.get('authorization',''))
    p=db.scalar(select(Player).where(Player.id==int(user['id'])).with_for_update())
    if not p:
        name=' '.join(filter(None,[user.get('first_name'),user.get('last_name')]))[:90] or 'Выживший'
        p=Player(id=int(user['id']),name=name,username=user.get('username','')[:90],stats={k:0 for k in STATS},skills=[])
        db.add(p);db.flush()
        for key,qty in [('knife',1),('medkit',2),('food',2),('water',2),('wood',3)]:give_item(db,p.id,key,qty)
    if p.banned or p.frozen:raise HTTPException(403,'Персонаж заблокирован')
    migrate_talents(p)
    tick(p)
    return p

@app.get('/api/config')
def config():return {'enemies':ENEMIES,'classes':CLASSES,'skills':SKILLS,'skill_trees':SKILL_TREES,'stats':STATS,'items':ITEMS,'locations':LOCATIONS,'recipes':RECIPES,'quests':QUESTS,'territory_names':TERRITORIES,'war_timezone':WAR_TIMEZONE,'location_territories':LOCATION_TERRITORY,'pets':PETS,'pet_adoption':{'random':750,'chosen':1250},'cases':{key:{**entry,'shop_price':None,'gem_price':GEM_CASE_PRICES[key],
            'weapons':CASE_POOLS[key]} for key,entry in CASES.items()},
            'chests':chest_catalog()}

@app.get('/api/me')
def me(request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db)
        return {**player_view(db,p), 'admin': p.id in ADMIN_IDS,
                'encounter_pending': pending_encounter(db,p.id)}

class Choice(BaseModel):
    key: str = Field(min_length=1,max_length=55)

@app.post('/api/class')
def choose_class(body:Choice,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db)
        if p.hero_class:raise ValueError('Класс выбирается один раз')
        if body.key not in CLASSES:raise ValueError('Неизвестный класс')
        p.hero_class=body.key;migrate_talents(p);p.hp=max_hp(p)
        return {'message':f'Твой класс — {CLASSES[body.key]["name"]}','me':player_view(db,p)}

def ready(p):
    if not p.hero_class:raise ValueError('Сначала выбери класс')
    if p.cooldown and aware(p.cooldown)>now():raise ValueError('Персонаж восстанавливается после смерти')

from raids import install_raids, RaidRun, RaidMember
from expeditions import install_expeditions, ExpeditionRun, ExpeditionMember, settle_player as settle_player_expedition
from gear import install_gear, create_gear, GearItem, BASE_GEAR, gear_stats, open_case, gear_view, wear_equipped
from legendary_ammo import spend_legendary_round, ammo_message
from armory_content import CASES, CASE_POOLS
from premium_chests import CHESTS, GEM_CASE_PRICES, chest_catalog, open_paid_chest
from story import install_story, StoryProgress, CHAPTERS
from gear_market import install_gear_market, expire_sales
from clan_missions import install_clan_missions
from admin import install_admin
install_raids(app, with_player, ready)
install_expeditions(app, with_player, ready)
install_gear(app, with_player, ready)
install_story(app, with_player, ready)
install_gear_market(app, with_player, ready, identify)
install_clan_missions(app, with_player, ready)
install_admin(app, identify, ADMIN_IDS)
install_notifications(app, with_player)
install_world_events(app, with_player, identify, ADMIN_IDS)
install_encounters(app, with_player, ready)

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
        node=talent_node(p.hero_class,body.key)
        if not node:raise ValueError('Это умение не твоего класса')
        if p.skill_points<1:raise ValueError('Нет очков талантов')
        rank=talent_rank(p,body.key)
        if rank>=node['max_rank']:raise ValueError('Навык полностью изучен')
        if p.level<node['min_level']:raise ValueError(f'Требуется уровень {node["min_level"]}')
        if node['requires'] and talent_rank(p,node['requires'])<node['required_rank']:
            required=talent_node(p.hero_class,node['requires'])
            raise ValueError(f'Сначала прокачай «{required["name"]}» до ранга {node["required_rank"]}')
        p.skills=[*(p.skills or []),body.key];p.skill_points-=1
        if node['effect']=='health':p.hp=min(max_hp(p),p.hp+int(node['per_rank']))
        return {'message':f'✦ {node["name"]}: ранг {rank+1}/{node["max_rank"]}','rank':rank+1}

@app.post('/api/skill/reset')
def reset_skills(request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        if not p.skills:raise ValueError('Ты ещё не вкладывала очки в навыки')
        if db.scalar(select(Battle).where(Battle.player_id==p.id)):
            raise ValueError('Не меняй специализацию во время боя')
        cost=talent_reset_cost(p)
        if p.caps<cost:raise ValueError(f'Для сброса нужно {cost} крышек')
        p.caps-=cost
        refund=len(p.skills or [])
        p.skill_points+=refund;p.skills=[]
        p.stats={**p.stats,'_talent_resets':int(p.stats.get('_talent_resets',0))+1}
        p.hp=min(p.hp,max_hp(p))
        return {'message':f'Таланты сброшены. Возвращено {refund} очков.'}

@app.post('/api/travel')
def travel(body:Choice,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        loc=LOCATIONS.get(body.key)
        if not loc:raise ValueError('Нет такой локации')
        if db.scalar(select(Battle).where(Battle.player_id==p.id)):raise ValueError('Нельзя уходить во время боя')
        if pending_encounter(db,p.id):raise ValueError('Сначала заверши случайную встречу в меню')
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
        if pending_encounter(db,p.id):raise ValueError('Сначала заверши случайную встречу в меню')
        if db.scalar(select(Battle).where(Battle.player_id==p.id)):raise ValueError('В бою нельзя искать припасы')
        spend_stamina(p,5)
        loc=LOCATIONS[p.location]
        key=random.choice(scavenge_pool(p.location))
        qty=random.randint(1,3)
        qty+=min(3,int(talent_bonus(p,'scavenge')*4))
        world_supply=record_world_action(db,p,'supplies')
        if world_supply:
            qty+=1
        give_item(db,p.id,key,qty);progress(db,p.id,'scavenge')
        # Searching sometimes yields unique equipment in addition to stackable materials.
        if random.random()<.035:
            from gear import roll_drop
            try:roll_drop(db,p.id,loc['threat'])
            except ValueError:pass
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
        if pending_encounter(db,p.id):raise ValueError('Сначала заверши случайную встречу в меню')
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
        effect=CONSUMABLE_EFFECTS.get(body.key)
        if not effect:raise ValueError('Нельзя использовать предмет')
        if body.qty!=1:raise ValueError('Используй по одному')
        take_item(db,p.id,body.key)
        if 'hp' in effect:
            p.hp=min(max_hp(p),p.hp+int(effect['hp']*CLASSES[p.hero_class]['healing']*(1+talent_bonus(p,'healing'))))
        if 'stamina' in effect:p.stamina=min(500,p.stamina+effect['stamina'])
        if 'hunger' in effect:p.hunger=max(0,p.hunger-effect['hunger'])
        if 'thirst' in effect:p.thirst=max(0,p.thirst-effect['thirst'])
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
        # Old stackable items and individually rolled gear share one equip slot.
        for new_gear in db.scalars(select(GearItem).where(GearItem.player_id==p.id,GearItem.equipped==True).with_for_update()).all():
            if BASE_GEAR[new_gear.base_key]['slot']==item['type']:new_gear.equipped=False
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
        output=recipe.get('output',body.key)
        if output not in ITEMS:raise ValueError('Неизвестный результат рецепта')
        if output in BASE_GEAR:
            for _ in range(recipe['qty']):create_gear(db,p.id,output,'common','craft')
        else:give_item(db,p.id,output,recipe['qty'])
        return {'message':f'Создано: {ITEMS[output]["name"]} ×{recipe["qty"]}'}

@app.post('/api/cases/open')
def case_open(body:Choice,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        if db.scalar(select(Battle.id).where(Battle.player_id==p.id)):
            raise ValueError('Нельзя вскрывать кейс в бою')
        reward=open_case(db,p.id,body.key)
        view=gear_view(reward)
        return {'message':f'Кейс вскрыт! {view["rarity_name"]} {view["name"]}.'+
                (' ✧ Выданы 12 легендарных патронов.' if view['ammo_key'] else ''),
                'gear':view}

@app.post('/api/chests/open')
def paid_chest_open(body:Choice,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        if db.scalar(select(Battle.id).where(Battle.player_id==p.id)):
            raise ValueError('Нельзя открывать сундук в бою')
        rewards=open_paid_chest(db,p.id,body.key)
        return {'message':f'🎉 Открыт {CHESTS[body.key]["name"]}! Наград: {len(rewards)}.',
                'rewards':rewards,'count':len(rewards)}


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

LEADERBOARD_SORTS={
    'level':('УРОВЕНЬ',Player.level.desc(),Player.xp.desc()),
    'kills':('ЗАРАЖЁННЫЕ',Player.kills.desc(),Player.level.desc()),
    'pvp':('АРЕНА',Player.rating.desc(),Player.pvp_wins.desc()),
}

def leaderboard_players(db:Session,sort:str='level',limit:int=30):
    if sort not in LEADERBOARD_SORTS:raise ValueError('Неизвестный рейтинг')
    _,primary,secondary=LEADERBOARD_SORTS[sort]
    return db.scalars(select(Player).where(Player.hero_class.isnot(None),
        Player.banned.is_(False),Player.frozen.is_(False))
        .order_by(primary,secondary,Player.id).limit(limit)).all()

@app.get('/api/leaderboard')
def leaderboard(sort:str='level',db:Session=Depends(db_session)):
    return [{'id':x.id,'name':x.name,'level':x.level,'class':x.hero_class,
             'rating':x.rating,'league':league(x.rating)['name'],
             'kills':x.kills,'pvp_wins':x.pvp_wins}
            for x in leaderboard_players(db,sort)]

@app.get('/api/boss')
def world_boss(db:Session=Depends(db_session)):
    with db.begin():
        b=boss_sync(db)
        hits=db.execute(select(BossHit.player_id,func.sum(BossHit.damage)).where(BossHit.spawn_at==str(int(aware(b.spawn_at).timestamp()))).group_by(BossHit.player_id).order_by(func.sum(BossHit.damage).desc()).limit(10)).all()
        ids=[x[0] for x in hits];names={x.id:x.name for x in db.scalars(select(Player).where(Player.id.in_(ids)))}
        boss_info=next((config for config in WORLD_BOSS_ROTATION if config['name']==b.name),
                       WORLD_BOSS_ROTATION[0])
        from boss_combat import combat_phase
        return {'name':b.name,'hp':b.hp,'max_hp':b.max_hp,
            'hint':boss_info['hint'],'mechanic':boss_info['mechanic'],
            'attack_name':boss_info['attack_name'],'phase':combat_phase(b),
            'cycle_bosses':len(WORLD_BOSS_ROTATION),
            'top_prize':'Легендарная винтовка лидеру урона, только если босс побеждён',
            'spawn_at':str(int(aware(b.spawn_at).timestamp())),
            'ends_at':(aware(b.spawn_at)+timedelta(days=3)).isoformat(),
            'top':[{'name':names.get(pid,'Выживший'),'damage':dmg} for pid,dmg in hits]}

@app.post('/api/boss/hit')
def boss_hit(request:Request,db:Session=Depends(db_session)):
    from boss_combat import boss_counterattack, next_turn
    with db.begin():
        # Same lock order as boss_sync() on a GET that settles an expired
        # cycle (boss row -> Player). Prevent boss/Player deadlocks.
        identify(request.headers.get('authorization',''))
        b=boss_sync(db)
        p=with_player(request,db);ready(p)
        if db.scalar(select(Battle.id).where(Battle.player_id==p.id)):
            raise ValueError('Сначала закончи бой с заражённым')
        if pending_encounter(db,p.id):
            raise ValueError('Сначала заверши случайную встречу')
        if b.hp<=0:raise ValueError('Босс уже повержен. Жди нового цикла')
        cycle=str(int(aware(b.spawn_at).timestamp()))
        entry=db.scalar(select(BossHit).where(
            BossHit.player_id==p.id,BossHit.spawn_at==cycle).with_for_update())
        if entry and (now()-aware(entry.last_hit)).total_seconds()<30:
            raise ValueError('Повторная атака через 30 секунд')
        spend_stamina(p,5)
        ammo_status=spend_legendary_round(db,p.id)
        damage=max(1,int(attack_power(db,p,ammo_status=ammo_status)*random.randint(3,5)*(1+talent_bonus(p,'boss'))))
        damage=min(damage,b.hp)
        b.hp-=damage
        wear_equipped(db,p.id,'weapon',1)
        if entry:entry.damage+=damage;entry.last_hit=now()
        else:db.add(BossHit(player_id=p.id,spawn_at=cycle,damage=damage))
        turn=next_turn(p,cycle)
        if b.hp==0:
            # Killing blow finishes the encounter before the counterattack.
            result={'message':f'{b.name} повержен!','damage_received':0,
                    'stamina_drained':0,'special':False,'phase':'Победа',
                    'defeated':False,'losses':None,'dodged':False}
        else:
            result=boss_counterattack(db,p,b,turn)
        if not result['defeated']:
            gain_xp(p,50)
            progress(db,p.id,'boss')
        return {**result,
            'message':f'Ты наносишь {damage} урона. '+result['message']
                       +(' +50 XP.' if not result['defeated'] else ''),
            'damage':damage,'hp':b.hp,'player_hp':p.hp,
            'player_stamina':p.stamina,'boss_defeated':b.hp==0,'turn':turn}

class ClanCreate(BaseModel):
    name:str=Field(min_length=3,max_length=30)

@app.get('/api/clans')
def clans(request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db)
        cs=db.scalars(select(Clan).order_by(Clan.level.desc(),Clan.treasury.desc()).limit(30)).all()
        mine=db.get(Clan,p.clan_id) if p.clan_id else None
        players=db.scalars(select(Player).where(Player.clan_id==p.clan_id).order_by(Player.level.desc())).all() if p.clan_id else []
        officers=db.scalars(select(ClanOfficer).where(ClanOfficer.clan_id==p.clan_id)).all() if p.clan_id else []
        officer_ids={o.player_id for o in officers}
        return {'mine':p.clan_id,'leader_id':mine.leader_id if mine else None,
                'can_command':can_command(db,p,mine),
                'warlord_ids':list(officer_ids),
                'members':[{'id':m.id,'name':m.name,'level':m.level,'class':m.hero_class,
                            'leader':bool(mine and m.id==mine.leader_id),'warlord':m.id in officer_ids} for m in players],
                'list':[{'id':c.id,'name':c.name,'level':c.level,'treasury':c.treasury,
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

class IdBody(BaseModel):id:int=Field(gt=0,le=9223372036854775807)

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
        officer=db.scalar(select(ClanOfficer).where(ClanOfficer.clan_id==p.clan_id,ClanOfficer.player_id==p.id))
        if officer:db.delete(officer)
        if c and c.leader_id==p.id:
            if members:c.leader_id=members[0].id
            else:
                for t in db.scalars(select(Territory).where(Territory.clan_id==c.id)):
                    collect_tax(db,t.id,force=True)
                    t.clan_id=None
                for off in db.scalars(select(ClanOfficer).where(ClanOfficer.clan_id==c.id)):
                    db.delete(off)
                for war in db.scalars(select(TerritoryWar).where(TerritoryWar.attacker_clan_id==c.id, TerritoryWar.status!='resolved')):
                    war.status='resolved';war.winner_clan_id=None
                    war.log=[*(war.log or [])[-69:],'Клан распущен: ставка аннулирована.']
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
    with db.begin():
        refresh_world(db)
        ts=db.scalars(select(Territory)).all()
        ids={t.clan_id for t in ts if t.clan_id}
        names={c.id:c.name for c in db.scalars(select(Clan).where(Clan.id.in_(ids)))}
        taxes={x.territory_id:x for x in db.scalars(select(TerritoryTax))}
        return [{'id':t.id,'name':TERRITORIES[t.id],'owner':names.get(t.clan_id,'Свободна'),
                 'clan_id':t.clan_id,'strength':t.strength,
                 'tax_pending':taxes[t.id].pending if t.id in taxes else 0,
                 'tax_collected':taxes[t.id].collected if t.id in taxes else 0,
                 'tax_next':(aware(taxes[t.id].last_collection)+timedelta(hours=5)).isoformat() if t.id in taxes else None,
                 'locations':[LOCATIONS[key]['name'] for key,region in LOCATION_TERRITORY.items() if region==t.id]}
                for t in ts]

@app.get('/api/territories/wars')
def wars(request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db)
        refresh_world(db)
        rows=db.scalars(select(TerritoryWar).where(TerritoryWar.war_date >= (local().date()-timedelta(days=3)).isoformat())
                        .order_by(TerritoryWar.war_date.desc(),TerritoryWar.territory_id).limit(30)).all()
        return {'timezone':WAR_TIMEZONE,'phase':phase(),'bid_date':war_date_for_bid(),
                'next_war_date':next_war_date(),'min_bid':MIN_BID,
                'wars':[war_view(db,w,p.id) for w in rows]}

class TerritoryBid(BaseModel):
    key:str=Field(min_length=1,max_length=30)
    amount:int=Field(ge=1,le=1000000)

@app.post('/api/territories/bid')
def territory_bid(body:TerritoryBid,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        w=place_bid(db,p,body.key,body.amount)
        return {'message':f'Ставка {w.bid} крышек принята. Торги завершатся в полночь перед КВ.'}

class PlayerIdForWar(BaseModel):
    player_id:int=Field(gt=0,le=9223372036854775807)

@app.post('/api/clans/warlord')
def make_warlord(body:PlayerIdForWar,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db)
        target=appoint_warlord(db,p,body.player_id)
        return {'message':f'{target.name} назначена воеводой клана.'}

class WarRosterBody(BaseModel):
    war_id:int=Field(gt=0,le=9223372036854775807)
    player_id:int=Field(gt=0,le=9223372036854775807)
    include:bool=True

@app.post('/api/territories/roster')
def war_roster(body:WarRosterBody,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db)
        set_roster(db,p,body.war_id,body.player_id,body.include)
        return {'message':'Боец зачислен в отряд' if body.include else 'Боец снят с КВ'}

class WarActBody(BaseModel):
    war_id:int=Field(gt=0,le=9223372036854775807)
    action:str=Field(max_length=12)

@app.post('/api/territories/act')
def act_war(body:WarActBody,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        result=war_action(db,p,body.war_id,body.action)
        return {'message':result}

@app.post('/api/territories/attack')
def old_territory_attack():
    raise HTTPException(410,'Мгновенные захваты отключены. Используй торги и КВ по расписанию.')

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
        if ITEMS[body.offer]['type'] in ('case','chest') or ITEMS[body.want]['type'] in ('case','chest'):
            raise ValueError('Премиум-кейсы и сундуки нельзя обменивать на бартерном рынке')
        # Unique GearItem has its own safe escrow marketplace. There are no
        # ItemStack rows for these keys, so asking for one created dead lots.
        legacy_stack_gear={'knife','vest','pistol','rifle'}
        if any(key in BASE_GEAR and key not in legacy_stack_gear
               for key in (body.offer,body.want)):
            raise ValueError('Уникальное снаряжение продаётся только на рынке снаряжения')
        if db.scalar(select(func.count()).select_from(MarketLot).where(MarketLot.seller_id==p.id,MarketLot.active==True))>=5:raise ValueError('Максимум 5 активных лотов')
        take_item(db,p.id,body.offer,body.qty)
        lot=MarketLot(seller_id=p.id,offered_key=body.offer,offered_qty=body.qty,wanted_key=body.want,wanted_qty=body.want_qty)
        db.add(lot)
        return {'message':'Лот размещён. Предметы зарезервированы'}

@app.post('/api/market/buy')
def market_buy(body:IdBody,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        buyer_id=int(identify(request.headers.get('authorization',''))['id'])
        seller_id=db.scalar(select(MarketLot.seller_id).where(MarketLot.id==body.id))
        if seller_id is not None:
            # Both inventories may change. Lock accounts in the same order for
            # reciprocal trades, before locking either lot or item stack.
            list(db.scalars(select(Player).where(Player.id.in_([buyer_id,seller_id]))
                            .order_by(Player.id).with_for_update()))
        p=with_player(request,db);ready(p)
        lot=db.scalar(select(MarketLot).where(MarketLot.id==body.id).with_for_update())
        if not lot or not lot.active:raise ValueError('Лот недоступен')
        if lot.seller_id==p.id:raise ValueError('Нельзя покупать свой лот')
        if lot.offered_key not in ITEMS or lot.wanted_key not in ITEMS:
            raise ValueError('Лот с неизвестным предметом недоступен. Продавец может отменить его.')
        if ITEMS[lot.offered_key]['type'] in ('case','chest') or ITEMS[lot.wanted_key]['type'] in ('case','chest'):
            raise ValueError('Этот премиум-лот больше недоступен. Продавец может отменить его.')
        if any(key in BASE_GEAR and key not in {'knife','vest','pistol','rifle'}
               for key in (lot.offered_key,lot.wanted_key)):
            raise ValueError('Уникальное оружие обменивается на рынке снаряжения')
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
        top=db.scalars(select(Player).where(Player.id!=p.id,Player.hero_class.isnot(None),
                           Player.banned.is_(False),Player.frozen.is_(False)).order_by(Player.rating.desc()).limit(20)).all()
        return {'match':pvp_view(db,match) if match else None,
            'league':league(p.rating),'remaining_rewarded':daily_remaining(p,now()),
            'daily_cap':DAILY_REWARDED_DUELS,
            'players':[{'id':x.id,'name':x.name,'level':x.level,
                        'rating':x.rating,'league':league(x.rating)['name']} for x in top]}

def pvp_view(db,m):
    if not m:return None
    names={p.id:p.name for p in db.scalars(select(Player).where(Player.id.in_([m.challenger_id,m.defender_id])))}
    return {'id':m.id,'state':m.state,'challenger':{'id':m.challenger_id,'name':names.get(m.challenger_id,'Игрок'),'hp':m.hp_a},
            'defender':{'id':m.defender_id,'name':names.get(m.defender_id,'Игрок'),'hp':m.hp_b},
            'current_id':m.current_id,'log':[x for x in (m.log or []) if not x.startswith('!pvp:')][-8:],
            'turn_seconds':90,'updated_at':aware(m.updated_at).isoformat()}

class PlayerId(BaseModel):player_id:int=Field(gt=0,le=9223372036854775807)

@app.post('/api/pvp/challenge')
def pvp_challenge(body:PlayerId,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        pid=int(identify(request.headers.get('authorization',''))['id'])
        if body.player_id==pid:raise ValueError('Нельзя вызвать себя')
        # Lock both accounts in ID order before testing active matches. This
        # serializes competing challenges for the same defender on PostgreSQL.
        locked={x.id:x for x in db.scalars(select(Player).where(Player.id.in_([pid,body.player_id]))
                                        .order_by(Player.id).with_for_update())}
        p=with_player(request,db);ready(p)
        other=locked.get(body.player_id)
        if not other or not other.hero_class or other.banned or other.frozen:raise ValueError('Игрок недоступен')
        pending=db.scalar(select(PvPMatch).where(or_(PvPMatch.challenger_id.in_([p.id,other.id]),PvPMatch.defender_id.in_([p.id,other.id])),PvPMatch.state.in_(['pending','active'])))
        if pending:raise ValueError('Один из игроков уже участвует в дуэли')
        spend_stamina(p,10)
        m=PvPMatch(challenger_id=p.id,defender_id=other.id,hp_a=max_hp(p),hp_b=max_hp(other),log=[f'{p.name} вызывает {other.name} на дуэль'])
        db.add(m)
        return {'message':'Вызов отправлен. Соперник увидит его на арене'}

class PvPDecision(BaseModel):id:int=Field(gt=0,le=9223372036854775807);action:str=Field(max_length=20)

@app.post('/api/pvp/act')
def pvp_act(body:PvPDecision,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        pid=int(identify(request.headers.get('authorization',''))['id'])
        m=db.scalar(select(PvPMatch).where(PvPMatch.id==body.id).with_for_update())
        if not m or pid not in (m.challenger_id,m.defender_id):raise ValueError('Нет такой дуэли')
        # Match first, then both participants in stable order. The loser and
        # winner balances are both protected before a result is calculated.
        list(db.scalars(select(Player).where(Player.id.in_([m.challenger_id,m.defender_id]))
                        .order_by(Player.id).with_for_update()))
        p=with_player(request,db);ready(p)
        if m.state=='pending':
            if body.action=='cancel' and p.id==m.challenger_id:m.state='cancelled';return {'message':'Вызов отозван'}
            if body.action not in ('accept','decline') or p.id!=m.defender_id:raise ValueError('Ожидается решение соперника')
            if body.action=='decline':m.state='declined';return {'message':'Вызов отклонён'}
            m.state='active';m.current_id=m.challenger_id;m.updated_at=now()
            return {'message':'Дуэль началась! Первый ход за инициатором'}
        if m.state!='active':raise ValueError('Дуэль завершена')
        if body.action=='claim_timeout':
            if m.current_id==p.id or now()-aware(m.updated_at)<=timedelta(seconds=90):
                raise ValueError('Время хода соперника ещё не вышло')
            winner_id=p.id
        elif body.action=='surrender':
            winner_id=m.defender_id if p.id==m.challenger_id else m.challenger_id
        else:
            if m.current_id!=p.id:raise ValueError('Сейчас ход соперника')
            permitted=('attack','crit','defend','heal','steal','feint','peace')
            if body.action not in permitted:raise ValueError('Неизвестная тактика PvP')
            if now()-aware(m.updated_at)>timedelta(seconds=90):
                winner_id=m.defender_id if p.id==m.challenger_id else m.challenger_id
            else:
                target=db.get(Player,m.defender_id if p.id==m.challenger_id else m.challenger_id)
                state=list(m.log or [])
                mine='!pvp:steal:'+str(p.id)
                peace='!pvp:peace:'+str(target.id)
                persistent=[entry for entry in state if entry.startswith('!pvp:steal:')]
                latest=[entry for entry in state if not entry.startswith('!pvp:')]
                if body.action=='peace' and peace in state:
                    m.state='finished';m.current_id=None;m.updated_at=now()
                    m.log=persistent+latest[-10:]+[f'{p.name} и {target.name} заключили перемирие. Ничья!']
                    return {'message':'Дуэль завершена миром. Рейтинг и награды не изменены.'}
                if body.action=='peace':
                    persistent.append('!pvp:peace:'+str(p.id))
                    message=f'{p.name} предлагает мир. Соперник может согласиться.'
                    damage=0
                elif body.action=='steal':
                    if mine in state:raise ValueError('Кража доступна один раз за дуэль')
                    amount=min(max(0,target.caps),random.randint(7,20) if p.hero_class=='thief' else random.randint(4,12))
                    target.caps-=amount;p.caps+=amount
                    persistent.append(mine)
                    damage=0
                    message=f'{p.name}: кража — {amount} крышек'
                elif body.action=='heal':
                    # PvP HP lives on the match, but treatment uses a real
                    # medkit from the player's stack inventory.
                    take_item(db,p.id,'medkit')
                    restored=int(45*CLASSES[p.hero_class]['healing']*(1+talent_bonus(p,'healing')))
                    if p.id==m.challenger_id:m.hp_a=min(max_hp(p),m.hp_a+restored)
                    else:m.hp_b=min(max_hp(p),m.hp_b+restored)
                    damage=0
                    message=f'{p.name}: лечение +{restored} HP (потрачена аптечка)'
                else:
                    damage=0
                    if body.action!='defend':
                        strength={'attack':1.0,'crit':1.75,'feint':.7}[body.action]
                        # Critical strike is stronger but may miss; a feint
                        # ignores the opponent's armor/defense at reduced power.
                        ammo_status=spend_legendary_round(db,p.id)
                        hit=body.action!='crit' or random.random()<.60+min(.25,talent_bonus(p,'crit'))
                        if hit:
                            damage=max(1,int(attack_power(db,p,ammo_status=ammo_status)*random.uniform(.55,1.0)*strength))
                            if body.action!='feint':
                                armor=gear_stats(db,target.id)['defense']
                                damage=max(1,damage-min(armor,int(damage*.65)))
                                if latest and latest[-1]==f'{target.name}: защита — 0 урона':
                                    damage=max(1,int(damage*.65))
                            dodge=min(.60,CLASSES[target.hero_class].get('dodge',0)
                                           +target.stats.get('agility',0)*.005
                                           +talent_bonus(target,'dodge'))
                            if random.random()<dodge:damage=0
                            if damage:
                                damage=max(1,int(damage*(1-min(.65,CLASSES[target.hero_class].get('mitigation',0)
                                                         +talent_bonus(target,'mitigation')))))
                    if body.action!='defend':wear_equipped(db,p.id,'weapon',1)
                    message=f'{p.name}: '+({'attack':'атака','crit':'критическая атака',
                        'feint':'финт','defend':'защита'}[body.action])+f' — {damage} урона'+(ammo_message(ammo_status) if body.action!='defend' else '')
                if damage:
                    wear_equipped(db,target.id,'armor',1)
                    if p.id==m.challenger_id:
                        m.hp_b=max(0,m.hp_b-damage);dead=m.hp_b==0
                    else:
                        m.hp_a=max(0,m.hp_a-damage);dead=m.hp_a==0
                else:dead=False
                m.log=persistent+latest[-10:]+[message]
                m.current_id=target.id;m.updated_at=now()
                if not dead:return {'message':message}
                winner_id=p.id
        winner=db.get(Player,winner_id);loser=db.get(Player,m.challenger_id if winner_id==m.defender_id else m.defender_id)
        rated,delta=settle_rated_duel(winner,loser,now())
        winner.pvp_wins+=1
        if rated:
            winner.caps+=35;gain_xp(winner,80);progress(db,winner.id,'pvp')
        m.state='finished';m.current_id=None;m.updated_at=now()
        m.log=[*(m.log or []),f'{winner.name} побеждает в дуэли!'][-12:]
        reward=(' +35 крышек, +80 XP, +'+str(delta)+' Elo'
                if rated else ' Без повторных наград и Elo: лимит дня или повторный соперник.')
        return {'message':f'Дуэль завершена. Победитель: {winner.name}. '+reward,
                'rated':rated,'elo_delta':delta,'league':league(winner.rating)['name']}

SHOP={key:{'caps':price} for key,price in SHOP_PRICES.items()}

@app.post('/api/pets/adopt')
def adopt_pet(body:Choice,request:Request,db:Session=Depends(db_session)):
    """Merchant companion: random rescue is cheaper than choosing a species."""
    with db.begin():
        p=with_player(request,db);ready(p)
        if pet_status(p):raise ValueError('У тебя уже есть питомец')
        if body.key!='random' and body.key not in PETS:
            raise ValueError('Неизвестный питомец')
        cost=750 if body.key=='random' else 1250
        if p.caps<cost:raise ValueError(f'Для приручения нужно {cost} крышек')
        key=secrets.choice(tuple(PETS)) if body.key=='random' else body.key
        p.caps-=cost
        p.stats={**(p.stats or {}),'_pet':{'key':key,'level':1,'xp':0}}
        return {'message':f'{PETS[key]["icon"]} Теперь с тобой {PETS[key]["name"]}. '
                          'Помощь в бою доступна один раз за столкновение.',
                'pet':pet_status(p)}


@app.get('/api/shop')
def shop():return [{'key':k,'price':v['caps'],**ITEMS[k]} for k,v in SHOP.items()]

@app.post('/api/shop/buy')
def shop_buy(body:Choice,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        if body.key not in SHOP:raise ValueError('Нет такого товара')
        cost=SHOP[body.key]['caps']
        if p.caps<cost:raise ValueError('Недостаточно крышек')
        p.caps-=cost
        if body.key in BASE_GEAR:create_gear(db,p.id,body.key,'common','shop')
        else:give_item(db,p.id,body.key)
        return {'message':f'Куплено: {ITEMS[body.key]["name"]}'}

# Monetization: real Telegram Stars invoices, delivery only on authenticated successful_payment updates.
STAR_OFFERS={'zombo_100':(100,100),'zombo_550':(500,550),'zombo_1800':(1500,1800),'zombo_6500':(5000,6500)}

PREMIUM_OFFERS={
    **{key:{'name':f'Открыть {CASES[key]["name"]}','price':price,
           'kind':'case','desc':'Коллекционная пушка из кейса · Zombo 💎'}
       for key,price in GEM_CASE_PRICES.items()},
    **{key:{'name':f'{data["icon"]} {data["name"]}','price':data['price'],
           'kind':'chest','drops':data['drops'],'desc':data['description']}
       for key,data in CHESTS.items()},
    'vip_7':{'name':'VIP на 7 дней','price':250,'days':7,'kind':'vip','desc':'Ускоренная энергия и +20% XP'},
    'vip_14':{'name':'VIP на 14 дней','price':450,'days':14,'kind':'vip','desc':'Ускоренная энергия и +20% XP'},
    'vip_30':{'name':'VIP на 30 дней','price':800,'days':30,'kind':'vip','desc':'Ускоренная энергия и +20% XP'},
    'xp_day':{'name':'×2 опыт на 24 часа','price':100,'days':1,'kind':'xp','desc':'Ускоренная прокачка'},
    'loot_day':{'name':'×2 шанс добычи на 24 часа','price':100,'days':1,'kind':'loot','desc':'Больше находок в PvE'},
    'insurance_day':{'name':'Страховка на 24 часа','price':200,'days':1,'kind':'insurance','desc':'При смерти: −5% крышек, −10% XP и припасов вместо обычных потерь'},
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
        if offer['kind'] in ('case','chest'):
            # Store a redeemable box. Purchases and redemption are separate,
            # so a full gear locker never destroys paid gems or case items.
            give_item(db,p.id,body.key,1)
            return {'message':f'Приобретено: {offer["name"]}. Открой в инвентаре!',
                    'item':body.key}
        if offer['kind']=='insurance':
            from game import insurance_active
            flags=dict(p.stats or {})
            try:end=datetime.fromisoformat(flags['_insurance_until']) if insurance_active(p) else None
            except (ValueError,KeyError):end=None
            start=max(now(),aware(end)) if end else now()
            flags['_insurance_until']=(start+timedelta(days=offer['days'])).isoformat()
            p.stats=flags
        else:
            field={'vip':'vip_until','xp':'xp_boost_until','loot':'loot_boost_until'}[offer['kind']]
            end=getattr(p,field)
            start=max(now(),aware(end)) if end else now()
            setattr(p,field,start+timedelta(days=offer['days']))
        return {'message':f'Активировано: {offer["name"]}'}

@app.get('/api/stars')
def stars_offers():return [{'key':k,'stars':s,'zombo':z} for k,(s,z) in STAR_OFFERS.items()]

def invoice_offer(db, payload, payer_id, currency, amount, *, checkout=False):
    """Resolve an issued invoice to its fixed reward without trusting update fields."""
    if currency!='XTR' or not isinstance(amount,int):return None
    if isinstance(payload,str) and payload.startswith('z1:'):
        invoice=db.get(StarInvoice,payload)
        if not invoice or invoice.player_id!=payer_id or invoice.stars!=amount:return None
        if checkout and aware(invoice.expires_at)<=now():return None
        return invoice.player_id,invoice.stars,invoice.zombo
    # In-flight links from 0.8.0 must remain redeemable during the rollout.
    if ACCEPT_LEGACY_STAR_INVOICES and isinstance(payload,str):
        match=re.fullmatch(r'(\d+):([a-z][a-z0-9_]{0,54}):([0-9a-f]{20})',payload)
        if match:
            pid,key,_=match.groups()
            offer=STAR_OFFERS.get(key)
            if int(pid)==payer_id and offer and offer[0]==amount:
                return int(pid),offer[0],offer[1]
    return None

@app.post('/api/stars/invoice')
async def invoice(body:Choice,request:Request,db:Session=Depends(db_session)):
    with db.begin():
        p=with_player(request,db);ready(p)
        if body.key not in STAR_OFFERS:raise ValueError('Нет такого набора')
        stars,zombo=STAR_OFFERS[body.key]
        payload='z1:'+secrets.token_urlsafe(24)
        db.add(StarInvoice(payload=payload,player_id=p.id,offer_key=body.key,stars=stars,zombo=zombo,
                           expires_at=now()+timedelta(hours=24)))
    # Do not hold a player row lock while waiting for Telegram's network API.
    result=await telegram_api('createInvoiceLink',{'title':f'{zombo} Zombo','description':'Премиум-валюта для ZOMBO',
        'payload':payload,'currency':'XTR','prices':[{'label':f'{zombo} Zombo','amount':stars}]})
    if not result.get('ok') or not result.get('result'):
        raise HTTPException(502,'Не удалось сформировать счёт Telegram Stars')
    return {'url':result['result']}

def bot_top(db:Session,mode:str,player_id:int):
    aliases={'':'level','level':'level','lvl':'level','уровень':'level',
             'kills':'kills','zombies':'kills','зомби':'kills',
             'pvp':'pvp','arena':'pvp','арена':'pvp'}
    sort=aliases.get(mode)
    if sort is None:return 'Рейтинги: /top level · /top kills · /top pvp'
    title=LEADERBOARD_SORTS[sort][0]
    rows=leaderboard_players(db,sort,10)
    lines=[]
    for index,p in enumerate(rows,1):
        score=(f'ур. {p.level}' if sort=='level' else
               f'{p.kills} побед' if sort=='kills' else f'{p.rating} рейтинга · {p.pvp_wins} побед')
        lines.append(f'{index}. {p.name[:40]} — {score}'+(' ← ты' if p.id==player_id else ''))
    return f'🏆 ТОП-10 · {title}\n'+('\n'.join(lines) if lines else 'Пока нет участников.')+'\n\n/top level · /top kills · /top pvp'

def bot_quests(db:Session,player_id:int):
    p=db.get(Player,player_id)
    if not p or not p.hero_class:return 'Сначала создай персонажа в игре.'
    progress_rows={q.code:q for q in db.scalars(select(QuestProgress).where(QuestProgress.player_id==player_id))}
    lines=[]
    for key,definition in QUESTS.items():
        q=progress_rows.get(key)
        amount=min(q.amount if q else 0,definition['target'])
        status='получено' if q and q.claimed else 'награда готова' if amount>=definition['target'] else f'{amount}/{definition["target"]}'
        lines.append(f'• {definition["name"]}: {status}')
    return '▣ ЗАДАНИЯ\n'+'\n'.join(lines)+'\n\nНаграды забираются в Mini App.'

def bot_boss(db:Session):
    boss=boss_sync(db)
    cycle=str(int(aware(boss.spawn_at).timestamp()))
    leaders=db.execute(select(BossHit.player_id,func.sum(BossHit.damage))
        .where(BossHit.spawn_at==cycle).group_by(BossHit.player_id)
        .order_by(func.sum(BossHit.damage).desc()).limit(3)).all()
    names={p.id:p.name for p in db.scalars(select(Player).where(Player.id.in_([pid for pid,_ in leaders])))}
    remaining=max(0,round(((aware(boss.spawn_at)+timedelta(days=3))-now()).total_seconds()/3600))
    top='\n'.join(f'{i}. {names.get(pid,"Выживший")[:40]} — {damage} урона' for i,(pid,damage) in enumerate(leaders,1))
    return f'☣ МИРОВОЙ БОСС\n{boss.name}\nHP: {boss.hp}/{boss.max_hp}\nДо смены цикла: ~{remaining} ч.\n\nТОП УРОНА\n{top or "Пока никто не атаковал."}'

def bot_raid(db:Session,player_id:int):
    run=db.scalar(select(RaidRun).join(RaidMember,RaidMember.run_id==RaidRun.id)
        .where(RaidMember.player_id==player_id).order_by(RaidRun.id.desc()).limit(1).with_for_update(of=RaidRun))
    if not run:return 'Сейчас ты не состоишь в рейде.'
    if run.status in ('lobby','active') and aware(run.expires_at)<=now():run.status='expired'
    state={'lobby':'сбор группы','active':f'этап {run.stage+1}/3',
           'cleared':'победа','failed':'поражение','expired':'время вышло'}.get(run.status,run.status)
    member=db.scalar(select(RaidMember).where(RaidMember.run_id==run.id,RaidMember.player_id==player_id))
    reward='Награда получена.' if member and member.rewarded else 'Награда доступна в Mini App.' if run.status=='cleared' and member and member.actions>0 else ''
    return f'⚔ РЕЙД #{run.id}\nСтатус: {state}\nУрон: {member.contribution if member else 0}\n{reward}'.strip()

def bot_expedition(db:Session,player_id:int):
    settle_player_expedition(db,player_id)
    run=db.scalar(select(ExpeditionRun).join(ExpeditionMember,
        ExpeditionMember.run_id==ExpeditionRun.id).where(ExpeditionMember.player_id==player_id)
        .order_by(ExpeditionRun.id.desc()).limit(1))
    if not run:return 'У тебя пока нет дальней экспедиции.'
    member=db.scalar(select(ExpeditionMember).where(ExpeditionMember.run_id==run.id,
        ExpeditionMember.player_id==player_id))
    status={'lobby':'сбор отряда','active':'отряд в пути','cleared':'успех',
            'failed':'неудача','expired':'группа распущена'}.get(run.status,run.status)
    detail=''
    if run.status=='active' and run.finishes_at:
        hours=max(0,round((aware(run.finishes_at)-now()).total_seconds()/3600,1))
        detail=f'\nДо возвращения: ~{hours} ч.'
    elif run.status in ('cleared','failed'):
        detail='\nНаграда получена.' if member.rewarded else '\nНаграда ждёт в Mini App.'
    return f'⌖ ЭКСПЕДИЦИЯ #{run.id}\nСтатус: {status}{detail}'

@app.post('/telegram/webhook')
async def webhook(request:Request):
    if not SECRET or not hmac.compare_digest(request.headers.get('x-telegram-bot-api-secret-token',''),SECRET):
        raise HTTPException(403,'Forbidden')
    data=await request.json()
    # Telegram includes update_id on real deliveries. Older tests and legacy
    # manually sent messages without one retain their original behavior.
    update_id = data.get('update_id')
    if update_id is None:
        return await _dispatch_update(data)
    with SessionLocal.begin() as db:
        status, lease = claim_update(db, update_id)
    if status == 'duplicate':
        return {'ok':True, 'duplicate':True}
    if status == 'busy':
        raise HTTPException(503,'Telegram update is being processed')
    try:
        result = await _dispatch_update(data)
    except BaseException:
        with SessionLocal.begin() as db:
            finish_update(db, update_id, completed=False, lease=lease)
        raise
    with SessionLocal.begin() as db:
        finish_update(db, update_id, completed=True, lease=lease)
    return result


async def _dispatch_update(data):
    if 'pre_checkout_query' in data:
        q=data['pre_checkout_query'];valid=False
        try:
            with SessionLocal() as db:
                valid=invoice_offer(db,q['invoice_payload'],q['from']['id'],q['currency'],q['total_amount'],checkout=True) is not None
        except (ValueError,KeyError,TypeError):pass
        reply = await telegram_api('answerPreCheckoutQuery',{'pre_checkout_query_id':q['id'],'ok':valid,'error_message':'Ошибка данных заказа' if not valid else None})
        if not reply.get('ok'):raise HTTPException(503,'Telegram checkout response failed')
    msg=data.get('message')
    if not msg:return {'ok':True}
    chat_id=msg.get('chat',{}).get('id');user=msg.get('from',{})
    if not chat_id or not user:return {'ok':True}
    if 'successful_payment' in msg:
        payment=msg['successful_payment']
        credited=False
        try:
            with SessionLocal.begin() as db:
                offer=invoice_offer(db,payment['invoice_payload'],user['id'],payment['currency'],payment['total_amount'])
                charge_id=payment['telegram_payment_charge_id']
                if offer:
                    pid,stars,zombo=offer
                    p=db.scalar(select(Player).where(Player.id==pid).with_for_update())
                    if not p:raise ValueError('Payment recipient missing')
                    if not db.get(Payment,charge_id):
                        tag_resource_operation(db, f'stars:{charge_id}', stable=True)
                        p.zombo+=zombo
                        db.add(Payment(id=charge_id,player_id=p.id,stars=stars,zombo=zombo))
                        credited=True
                elif not db.get(PaymentReview,charge_id):
                    db.add(PaymentReview(charge_id=charge_id,player_id=int(user['id']),
                                         payload=str(payment['invoice_payload'])[:128],
                                         currency=str(payment['currency'])[:8],amount=int(payment['total_amount']),
                                         reason='invoice_not_verified'))
                    logger.warning('Stars payment requires review: payer=%s',user['id'])
            if credited:
                await telegram_api('sendMessage',{'chat_id':chat_id,'text':'💎 Покупка успешно зачислена! Открой ZOMBO и проверь баланс.'})
        except Exception:
            logger.exception('payment processing error')
            raise HTTPException(503,'Не удалось обработать платёж')
        return {'ok':True}
    parts=(msg.get('text') or '').strip().split(maxsplit=1)
    text=parts[0].split('@',1)[0].lower() if parts else ''
    argument=parts[1].strip().split()[0].lower() if len(parts)>1 and parts[1].strip() else ''
    if text in ('/start','/help','/profile','/daily','/enemies','/clan','/map','/skills','/bag','/story',
                '/top','/rank','/quests','/boss','/raid','/expedition','/id','/admin'):
        if text in ('/id', '/admin'):
            if msg.get('chat', {}).get('type') != 'private':
                reply = '🔒 Напиши команду в личных сообщениях боту.'
            elif text == '/id':
                reply = f'🆔 Твой Telegram ID: {int(user["id"])}.\nДобавить администратора: Railway → zombo-web → Variables → ADMIN_IDS.'
            elif int(user['id']) in ADMIN_IDS:
                reply = '🛡 Доступ подтверждён. Открой игру → Меню → Админский терминал. Без класса сначала создай персонажа.'
            elif not ADMIN_IDS:
                reply = f'🔒 Админка не настроена. Твой Telegram ID: {int(user["id"])}.\nRailway → zombo-web → Variables → ADMIN_IDS → вставь свой ID.'
            else:
                reply = f'🔒 Твой Telegram ID: {int(user["id"])}.\nДобавь этот номер в ADMIN_IDS на Railway.'
        elif text=='/daily':
            with SessionLocal.begin() as db:
                if data.get('update_id') is not None:
                    tag_resource_operation(db, f'telegram-daily:{data["update_id"]}', stable=True)
                p=db.scalar(select(Player).where(Player.id==int(user['id'])).with_for_update())
                if not p or not p.hero_class:reply='Сначала создай персонажа в игре.'
                elif p.banned or p.frozen:reply='Персонаж заблокирован.'
                elif p.last_daily==now().strftime('%Y-%m-%d'):reply='Сегодняшний набор уже получен. Возвращайся завтра!'
                else:
                    p.last_daily=now().strftime('%Y-%m-%d');p.caps+=75;p.stamina=min(500,p.stamina+80)
                    give_item(db,p.id,'food');give_item(db,p.id,'water');gain_xp(p,45)
                    reply='🎁 +75 крышек, +80 энергии, еда, вода и +45 XP!'
        elif text in ('/top','/rank'):
            with SessionLocal() as db:reply=bot_top(db,argument,int(user['id']))
        elif text=='/quests':
            with SessionLocal() as db:reply=bot_quests(db,int(user['id']))
        elif text=='/boss':
            with SessionLocal.begin() as db:reply=bot_boss(db)
        elif text=='/raid':
            with SessionLocal.begin() as db:reply=bot_raid(db,int(user['id']))
        elif text=='/expedition':
            with SessionLocal.begin() as db:reply=bot_expedition(db,int(user['id']))
        elif text=='/enemies':
            with SessionLocal() as db:
                p=db.get(Player,int(user['id']))
                codex=(p.stats or {}).get('_enemy_codex',{}) if p else {}
                seen=len(codex);defeated=sum(1 for v in codex.values() if v.get('kills',0)>0)
                rows=[f"{ENEMIES[k]['name']}: {v.get('kills',0)} побед" for k,v in codex.items() if k in ENEMIES]
                reply=f'☣ БЕСТИАРИЙ ZOMBO\nОбнаружено: {seen}/10, побеждено: {defeated}/10\n'+('\n'.join(rows) if rows else 'Пока не встретился ни один вид.')+'\n\nЗа первый трофей вида: +25 XP и 15 крышек.'
        elif text=='/clan':
            with SessionLocal() as db:
                p=db.get(Player,int(user['id']))
                clan=db.get(Clan,p.clan_id) if p and p.clan_id else None
                holdings=db.scalars(select(Territory).where(Territory.clan_id==clan.id)).all() if clan else []
                title=f'Твой клан: {clan.name}\nКазна: {clan.treasury} крышек\nТерриторий: {len(holdings)}' if clan else 'У тебя пока нет клана. Создай или вступи в Mini App.'
                reply='⚔ КЛАНОВЫЕ ВОЙНЫ\n'+title+f'\n\nПн / ср / пт — ставки\nВт / чт / сб — состав 10:00–15:00, война 16:00–16:30 ({WAR_TIMEZONE}).\nНалог с заражённых — 1%, сбор раз в 5 часов.'
        elif text=='/map':
            with SessionLocal() as db:
                p=db.get(Player,int(user['id']))
                if p:
                    loc=LOCATIONS.get(p.location,LOCATIONS['base'])
                    area=LOCATION_TERRITORY.get(p.location)
                    owner='Зомби'
                    if area:
                        terr=db.get(Territory,area)
                        if terr and terr.clan_id:
                            clan=db.get(Clan,terr.clan_id)
                            owner=clan.name if clan else 'Зомби'
                    reply=f'⌖ ТВОЯ ПОЗИЦИЯ\n{loc["name"]} · опасность {loc["threat"]}/5\nКонтроль: {owner}\n\nОткрой карту, чтобы выбрать следующую зону.'
                else: reply='Ты ещё не создал персонажа. Открой игру.'
        elif text=='/story':
            with SessionLocal() as db:
                p=db.get(Player,int(user['id']))
                if not p or not p.hero_class:
                    reply='📻 СЮЖЕТ ZOMBO\nВыбери класс, чтобы начать кампанию «Протокол Седьмой».'
                else:
                    st=db.get(StoryProgress,p.id)
                    chapter_index=min(st.chapter if st else 0,10)
                    name=CHAPTERS[chapter_index]['title'] if chapter_index<10 else 'История завершена'
                    progress_count=st.stage if st else 0
                    unlock=CHAPTERS[chapter_index]['level'] if chapter_index<10 else 0
                    reply=f'📻 ПРОТОКОЛ СЕДЬМОЙ\nГлав пройдено: {chapter_index}/10\nТекущая глава: {name}\nЭтап: {progress_count+1 if chapter_index<10 else "финал"}\nРекомендуемый уровень: {unlock}\n\nНайди пункт «Сюжетная кампания» в Mini App.'
        elif text=='/skills':
            with SessionLocal() as db:
                p=db.get(Player,int(user['id']))
                if p:
                    branches=SKILL_TREES.get(p.hero_class,[])
                    reply=f'✦ ПРОКАЧКА\n{CLASSES.get(p.hero_class,{}).get("name","Выживший")} · уровень {p.level}\nОчки талантов: {p.skill_points}\nОчки характеристик: {p.stat_points}\n\n'+(' / '.join(x['name'].title() for x in branches) if branches else 'Выбери класс в игре.')
                else: reply='Сначала создай персонажа в игре.'
        elif text=='/bag':
            with SessionLocal() as db:
                p=db.get(Player,int(user['id']))
                if not p:reply='Сначала создай персонажа в игре.'
                else:
                    stacks=db.scalars(select(ItemStack).where(ItemStack.player_id==p.id,ItemStack.quantity>0).order_by(ItemStack.item_key).limit(12)).all()
                    reply='▣ РЮКЗАК\n'+('\n'.join(f"{ITEMS[i.item_key]['name']}: {i.quantity}" for i in stacks if i.item_key in ITEMS) if stacks else 'Пусто')+'\n\nПолный инвентарь доступен в Mini App.'
        elif text=='/profile':
            with SessionLocal() as db:
                p=db.get(Player,int(user['id']))
                reply=f'🧟 {p.name}\nУровень {p.level} · {CLASSES.get(p.hero_class,{}).get("name","Новичок")}\n❤️ {p.hp}/{max_hp(p)} · ⚡ {p.stamina}/500\nКрышки: {p.caps}' if p else 'Открой игру, чтобы создать персонажа.'
        elif text=='/help':reply='📟 КОМАНДЫ ZOMBO\n/id — мой Telegram ID\n/admin — админский доступ\n/start — начать\n/profile — герой\n/skills — таланты\n/map — позиция\n/enemies — бестиарий\n/bag — рюкзак\n/clan — клан и КВ\n/daily — ежедневные припасы\n/quests — задания\n/boss — мировой босс\n/raid — мой рейд\n/expedition — дальняя экспедиция\n/top — лидеры по уровню\n/top kills — победы над зомби\n/top pvp — рейтинг арены'
        else:reply='🧟 ZOMBO: After the Fall\n1. Выбери класс и отправься в Мёртвый лес.\n2. Побеждай заражённых и открывай досье врагов.\n3. Прокачивай три ветки талантов.\n4. Вступи в клан и борись за территории!\n\nКоманды: /help'
        message={'chat_id':chat_id,'text':reply}
        if PUBLIC_URL:message['reply_markup']={'inline_keyboard':[[{'text':'🎮 Открыть ZOMBO','web_app':{'url':PUBLIC_URL}}]]}
        sent = await telegram_api('sendMessage',message)
        if not sent.get('ok'):raise HTTPException(503,'Telegram message delivery failed')
    return {'ok':True}

