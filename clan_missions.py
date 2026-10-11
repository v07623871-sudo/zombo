"""Durable weekly clan objectives and monthly rankings for ZOMBO.

Installed via install_clan_missions(app, with_player). No existing DB tables change.
The game.progress() hook is the sole event source. Rewards are server-only and
idempotent under concurrent requests; all writes participate in the caller's transaction.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Request, Depends
from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func, select, text
from sqlalchemy.orm import Session
from models import Base, Clan, Player, SessionLocal, now

TASKS = {
    'kills': {'name':'Очищение кварталов', 'icon':'☣', 'desc':'Уничтожайте заражённых в обычных вылазках.',
              'target':25, 'minimum':3, 'treasury':250, 'renown':120, 'personal_caps':35, 'personal_xp':55},
    'scavenge': {'name':'Обеспечение убежища', 'icon':'▣', 'desc':'Добывайте ресурсы в пустоши и после побед.',
                 'target':35, 'minimum':4, 'treasury':300, 'renown':150, 'personal_caps':45, 'personal_xp':65},
    'boss': {'name':'Последний рубеж', 'icon':'⚔', 'desc':'Атакуйте мирового босса сообща.',
              'target':12, 'minimum':2, 'treasury':420, 'renown':210, 'personal_caps':65, 'personal_xp':85},
}
MAX_CLAN_LEVEL = 30

class ClanMission(Base):
    __tablename__ = 'clan_missions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    clan_id = Column(Integer, nullable=False, index=True)
    week = Column(String(10), nullable=False)
    code = Column(String(20), nullable=False)
    amount = Column(Integer, nullable=False, default=0)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint('clan_id','week','code',name='uq_clan_mission_period'),)

class ClanMissionMember(Base):
    __tablename__ = 'clan_mission_members'
    id = Column(Integer, primary_key=True, autoincrement=True)
    clan_id = Column(Integer, nullable=False, index=True)
    week = Column(String(10), nullable=False)
    code = Column(String(20), nullable=False)
    player_id = Column(BigInteger, nullable=False, index=True)
    amount = Column(Integer, nullable=False, default=0)
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint('clan_id','week','code','player_id',name='uq_clan_mission_member'),)

class ClanRenown(Base):
    __tablename__ = 'clan_renown'
    clan_id = Column(Integer, primary_key=True)
    xp = Column(Integer, nullable=False, default=0)
    missions_completed = Column(Integer, nullable=False, default=0)

class ClanSeasonScore(Base):
    __tablename__ = 'clan_seasons'
    clan_id = Column(Integer, primary_key=True)
    season = Column(String(7), primary_key=True)
    points = Column(Integer, nullable=False, default=0)
    completed = Column(Integer, nullable=False, default=0)


def week_key(at:datetime|None=None)->str:
    at = (at or now()).astimezone(timezone.utc)
    year, week, _ = at.isocalendar()
    return f'{year}-W{week:02d}'


def season_key(at:datetime|None=None)->str:
    return (at or now()).astimezone(timezone.utc).strftime('%Y-%m')


def next_week(at:datetime|None=None)->str:
    at=(at or now()).astimezone(timezone.utc)
    monday=at.replace(hour=0,minute=0,second=0,microsecond=0)-timedelta(days=at.weekday())
    return (monday+timedelta(days=7)).isoformat()


def get_or_create(db:Session,clan_id:int,week:str,code:str)->ClanMission:
    db.execute(text('''INSERT INTO clan_missions (clan_id,week,code,amount)
        VALUES (:clan,:week,:code,0) ON CONFLICT (clan_id,week,code) DO NOTHING'''),
        {'clan':clan_id,'week':week,'code':code})
    return db.scalar(select(ClanMission).where(ClanMission.clan_id==clan_id,
        ClanMission.week==week,ClanMission.code==code).with_for_update())


def record_clan_progress(db:Session,player_id:int,code:str,qty:int=1,at:datetime|None=None):
    """Called on genuine PvE actions, including from other code paths.

    DB transaction and player row lock come from the original game operation.
    Mission row lock serializes completion and guarantees one treasury payout.
    """
    if code not in TASKS or not isinstance(qty,int) or qty<=0:
        return
    p=db.get(Player,player_id)
    if not p or not p.clan_id or not p.hero_class:
        return
    c=db.get(Clan,p.clan_id)
    if not c:return
    today=at or now()
    week=week_key(today)
    task=TASKS[code]
    mission=get_or_create(db,c.id,week,code)
    # Contribution remains available even after the collective target is met.
    db.execute(text('''INSERT INTO clan_mission_members (clan_id,week,code,player_id,amount)
        VALUES (:clan,:week,:code,:pid,:qty)
        ON CONFLICT (clan_id,week,code,player_id) DO UPDATE SET
        amount = clan_mission_members.amount + EXCLUDED.amount'''),
        {'clan':c.id,'week':week,'code':code,'pid':player_id,'qty':qty})
    if mission.completed_at:
        return
    mission.amount=min(task['target'],mission.amount+qty)
    if mission.amount<task['target']:
        return
    mission.completed_at=today
    # Lock clan row for money operations; all three updates share one transaction.
    c=db.scalar(select(Clan).where(Clan.id==c.id).with_for_update())
    c.treasury+=task['treasury']
    db.execute(text('''INSERT INTO clan_renown (clan_id,xp,missions_completed)
       VALUES (:id,:xp,1) ON CONFLICT (clan_id) DO UPDATE SET
       xp = clan_renown.xp + EXCLUDED.xp,
       missions_completed = clan_renown.missions_completed + 1'''),
       {'id':c.id,'xp':task['renown']})
    db.execute(text('''INSERT INTO clan_seasons (clan_id,season,points,completed)
       VALUES (:id,:season,:score,1) ON CONFLICT (clan_id,season) DO UPDATE SET
       points = clan_seasons.points + EXCLUDED.points,
       completed = clan_seasons.completed + 1'''),
       {'id':c.id,'season':season_key(today),'score':task['renown']})
    # Persistent clan level is monotonically increasing; it never resets monthly.
    db.flush()
    xp=db.scalar(select(ClanRenown.xp).where(ClanRenown.clan_id==c.id)) or 0
    c.level=max(c.level or 1,min(MAX_CLAN_LEVEL,1+xp//350))


def board(db:Session,p:Player,at:datetime|None=None):
    today=at or now();season=season_key(today);week=week_key(today)
    rows=db.execute(select(ClanSeasonScore,Clan.name).join(Clan,Clan.id==ClanSeasonScore.clan_id)
        .where(ClanSeasonScore.season==season).order_by(ClanSeasonScore.points.desc(),ClanSeasonScore.completed.desc(),ClanSeasonScore.clan_id)
        .limit(15)).all()
    ranking=[{'clan_id':score.clan_id,'name':name,'points':score.points,'completed':score.completed} for score,name in rows]
    if not p.clan_id:return {'clan_id':None,'week':week,'season':season,'ends_at':next_week(today),'missions':[],'ranking':ranking}
    c=db.get(Clan,p.clan_id)
    if not c:return {'clan_id':None,'week':week,'season':season,'ends_at':next_week(today),'missions':[],'ranking':ranking}
    miss={x.code:x for x in db.scalars(select(ClanMission).where(ClanMission.clan_id==c.id,ClanMission.week==week))}
    own={x.code:x for x in db.scalars(select(ClanMissionMember).where(ClanMissionMember.clan_id==c.id,ClanMissionMember.week==week,ClanMissionMember.player_id==p.id))}
    renown=db.get(ClanRenown,c.id)
    season_stats=db.get(ClanSeasonScore,(c.id,season))
    return {'clan_id':c.id,'clan_name':c.name,'clan_level':c.level,'renown':renown.xp if renown else 0,
            'season_points':season_stats.points if season_stats else 0,'week':week,'season':season,'ends_at':next_week(today),'ranking':ranking,
            'missions':[{'code':code,**task,'progress':miss[code].amount if code in miss else 0,
              'completed':bool(code in miss and miss[code].completed_at),
              'mine':own[code].amount if code in own else 0,
              'claimed':bool(code in own and own[code].claimed_at),
              'can_claim':bool(code in miss and miss[code].completed_at and code in own and own[code].amount>=task['minimum'] and not own[code].claimed_at)}
              for code,task in TASKS.items()]}


def claim_clan_reward(db:Session,p:Player,code:str,at:datetime|None=None):
    if code not in TASKS:raise ValueError('Неизвестное задание клана')
    if not p.clan_id:raise ValueError('Сначала вступи в клан')
    week=week_key(at)
    miss=db.scalar(select(ClanMission).where(ClanMission.clan_id==p.clan_id,
        ClanMission.week==week,ClanMission.code==code))
    if not miss or not miss.completed_at:raise ValueError('Клан ещё не выполнил задание')
    member=db.scalar(select(ClanMissionMember).where(ClanMissionMember.clan_id==p.clan_id,
        ClanMissionMember.week==week,ClanMissionMember.code==code,ClanMissionMember.player_id==p.id).with_for_update())
    if not member or member.amount<TASKS[code]['minimum']:
        raise ValueError('Недостаточный личный вклад для награды')
    if member.claimed_at:raise ValueError('Награда уже получена')
    from game import gain_xp
    reward=TASKS[code]
    member.claimed_at=at or now()
    p.caps+=reward['personal_caps']
    gain_xp(p,reward['personal_xp'])
    return {'message':f'Награда за «{reward["name"]}»: {reward["personal_caps"]} крышек и {reward["personal_xp"]} XP!',
            'caps':reward['personal_caps'],'xp':reward['personal_xp']}


def install_clan_missions(app,with_player,ready):
    router=APIRouter(prefix='/api/clan-missions',tags=['Clan missions'])
    class Claim(BaseModel):
        code:str=Field(min_length=1,max_length=20)
    def session():
        db=SessionLocal()
        try:yield db
        finally:db.close()

    @router.get('')
    def get(request:Request,db:Session=Depends(session)):
        with db.begin():
            p=with_player(request,db)
            return board(db,p)

    @router.post('/claim')
    def claim(body:Claim,request:Request,db:Session=Depends(session)):
        with db.begin():
            p=with_player(request,db);ready(p)
            return claim_clan_reward(db,p,body.code)

    app.include_router(router)