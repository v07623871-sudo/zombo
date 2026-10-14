"""ZOMBO cooperative instanced raids (3–10 players, three stages).

No existing production DB table is modified. Raid state and payouts persist in new
SQLAlchemy tables. Hook by calling install_raids(app, with_player, ready) before
FastAPI lifespan (Base.metadata.create_all).
"""
from __future__ import annotations
from datetime import timedelta, timezone, datetime
import random
from fastapi import APIRouter, Request, Depends
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, JSON, Boolean, ForeignKey, UniqueConstraint, select, func
from sqlalchemy.orm import Session
from models import Base, SessionLocal, Player, now
from game import give_item, take_item, item_count, attack_power, spend_stamina, max_hp, gain_xp, talent_bonus
from armory_content import raid_case_drop
from legendary_ammo import spend_legendary_round, ammo_message
from notifications import queue_notification

RAIDS={
    'outpost':{'name':'Аванпост «Ноль»','level':1,'duration_hours':1,'enemy_names':['Заражённые у ворот','Коридор мясников','Командир-реанимант'],
               'hp':100,'damage':8,'xp':130,'caps':85,'icon':'🧟','desc':'Первый групповой рейд. Штурмуйте заражённый аванпост.'},
    'vault':{'name':'Затопленный бункер','level':10,'duration_hours':3,'enemy_names':['Ржавые стражи','Стая подземных охотников','Танк-безликий'],
             'hp':200,'damage':16,'xp':310,'caps':180,'icon':'☢','desc':'Укреплённые тоннели и элитные мутанты.'},
    'citadel':{'name':'Последняя цитадель','level':25,'duration_hours':6,'enemy_names':['Блокпост смерти','Лаборатория мутаций','Матерь роя'],
               'hp':370,'damage':29,'xp':700,'caps':430,'icon':'⚔','desc':'Максимальная сложность, ценная добыча.'},
}
MIN_PARTY=3
MAX_PARTY=10
ACTION_COOLDOWN=12
LOBBY_LIFETIME=6*3600

class RaidRun(Base):
    __tablename__='raid_runs'
    id=Column(Integer,primary_key=True,autoincrement=True)
    creator_id=Column(BigInteger,nullable=False,index=True)
    scenario=Column(String(30),nullable=False)
    status=Column(String(18),default='lobby',nullable=False,index=True)
    stage=Column(Integer,default=0,nullable=False)
    enemy_hp=Column(Integer,default=0,nullable=False)
    enemy_max_hp=Column(Integer,default=0,nullable=False)
    created_at=Column(DateTime(timezone=True),default=now,nullable=False)
    started_at=Column(DateTime(timezone=True),nullable=True)
    expires_at=Column(DateTime(timezone=True),nullable=False)
    log=Column(JSON,default=list)

class RaidMember(Base):
    __tablename__='raid_members'
    id=Column(Integer,primary_key=True,autoincrement=True)
    run_id=Column(Integer,ForeignKey('raid_runs.id'),nullable=False,index=True)
    player_id=Column(BigInteger,ForeignKey('players.id'),nullable=False,index=True)
    hp=Column(Integer,default=100,nullable=False)
    max_hp=Column(Integer,default=100,nullable=False)
    contribution=Column(Integer,default=0,nullable=False)
    actions=Column(Integer,default=0,nullable=False)
    rewarded=Column(Boolean,default=False,nullable=False)
    last_action=Column(DateTime(timezone=True),nullable=True)
    __table_args__=(UniqueConstraint('run_id','player_id',name='unique_raid_member'),)

class RaidRequest(BaseModel):
    id:int=Field(gt=0,le=9223372036854775807)

class ScenarioRequest(BaseModel):
    key:str=Field(min_length=1,max_length=30)

class RaidActionRequest(BaseModel):
    id:int=Field(gt=0,le=9223372036854775807)
    action:str=Field(pattern=r'^(attack|guard|medkit|rescue)$')
    target_id:int|None=None


