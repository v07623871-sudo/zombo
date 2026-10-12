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
from notifications import queue_notification

TASKS = {
    'kills': {'name':'Очищение кварталов', 'icon':'☣', 'desc':'Уничтожайте заражённых в обычных вылазках.',
              'target':25, 'minimum':3, 'treasury':250, 'renown':120, 'personal_caps':35, 'personal_xp':55},
    'scavenge': {'name':'Обеспечение убежища', 'icon':'▣', 'desc':'Добывайте ресурсы в пустоши и после побед.',
                 'target':35, 'minimum':4, 'treasury':300, 'renown':150, 'personal_caps':45, 'personal_xp':65},
    'boss': {'name':'Последний рубеж', 'icon':'⚔', 'desc':'Атакуйте мирового босса сообща.',
              'target':12, 'minimum':2, 'treasury':420, 'renown':210, 'personal_caps':65, 'personal_xp':85},
}
MAX_CLAN_LEVEL = 30
SEASON_MIN_CONTRIBUTION = 10
SEASON_PRIZES = {1: (120, 180), 2: (80, 120), 3: (50, 80)}

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

class ClanSeasonContribution(Base):
    __tablename__ = 'clan_season_contributions'
    season = Column(String(7), primary_key=True)
    clan_id = Column(Integer, primary_key=True)
    player_id = Column(BigInteger, primary_key=True)
    amount = Column(Integer, nullable=False, default=0)

class ClanSeasonSettlement(Base):
    __tablename__ = 'clan_season_settlements'
    season = Column(String(7), primary_key=True)
    settled_at = Column(DateTime(timezone=True), nullable=True)

class ClanSeasonResult(Base):
    __tablename__ = 'clan_season_results'
    season = Column(String(7), primary_key=True)
    clan_id = Column(Integer, primary_key=True)
    place = Column(Integer, nullable=False)
    clan_name = Column(String(55), nullable=False)
    points = Column(Integer, nullable=False)
    completed = Column(Integer, nullable=False)

class ClanSeasonRewardClaim(Base):
    __tablename__ = 'clan_season_reward_claims'
    season = Column(String(7), primary_key=True)
    player_id = Column(BigInteger, primary_key=True)
    clan_id = Column(Integer, nullable=False)
    place = Column(Integer, nullable=False)
    caps = Column(Integer, nullable=False)
    xp = Column(Integer, nullable=False)
    claimed_at = Column(DateTime(timezone=True), nullable=False)


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


def previous_season(at:datetime|None=None)->str:
    current=(at or now()).astimezone(timezone.utc).replace(day=1)
    return (current-timedelta(days=1)).strftime('%Y-%m')


def season_end(season:str)->datetime:
    first=datetime.strptime(season,'%Y-%m').replace(tzinfo=timezone.utc)
    return (first.replace(day=28)+timedelta(days=4)).replace(day=1)


