"""Opt-in, transactional Telegram outbox.

Enqueue in the same transaction as the game event. Delivery is performed only
after commit by a separate scheduler pass, so Telegram outages cannot roll
back purchases or rewards. SQL leases work across multiple Railway workers.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import (BigInteger, Boolean, Column, DateTime, ForeignKey,
                        Integer, String, Text, or_, select, delete)
from sqlalchemy.orm import Session

from models import Base, Player, SessionLocal, now

CATEGORIES = ('expeditions', 'market')


class NotificationPreference(Base):
    __tablename__ = 'notification_preferences'
    player_id = Column(BigInteger, ForeignKey('players.id'), primary_key=True)
    expeditions = Column(Boolean, nullable=False, default=False)
    market = Column(Boolean, nullable=False, default=False)


class NotificationOutbox(Base):
    __tablename__ = 'notification_outbox'
    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(BigInteger, ForeignKey('players.id'), nullable=False, index=True)
    event_key = Column(String(160), nullable=False, unique=True)
    category = Column(String(20), nullable=False)
    kind = Column(String(35), nullable=False)
    message = Column(String(700), nullable=False)
    status = Column(String(16), nullable=False, default='pending', index=True)
    attempts = Column(Integer, nullable=False, default=0)
    scheduled_at = Column(DateTime(timezone=True), nullable=False, index=True)
    lease_until = Column(DateTime(timezone=True))
    lease_token = Column(String(40))
    last_error = Column(String(50))
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    finished_at = Column(DateTime(timezone=True))


def aware(value: datetime | None):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def settings(db: Session, player_id: int) -> dict:
    p = db.get(NotificationPreference, player_id)
    return {key: bool(getattr(p, key)) if p else False for key in CATEGORIES}


def queue_notification(db: Session, player_id: int, event_key: str, category: str,
                       kind: str, message: str, scheduled_at: datetime | None = None) -> bool:
    """Only opted-in users get messages. Event keys dedupe repeats during game operations."""
    if category not in CATEGORIES or not event_key or len(event_key) > 160:
        raise ValueError('Некорректный тип игрового уведомления')
    preference = db.get(NotificationPreference, player_id)
    if not preference or not getattr(preference, category):
        return False
    if db.scalar(select(NotificationOutbox.id).where(NotificationOutbox.event_key == event_key)):
        return False
    db.add(NotificationOutbox(
        player_id=player_id, event_key=event_key, category=category, kind=kind,
        message=message[:700], scheduled_at=scheduled_at or now()))
    return True


def _eligible(db: Session, row: NotificationOutbox, instant: datetime) -> bool:
    """Do not deliver stale choices, disabled preferences, or banned players."""
    preference = db.get(NotificationPreference, row.player_id)
    player = db.get(Player, row.player_id)
    if not player or player.banned or player.frozen or not preference:
        return False
    if not getattr(preference, row.category, False):
        return False
    if row.kind == 'expedition_incident':
        from expeditions import ExpeditionIncident, ExpeditionRun
        try:
            run_id = int(row.event_key.split(':')[1])
        except (ValueError, IndexError):
            return False
        run = db.get(ExpeditionRun, run_id)
        incident = db.scalar(select(ExpeditionIncident).where(ExpeditionIncident.run_id == run_id))
        return bool(run and incident and run.status == 'active' and not incident.choice
                    and run.finishes_at and aware(run.finishes_at) > instant)
    return True


def claim_batch(limit: int = 5) -> list[dict]:
    """Lease at most five due messages; concurrent workers cannot claim the same row."""
    limit = max(1, min(5, limit))
    instant = now()
    with SessionLocal.begin() as db:
        due = db.scalars(select(NotificationOutbox).where(
            NotificationOutbox.scheduled_at <= instant,
            or_(NotificationOutbox.status == 'pending',
                (NotificationOutbox.status == 'sending') &
                (NotificationOutbox.lease_until < instant)))
            .order_by(NotificationOutbox.scheduled_at, NotificationOutbox.id)
            .limit(limit).with_for_update(skip_locked=True)).all()
        result = []
        for row in due:
            if not _eligible(db, row, instant):
                row.status = 'skipped'
                row.finished_at = instant
                row.lease_until = None
                row.lease_token = None
                continue
            if row.attempts >= 8:
                row.status = 'failed'
                row.finished_at = instant
                row.last_error = 'too_many_attempts'
                continue
            lease = uuid4().hex
            row.status = 'sending'
            row.attempts += 1
            row.lease_token = lease
            row.lease_until = instant + timedelta(seconds=120)
            result.append({'id': row.id, 'lease': lease, 'player_id': row.player_id,
                           'message': row.message})
        return result


def complete_delivery(id: int, lease: str, result: dict):
    instant = now()
    with SessionLocal.begin() as db:
        row = db.scalar(select(NotificationOutbox).where(NotificationOutbox.id == id)
                        .with_for_update())
        if not row or row.status != 'sending' or row.lease_token != lease:
            return False
        row.lease_until = None
        row.lease_token = None
        if result.get('ok'):
            row.status = 'sent'
            row.finished_at = instant
            row.last_error = None
        elif result.get('error_code') in (400, 403):
            row.status = 'failed'
            row.finished_at = instant
            row.last_error = 'telegram_rejected'
        elif row.attempts >= 8:
            row.status = 'failed'
            row.finished_at = instant
            row.last_error = 'too_many_attempts'
        else:
            # Telegram 429 (rate-limited) and transport / 5xx: retry with backoff.
            row.status = 'pending'
            raw_retry = (result.get('parameters') or {}).get('retry_after', 0)
            try:
                retry = min(3600, max(0, int(raw_retry)))
            except (TypeError, ValueError):
                retry = 0
            delay = max(retry, min(3600, 30 * 2 ** min(row.attempts, 7)))
            row.scheduled_at = instant + timedelta(seconds=delay)
            row.last_error = 'telegram_retry'
        return True


def cleanup(db: Session, limit: int = 200):
    """Never delete pending messages; keep 45 days of delivery history."""
    old = now() - timedelta(days=45)
    ids = db.scalars(select(NotificationOutbox.id).where(
        NotificationOutbox.status.in_(('sent', 'skipped', 'failed')),
        NotificationOutbox.finished_at < old).order_by(NotificationOutbox.id)
        .limit(limit)).all()
    if ids:
        db.execute(delete(NotificationOutbox).where(NotificationOutbox.id.in_(ids)))
    return len(ids)


class PreferenceChange(BaseModel):
    category: str
    enabled: bool


def install_notifications(app, with_player):
    router = APIRouter(prefix='/api/notifications', tags=['Notifications'])

    def session():
        with SessionLocal() as db:
            yield db

    @router.get('')
    def overview(request: Request, db: Session = Depends(session)):
        with db.begin():
            player = with_player(request, db)
            rows = db.scalars(select(NotificationOutbox).where(
                NotificationOutbox.player_id == player.id)
                .order_by(NotificationOutbox.id.desc()).limit(15)).all()
            return {'settings': settings(db, player.id),
                    'history': [{'id': row.id, 'category': row.category, 'kind': row.kind,
                                 'message': row.message, 'status': row.status,
                                 'created_at': aware(row.created_at).isoformat()}
                                for row in rows]}

    @router.post('/settings')
    def change_settings(body: PreferenceChange, request: Request,
                        db: Session = Depends(session)):
        if body.category not in CATEGORIES:
            raise ValueError('Неизвестная категория уведомлений')
        with db.begin():
            player = with_player(request, db)
            entry = db.scalar(select(NotificationPreference).where(
                NotificationPreference.player_id == player.id).with_for_update())
            if not entry:
                entry = NotificationPreference(player_id=player.id)
                db.add(entry)
            setattr(entry, body.category, body.enabled)
            return {'message': 'Уведомления включены' if body.enabled else 'Уведомления отключены',
                    'settings': settings(db, player.id)}

    app.include_router(router)