def aware(dt):
    if dt is None:return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def raid_log(raid:RaidRun,text:str):
    raid.log=[*(raid.log or [])[-39:],text[:260]]


def current_raid(db:Session,player_id:int):
    return db.scalar(select(RaidRun).join(RaidMember,RaidMember.run_id==RaidRun.id)
        .where(RaidMember.player_id==player_id,RaidRun.status.in_(['lobby','active']))
        .order_by(RaidRun.id.desc()).limit(1))


def close_expired(db:Session,at:datetime|None=None):
    stamp=at or now()
    # Only overdue sessions are settled; new raids can be created afterward.
    for run in db.scalars(select(RaidRun).where(RaidRun.status.in_(['lobby','active']),RaidRun.expires_at<stamp).with_for_update()):
        run.status='expired'
        raid_log(run,'Время истекло. Экспедиция не вернулась.')
        for member_id in db.scalars(select(RaidMember.player_id).where(RaidMember.run_id==run.id)):
            queue_notification(db,member_id,f'raid:{run.id}:deadline:{member_id}',
                               'raids','raid_deadline',f'Рейд «{RAIDS[run.scenario]["name"]}» завершился по времени.')
    db.flush()


def start_stage(run:RaidRun,count:int):
    data=RAIDS[run.scenario]
    run.enemy_max_hp=int(data['hp']*max(3,count)*(1+.52*run.stage))
    run.enemy_hp=run.enemy_max_hp
    raid_log(run,f'Этап {run.stage+1}/3: {data["enemy_names"][run.stage]}!')


def view(db:Session,r:RaidRun,me:int):
    parts=list(db.scalars(select(RaidMember).where(RaidMember.run_id==r.id).order_by(RaidMember.contribution.desc(),RaidMember.id)))
    ids=[m.player_id for m in parts]
    names={p.id:p.name for p in db.scalars(select(Player).where(Player.id.in_(ids)))}
    config=RAIDS[r.scenario]
    return {'id':r.id,'scenario':r.scenario,'name':config['name'],'status':r.status,
            'stage':r.stage+1,'stages':3,'enemy':config['enemy_names'][min(r.stage,2)],
            'hp':r.enemy_hp,'max_hp':r.enemy_max_hp,'expires_at':aware(r.expires_at).isoformat(),
            'leader_id':r.creator_id,'member_count':len(parts),'mine':me in ids,
            'log':(r.log or [])[-16:],
            'members':[{'id':m.player_id,'name':names.get(m.player_id,'Выживший'),
                        'hp':m.hp,'max_hp':m.max_hp,'contribution':m.contribution,'actions':m.actions,
                        'rewarded':m.rewarded,'next_action_at':(aware(m.last_action)+timedelta(seconds=ACTION_COOLDOWN)).isoformat() if m.last_action else None}
                       for m in parts]}