def settle_seasons(db:Session,at:datetime|None=None):
    """Snapshot completed months after a one-hour grace period, once across workers."""
    instant=at or now()
    current=season_key(instant)
    seasons=db.scalars(select(ClanSeasonScore.season).outerjoin(
        ClanSeasonSettlement,ClanSeasonSettlement.season==ClanSeasonScore.season).where(
        ClanSeasonScore.season<current,ClanSeasonSettlement.settled_at.is_(None))
        .distinct().order_by(ClanSeasonScore.season)).all()
    for season in seasons:
        if season_end(season)+timedelta(hours=1)>instant:
            continue
        db.execute(text('''INSERT INTO clan_season_settlements (season)
            VALUES (:season) ON CONFLICT (season) DO NOTHING'''),{'season':season})
        settlement=db.scalar(select(ClanSeasonSettlement).where(
            ClanSeasonSettlement.season==season).with_for_update())
        if settlement.settled_at:
            continue
        scores=db.execute(select(ClanSeasonScore,Clan.name).join(
            Clan,Clan.id==ClanSeasonScore.clan_id).where(
            ClanSeasonScore.season==season).order_by(
            ClanSeasonScore.points.desc(),ClanSeasonScore.completed.desc(),
            ClanSeasonScore.clan_id).limit(10)).all()
        for place,(score,name) in enumerate(scores,1):
            db.add(ClanSeasonResult(season=season,clan_id=score.clan_id,
                place=place,clan_name=name,points=score.points,completed=score.completed))
        settlement.settled_at=instant
        db.flush()


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
    useful=min(qty,max(0,task['target']-mission.amount))
    if useful:
        db.execute(text('''INSERT INTO clan_season_contributions
            (season,clan_id,player_id,amount) VALUES (:season,:clan,:pid,:qty)
            ON CONFLICT (season,clan_id,player_id) DO UPDATE SET
            amount = clan_season_contributions.amount + EXCLUDED.amount'''),
            {'season':season_key(today),'clan':c.id,'pid':player_id,'qty':useful})
        queue_notification(db,player_id,f'clan:{c.id}:week:{week}:reset:{player_id}',
            'clans','weekly_reset','Новые клановые поручения доступны. Проверь цели недели.',
            datetime.fromisoformat(next_week(today)))
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
    settle_seasons(db,today)
    rows=db.execute(select(ClanSeasonScore,Clan.name).join(Clan,Clan.id==ClanSeasonScore.clan_id)
        .where(ClanSeasonScore.season==season).order_by(ClanSeasonScore.points.desc(),ClanSeasonScore.completed.desc(),ClanSeasonScore.clan_id)
        .limit(15)).all()
    ranking=[{'clan_id':score.clan_id,'name':name,'points':score.points,'completed':score.completed} for score,name in rows]
    previous=previous_season(today)
    history=db.scalars(select(ClanSeasonResult).where(
        ClanSeasonResult.season<=previous,ClanSeasonResult.place<=3).order_by(
        ClanSeasonResult.season.desc(),ClanSeasonResult.place).limit(9)).all()
    results=[{'season':r.season,'place':r.place,'clan_id':r.clan_id,
              'name':r.clan_name,'points':r.points,'completed':r.completed} for r in history]
    base={'week':week,'season':season,'season_ends_at':season_end(season).isoformat(),
          'ends_at':next_week(today),'ranking':ranking,'season_history':results}
    if not p.clan_id:return {'clan_id':None,'missions':[],'season_reward':None,**base}
    c=db.get(Clan,p.clan_id)
    if not c:return {'clan_id':None,'missions':[],'season_reward':None,**base}
    miss={x.code:x for x in db.scalars(select(ClanMission).where(ClanMission.clan_id==c.id,ClanMission.week==week))}
    own={x.code:x for x in db.scalars(select(ClanMissionMember).where(ClanMissionMember.clan_id==c.id,ClanMissionMember.week==week,ClanMissionMember.player_id==p.id))}
    renown=db.get(ClanRenown,c.id)
    season_stats=db.get(ClanSeasonScore,(c.id,season))
    result=db.get(ClanSeasonResult,(previous,c.id))
    contribution=db.get(ClanSeasonContribution,(previous,c.id,p.id))
    claimed=db.get(ClanSeasonRewardClaim,(previous,p.id))
    prize=SEASON_PRIZES.get(result.place) if result else None
    reward={'season':previous,'place':result.place,'contribution':contribution.amount if contribution else 0,
            'minimum':SEASON_MIN_CONTRIBUTION,'caps':prize[0],'xp':prize[1],
            'claimed':bool(claimed),
            'can_claim':bool(prize and contribution and contribution.amount>=SEASON_MIN_CONTRIBUTION and not claimed)} if prize else None
    return {'clan_id':c.id,'clan_name':c.name,'clan_level':c.level,'renown':renown.xp if renown else 0,
            'season_points':season_stats.points if season_stats else 0,
            'season_reward':reward,**base,
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


def claim_season_reward(db:Session,p:Player,at:datetime|None=None):
    instant=at or now()
    if instant<season_end(previous_season(instant))+timedelta(hours=1):
        raise ValueError('Итоги прошлого сезона появятся после 01:00 UTC')
    settle_seasons(db,instant)
    season=previous_season(instant)
    if not p.clan_id:
        raise ValueError('Для сезонной награды нужно состоять в клане-победителе')
    result=db.get(ClanSeasonResult,(season,p.clan_id))
    prize=SEASON_PRIZES.get(result.place) if result else None
    if not prize:
        raise ValueError('Клан не вошёл в призовую тройку прошлого сезона')
    contribution=db.get(ClanSeasonContribution,(season,p.clan_id,p.id))
    if not contribution or contribution.amount<SEASON_MIN_CONTRIBUTION:
        raise ValueError('Недостаточный личный вклад в прошлом сезоне')
    if db.get(ClanSeasonRewardClaim,(season,p.id)):
        raise ValueError('Сезонная награда уже получена')
    from game import gain_xp
    db.add(ClanSeasonRewardClaim(season=season,player_id=p.id,clan_id=p.clan_id,
        place=result.place,caps=prize[0],xp=prize[1],claimed_at=instant))
    p.caps+=prize[0]
    gain_xp(p,prize[1])
    db.flush()
    return {'message':f'Награда за {result.place}-е место сезона {season}: {prize[0]} крышек и {prize[1]} XP!',
            'caps':prize[0],'xp':prize[1],'season':season,'place':result.place}


class ClanMissionClaim(BaseModel):
    code: str = Field(min_length=1, max_length=20)


def install_clan_missions(app,with_player,ready):
    router=APIRouter(prefix='/api/clan-missions',tags=['Clan missions'])
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
    def claim(body:ClanMissionClaim,request:Request,db:Session=Depends(session)):
        with db.begin():
            p=with_player(request,db);ready(p)
            return claim_clan_reward(db,p,body.code)

    @router.post('/season-claim')
    def season_claim(request:Request,db:Session=Depends(session)):
        with db.begin():
            p=with_player(request,db);ready(p)
            return claim_season_reward(db,p)

    app.include_router(router)
