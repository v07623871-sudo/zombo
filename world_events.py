"""Scheduled world events with transactional gameplay effects and one-time rewards.

Every game action mutates event progress in the same transaction as loot/combat.
Administrators schedule bounded events; no in-memory timers or auto-generated loot.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func, select, text
from sqlalchemy.orm import Session

from models import Base, Player, SessionLocal, now

EVENT_TYPES = {
    'horde': {'name': 'Орда заражённых', 'description': 'Зачищай территорию. Каждая победа над заражённым даёт +20% XP и крышек.', 'goal': 25, 'action': 'kills', 'bonus_caps': 90, 'bonus_xp': 130},
    'supplies': {'name': 'Военный груз', 'description': 'Обыскивай локацию. Каждая вылазка приносит +1 единицу найденного ресурса.', 'goal': 35, 'action': 'scavenge', 'bonus_caps': 70, 'bonus_xp': 100},
}
MAX_EVENT_LENGTH_HOURS = 24


class WorldEvent(Base):
    __tablename__ = 'world_events'
    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(20), nullable=False)
    location = Column(String(30), nullable=False)
    starts_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ends_at = Column(DateTime(timezone=True), nullable=False, index=True)
    stopped_at = Column(DateTime(timezone=True))
    created_by = Column(BigInteger, nullable=False)
    total_progress = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)


class WorldEventParticipation(Base):
    __tablename__ = 'world_event_participants'
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey('world_events.id'), nullable=False, index=True)
    player_id = Column(BigInteger, ForeignKey('players.id'), nullable=False, index=True)
    actions = Column(Integer, nullable=False, default=0)
    claimed = Column(Boolean, nullable=False, default=False)
    __table_args__ = (UniqueConstraint('event_id', 'player_id', name='unique_world_event_player'),)


def aware(dt: datetime | None):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def event_status(event: WorldEvent, instant: datetime | None = None):
    instant = instant or now()
    if event.stopped_at:
        return 'stopped'
    if aware(event.starts_at) > instant:
        return 'scheduled'
    if aware(event.ends_at) > instant:
        return 'active'
    return 'finished'


def active_event(db: Session, location: str, type: str | None = None):
    instant = now()
    query = select(WorldEvent).where(
        WorldEvent.location == location,
        WorldEvent.starts_at <= instant, WorldEvent.ends_at > instant,
        WorldEvent.stopped_at.is_(None))
    if type:
        query = query.where(WorldEvent.type == type)
    return db.scalar(query.order_by(WorldEvent.id.desc()).limit(1))


def record_action(db: Session, player: Player, type: str):
    """Lock event row first; prevent duplicate one-time claims at event closure."""
    if type not in EVENT_TYPES:
        raise ValueError('Неизвестное событие')
    found = active_event(db, player.location, type)
    if not found:
        return None
    event = db.scalar(select(WorldEvent).where(WorldEvent.id == found.id).with_for_update())
    if not event or event_status(event) != 'active':
        return None
    participation = db.scalar(select(WorldEventParticipation).where(
        WorldEventParticipation.event_id == event.id,
        WorldEventParticipation.player_id == player.id).with_for_update())
    if not participation:
        participation = WorldEventParticipation(event_id=event.id, player_id=player.id,
                                                   actions=0, claimed=False)
        db.add(participation)
        # SessionLocal disables autoflush. Persist the unique membership before
        # another event action in the same transaction can query it.
        db.flush()
    participation.actions += 1
    event.total_progress += 1
    return event


def event_view(db: Session, event: WorldEvent, pid: int | None):
    config = EVENT_TYPES[event.type]
    part = db.scalar(select(WorldEventParticipation).where(
        WorldEventParticipation.event_id == event.id,
        WorldEventParticipation.player_id == pid)) if pid else None
    state = event_status(event)
    qualified = bool(part and part.actions > 0 and event.total_progress >= config['goal']
                     and state in ('finished', 'stopped'))
    return {'id': event.id, 'type': event.type, 'name': config['name'],
            'description': config['description'], 'location': event.location,
            'starts_at': aware(event.starts_at).isoformat(),
            'ends_at': aware(event.ends_at).isoformat(),
            'status': state, 'goal': config['goal'],
            'progress': min(event.total_progress, config['goal']),
            'total_progress': event.total_progress,
            'my_actions': part.actions if part else 0,
            'reward': {'caps': config['bonus_caps'], 'xp': config['bonus_xp']},
            'can_claim': qualified and not part.claimed,
            'claimed': bool(part and part.claimed)}


class ClaimEvent(BaseModel):
    id: int = Field(gt=0)


class CreateEvent(BaseModel):
    type: str = Field(pattern=r'^(horde|supplies)$')
    location: str = Field(min_length=1, max_length=30)
    starts_in_minutes: int = Field(ge=0, le=10080)
    duration_minutes: int = Field(ge=30, le=1440)
    reason: str = Field(min_length=5, max_length=300)
    request_id: UUID


class StopEvent(BaseModel):
    reason: str = Field(min_length=5, max_length=300)
    request_id: UUID


def install_world_events(app, with_player, identify, admin_ids):
    router = APIRouter(prefix='/api/world-events', tags=['World Events'])
    admin = APIRouter(prefix='/api/admin/world-events', tags=['World Events Admin'])

    def session():
        with SessionLocal() as db:
            yield db

    def require_admin(request: Request, db: Session):
        pid = int(identify(request.headers.get('authorization', ''))['id'])
        if pid not in admin_ids:
            raise HTTPException(403, 'Только администратор')
        user = db.get(Player, pid)
        if not user or user.banned or user.frozen:
            raise HTTPException(403, 'Администратор недоступен')
        return user

    @router.get('')
    def overview(request: Request, db: Session = Depends(session)):
        with db.begin():
            p = with_player(request, db)
            instant = now()
            events = db.scalars(select(WorldEvent).where(
                WorldEvent.starts_at <= instant + timedelta(days=7),
                WorldEvent.ends_at >= instant - timedelta(days=7))
                .order_by(WorldEvent.id.desc()).limit(40)).all()
            # Keep recently ended events and scheduled events, bounded by 40 rows.
            return {'types': EVENT_TYPES,
                    'events': [event_view(db, e, p.id) for e in events]}

    @router.post('/claim')
    def claim(body: ClaimEvent, request: Request, db: Session = Depends(session)):
        from game import gain_xp
        with db.begin():
            p = with_player(request, db)
            event = db.scalar(select(WorldEvent).where(WorldEvent.id == body.id).with_for_update())
            if not event:
                raise ValueError('Событие не найдено')
            if event_status(event) not in ('finished', 'stopped'):
                raise ValueError('Событие ещё идёт')
            reward = EVENT_TYPES[event.type]
            if event.total_progress < reward['goal']:
                raise ValueError('Общая цель события не достигнута')
            part = db.scalar(select(WorldEventParticipation).where(
                WorldEventParticipation.event_id == event.id,
                WorldEventParticipation.player_id == p.id).with_for_update())
            if not part or part.actions < 1 or part.claimed:
                raise ValueError('Нет доступной награды или она уже получена')
            if p.caps + reward['bonus_caps'] > 2_000_000_000:
                raise ValueError('Достигнут лимит крышек')
            part.claimed = True
            p.caps += reward['bonus_caps']
            gain_xp(p, reward['bonus_xp'])
            return {'message': f'Награда события: +{reward["bonus_caps"]} крышек и +{reward["bonus_xp"]} XP'}

    @admin.get('')
    def admin_events(request: Request, db: Session = Depends(session)):
        require_admin(request, db)
        events = db.scalars(select(WorldEvent).order_by(WorldEvent.id.desc()).limit(30)).all()
        return {'events': [event_view(db, e, None) for e in events]}

    @admin.post('/create')
    def create(body: CreateEvent, request: Request, db: Session = Depends(session)):
        from admin import AdminAudit
        from game import LOCATIONS
        with db.begin():
            user = require_admin(request, db)
            if body.location not in LOCATIONS or body.location == 'base':
                raise ValueError('Укажи игровую локацию, отличную от убежища')
            existing = db.scalar(select(AdminAudit).where(AdminAudit.request_id == str(body.request_id)))
            if existing:
                return {'message': 'Событие уже создано', 'replayed': True}
            # Serialize creation across all admins (SQLite writer / PostgreSQL advisory lock).
            if db.bind.dialect.name == 'postgresql':
                db.execute(text('SELECT pg_advisory_xact_lock(14015015)'))
            instant = now()
            start = instant + timedelta(minutes=body.starts_in_minutes)
            end = start + timedelta(minutes=body.duration_minutes)
            overlap = db.scalar(select(WorldEvent.id).where(
                WorldEvent.location == body.location,
                WorldEvent.stopped_at.is_(None),
                WorldEvent.starts_at < end,
                WorldEvent.ends_at > start).limit(1))
            if overlap:
                raise ValueError('В этой локации уже запланировано пересекающееся событие')
            event = WorldEvent(type=body.type, location=body.location,
                               starts_at=start, ends_at=end, created_by=user.id)
            db.add(event)
            db.flush()
            db.add(AdminAudit(request_id=str(body.request_id), actor_id=user.id,
                              target_id=user.id, action='world_event', field='create',
                              before='none', after=str(event.id), reason=body.reason.strip()))
            return {'message': 'Глобальное событие запланировано', 'id': event.id}

    @admin.post('/{eid}/stop')
    def stop(eid: int, body: StopEvent, request: Request, db: Session = Depends(session)):
        from admin import AdminAudit
        with db.begin():
            user = require_admin(request, db)
            existing = db.scalar(select(AdminAudit).where(AdminAudit.request_id == str(body.request_id)))
            if existing:
                return {'message': 'Операция уже выполнена', 'replayed': True}
            event = db.scalar(select(WorldEvent).where(WorldEvent.id == eid).with_for_update())
            if not event or event_status(event) not in ('scheduled', 'active'):
                raise ValueError('Событие уже завершилось или не существует')
            before = event_status(event)
            event.stopped_at = now()
            db.add(AdminAudit(request_id=str(body.request_id), actor_id=user.id,
                              target_id=user.id, action='world_event', field='stop',
                              before=before, after=f'stopped:{event.id}', reason=body.reason.strip()))
            return {'message': 'Событие остановлено', 'id': event.id}

    app.include_router(router)
    app.include_router(admin)