def install_raids(app, with_player, ready):
    router=APIRouter(prefix='/api/raids',tags=['Raids'])

    def session():
        with SessionLocal() as db:yield db

    @router.get('')
    def list_raids(request:Request,db:Session=Depends(session)):
        with db.begin():
            p=with_player(request,db)
            close_expired(db)
            current=current_raid(db,p.id)
            raids=list(db.scalars(select(RaidRun).where(RaidRun.status=='lobby').order_by(RaidRun.id.desc()).limit(12)))
            return {'scenarios':RAIDS,'my_raid':view(db,current,p.id) if current else None,
                    'lobbies':[view(db,r,p.id) for r in raids if r.id!=(current.id if current else -1)],
                    'recent':[view(db,r,p.id) for r in db.scalars(select(RaidRun).join(RaidMember,RaidMember.run_id==RaidRun.id)
                        .where(RaidMember.player_id==p.id,RaidRun.status.in_(['cleared','failed','expired']))
                        .order_by(RaidRun.id.desc()).limit(5))]}

    @router.post('/create')
    def create(body:ScenarioRequest,request:Request,db:Session=Depends(session)):
        with db.begin():
            p=with_player(request,db);ready(p);close_expired(db)
            config=RAIDS.get(body.key)
            if not config:raise ValueError('Рейд не найден')
            if p.level<config['level']:raise ValueError(f'Для рейда нужен уровень {config["level"]}')
            if current_raid(db,p.id):raise ValueError('Сначала заверши текущий рейд')
            raid=RaidRun(creator_id=p.id,scenario=body.key,status='lobby',stage=0,
                expires_at=now()+timedelta(seconds=LOBBY_LIFETIME),log=[f'{p.name} собирает группу.'])
            db.add(raid);db.flush()
            db.add(RaidMember(run_id=raid.id,player_id=p.id,hp=max_hp(p),max_hp=max_hp(p)))
            return {'message':f'Группа «{config["name"]}» создана. Пригласи ещё двоих!','id':raid.id}

    @router.post('/join')
    def join(body:RaidRequest,request:Request,db:Session=Depends(session)):
        with db.begin():
            p=with_player(request,db);ready(p);close_expired(db)
            r=db.scalar(select(RaidRun).where(RaidRun.id==body.id).with_for_update())
            if not r or r.status!='lobby':raise ValueError('Нельзя вступить: набор уже закрыт')
            if p.level<RAIDS[r.scenario]['level']:raise ValueError('Не хватает уровня')
            if current_raid(db,p.id):raise ValueError('Ты уже состоишь в активной группе')
            size=db.scalar(select(func.count()).select_from(RaidMember).where(RaidMember.run_id==r.id))
            if size>=MAX_PARTY:raise ValueError('Группа заполнена')
            db.add(RaidMember(run_id=r.id,player_id=p.id,hp=max_hp(p),max_hp=max_hp(p)));db.flush()
            raid_log(r,f'{p.name} вступает в группу ({size+1}/10)')
            if size+1==MIN_PARTY:
                queue_notification(db,r.creator_id,f'raid:{r.id}:ready:{r.creator_id}',
                                   'raids','raid_ready',f'Группа рейда «{RAIDS[r.scenario]["name"]}» собрана. Можно начинать!')
            return {'message':'Ты присоединился к группе'}

    @router.post('/leave')
    def leave(body:RaidRequest,request:Request,db:Session=Depends(session)):
        with db.begin():
            p=with_player(request,db)
            r=db.scalar(select(RaidRun).where(RaidRun.id==body.id).with_for_update())
            if not r or r.status!='lobby':raise ValueError('Покинуть можно только группу до старта')
            member=db.scalar(select(RaidMember).where(RaidMember.run_id==r.id,RaidMember.player_id==p.id).with_for_update())
            if not member:raise ValueError('Ты не в этом рейде')
            db.delete(member);db.flush()
            participants=list(db.scalars(select(RaidMember).where(RaidMember.run_id==r.id).order_by(RaidMember.id)))
            if not participants:r.status='failed';raid_log(r,'Группа распущена.')
            elif r.creator_id==p.id:
                r.creator_id=participants[0].player_id
                if len(participants)>=MIN_PARTY:
                    queue_notification(db,r.creator_id,f'raid:{r.id}:ready:{r.creator_id}',
                                       'raids','raid_ready',f'Ты возглавляешь рейд «{RAIDS[r.scenario]["name"]}». Группа готова к старту.')
            return {'message':'Ты вышел из рейда'}

    @router.post('/launch')
    def launch(body:RaidRequest,request:Request,db:Session=Depends(session)):
        with db.begin():
            p=with_player(request,db);ready(p)
            r=db.scalar(select(RaidRun).where(RaidRun.id==body.id).with_for_update())
            if not r or r.status!='lobby':raise ValueError('Рейд уже запущен или закрыт')
            if r.creator_id!=p.id:raise ValueError('Запуск доступен только лидеру рейда')
            members=list(db.scalars(select(RaidMember).where(RaidMember.run_id==r.id).with_for_update()))
            if len(members)<MIN_PARTY:raise ValueError('Для старта нужно минимум три участника')
            if len(members)>MAX_PARTY:raise ValueError('Слишком большая группа')
            r.status='active';r.stage=0;r.started_at=now()
            r.expires_at=now()+timedelta(hours=RAIDS[r.scenario]['duration_hours'])
            start_stage(r,len(members))
            for member in members:
                queue_notification(db,member.player_id,f'raid:{r.id}:started:{member.player_id}',
                                   'raids','raid_started',f'Рейд «{RAIDS[r.scenario]["name"]}» начался. Вступай в бой!')
                queue_notification(db,member.player_id,f'raid:{r.id}:deadline:{member.player_id}',
                                   'raids','raid_deadline',f'Время рейда «{RAIDS[r.scenario]["name"]}» истекло.',r.expires_at)
            return {'message':'Экспедиция началась. Пройдите три этапа!'}

    @router.post('/act')
    def act(body:RaidActionRequest,request:Request,db:Session=Depends(session)):
        with db.begin():
            p=with_player(request,db);ready(p)
            r=db.scalar(select(RaidRun).where(RaidRun.id==body.id).with_for_update())
            if not r or r.status!='active':raise ValueError('Рейд неактивен')
            fighter=db.scalar(select(RaidMember).where(RaidMember.run_id==r.id,RaidMember.player_id==p.id).with_for_update())
            if not fighter:raise ValueError('Ты не состоишь в этом рейде')
            if aware(r.expires_at)<=now():
                # Raising here rolled the status change back with the transaction.
                r.status='expired'
                raid_log(r,'Время истекло. Экспедиция не вернулась.')
                for member_id in db.scalars(select(RaidMember.player_id).where(RaidMember.run_id==r.id)):
                    queue_notification(db,member_id,f'raid:{r.id}:deadline:{member_id}',
                                       'raids','raid_deadline',f'Время рейда «{RAIDS[r.scenario]["name"]}» истекло.')
                return {'message':'Время рейда вышло', 'raid':view(db,r,p.id)}
            if fighter.hp<=0:raise ValueError('Персонаж выбит. Нужна помощь врача')
            if fighter.last_action and (now()-aware(fighter.last_action)).total_seconds()<ACTION_COOLDOWN:
                raise ValueError('Способность восстанавливается. Подожди несколько секунд')
            cost={'attack':6,'guard':3,'medkit':3,'rescue':5}[body.action]
            spend_stamina(p,cost)
            party=list(db.scalars(select(RaidMember).where(RaidMember.run_id==r.id).with_for_update()))
            config=RAIDS[r.scenario]
            dealt=0
            if body.action=='attack':
                ammo_status=spend_legendary_round(db,p.id)
                dealt=max(1,int(attack_power(db,p,ammo_status=ammo_status)*random.uniform(.85,1.2)*(1+.05*r.stage)))
                r.enemy_hp=max(0,r.enemy_hp-dealt)
                from gear import wear_equipped
                wear_equipped(db,p.id,'weapon',1)
                fighter.contribution+=dealt
                raid_log(r,f'⚔ {p.name}: {dealt} урона. Осталось {r.enemy_hp} HP у босса.'+ammo_message(ammo_status))
            elif body.action=='guard':
                fighter.contribution+=3
                raid_log(r,f'🛡 {p.name} удерживает оборону и снижает встречный удар.')
            elif body.action=='medkit':
                if item_count(db,p.id,'medkit')<1:raise ValueError('Нет аптечки')
                take_item(db,p.id,'medkit')
                heal=min(fighter.max_hp-fighter.hp,45)
                if heal<=0:raise ValueError('Здоровье уже полностью восстановлено')
                fighter.hp+=heal;fighter.contribution+=heal//2
                raid_log(r,f'✚ {p.name} лечится: +{heal} HP.')
            else:
                if p.hero_class!='medic':raise ValueError('Поднять товарища может только врач')
                teammate=next((m for m in party if m.player_id==body.target_id),None)
                if not teammate or teammate.id==fighter.id or teammate.hp>0:
                    raise ValueError('Выбери павшего товарища')
                if item_count(db,p.id,'medkit')<1:raise ValueError('Нужна аптечка для реанимации')
                take_item(db,p.id,'medkit');teammate.hp=max(1,teammate.max_hp//3)
                fighter.contribution+=20
                raid_log(r,f'✚ {p.name} возвращает товарища {teammate.player_id} в бой!')
            fighter.actions+=1;fighter.last_action=now()
            if r.enemy_hp<=0:
                if r.stage>=2:
                    r.status='cleared'
                    raid_log(r,'🏆 Рейд пройден! Заберите награды из штаба экспедиции.')
                else:
                    r.stage+=1;start_stage(r,len(party))
            else:
                damage=max(1,round(config['damage']*(1+.55*r.stage)*random.uniform(.75,1.2)))
                if body.action=='guard':damage=max(1,damage//4)
                # Equipped armor contributes real damage reduction inside raids.
                from gear import gear_stats
                damage=max(1,damage-min(gear_stats(db,p.id)['defense'],int(damage*.65)))
                fighter.hp=max(0,fighter.hp-damage)
                from gear import wear_equipped
                wear_equipped(db,p.id,'armor',1)
                if fighter.hp==0:raid_log(r,f'☠ {p.name} выбыл из боя!')
                if not any(m.hp>0 for m in party):r.status='failed';raid_log(r,'Группа уничтожена. Экспедиция провалена.')
            if r.status in ('cleared','failed'):
                for member in party:
                    if r.status=='cleared' and member.actions<1:
                        continue
                    message=(f'Рейд «{config["name"]}» пройден! Забери награду.' if r.status=='cleared'
                             else f'Рейд «{config["name"]}» провален. Группа выбыла из боя.')
                    queue_notification(db,member.player_id,f'raid:{r.id}:{r.status}:{member.player_id}',
                                       'raids',f'raid_{r.status}',message)
            return {'message':'Рейд завершён!' if r.status=='cleared' else f'Действие выполнено: {dealt} урона' if dealt else 'Действие выполнено','raid':view(db,r,p.id)}

    @router.post('/claim')
    def claim(body:RaidRequest,request:Request,db:Session=Depends(session)):
        with db.begin():
            p=with_player(request,db)
            r=db.scalar(select(RaidRun).where(RaidRun.id==body.id).with_for_update())
            if not r or r.status!='cleared':raise ValueError('Награды доступны после победы')
            member=db.scalar(select(RaidMember).where(RaidMember.run_id==r.id,RaidMember.player_id==p.id).with_for_update())
            if not member:raise ValueError('Ты не участвовал в рейде')
            if member.rewarded:raise ValueError('Эта награда уже получена')
            if member.actions<1:raise ValueError('Чтобы получить награду, внеси вклад в рейд')
            data=RAIDS[r.scenario]
            xp=data['xp']+min(300,member.contribution//4)
            caps=data['caps']+min(160,member.contribution//8)
            gain_xp(p,xp);p.caps+=caps
            give_item(db,p.id,'metal',1+r.stage)
            if r.scenario!='outpost':give_item(db,p.id,'rare',1)
            else:give_item(db,p.id,'food',2)
            # Optional guaranteed high-tier loot for advanced cooperative clears.
            from gear import roll_drop, gear_view
            drop=None
            if r.scenario!='outpost' or random.random()<.60:
                min_rarity={'outpost':'uncommon','vault':'rare','citadel':'epic'}[r.scenario]
                threat={'outpost':2,'vault':4,'citadel':5}[r.scenario]
                try:drop=gear_view(roll_drop(db,p.id,threat,minimum=min_rarity))
                except ValueError:pass  # Locker cap must not block currency/XP rewards.
            # Battle cases are earned from cleared raids; no Stars payments.
            case_key=raid_case_drop(r.scenario,random)
            if case_key:give_item(db,p.id,case_key)
            member.rewarded=True
            return {'message':f'Награда: {xp} XP, {caps} крышек и редкие припасы!'+(' · '+drop['rarity_name']+' '+drop['name'] if drop else ''), 'xp':xp,'caps':caps,'gear_drop':drop,'case_drop':case_key}

    app.include_router(router)
