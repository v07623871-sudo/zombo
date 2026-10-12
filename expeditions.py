"""Persistent twelve-hour cooperative expeditions.

All state lives in new tables. A run settles on the first request after its
deadline, so a restart cannot lose the result or issue rewards twice.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func, select
from sqlalchemy.orm import Session

from game import gain_xp, give_item
from gear import create_gear, gear_stats
from models import Base, Player, SessionLocal, now
from notifications import queue_notification

SCENARIOS = {
    'relay': {'name': 'Мёртвая радиостанция', 'level': 5, 'xp': 260,
              'caps': 180, 'gear': 'pistol', 'rarity': 'rare',
              'desc': 'Восстанови сигнал и вывези оборудование до рассвета.'},
    'convoy': {'name': 'Конвой через пустошь', 'level': 25, 'xp': 720,
               'caps': 480, 'gear': 'rifle', 'rarity': 'epic',
               'desc': 'Проведи караван сквозь заражённые территории.'},
    'hospital': {'name': 'Заражённый госпиталь', 'level': 12, 'xp': 390,
                 'caps': 260, 'gear': 'vest', 'rarity': 'rare',
                 'desc': 'Забери медикаменты и броню из закрытого госпитального корпуса.'},
    'bunker': {'name': 'Бункер «Ноль»', 'level': 40, 'xp': 1040,
               'caps': 760, 'gear': 'rifle', 'rarity': 'legendary',
               'desc': 'Штурмуй секретный комплекс, откуда началось заражение.'},
}

# Each expedition has one durable incident that becomes actionable after 4 hours.
# A fixed secret roll prevents the leader from re-rolling the outcome by tapping again.
INCIDENTS = {
    'relay': ('Чужой голос', 'По аварийной частоте кто-то зовёт на помощь. Время на исходе.',
              'Проверить источник сигнала', 'Идти напролом к радиобашне'),
    'convoy': ('Мост без опор', 'Перед конвоем провал, а за спиной слышны заражённые.',
               'Провести груз в обход', 'Прорваться по обломкам'),
    'hospital': ('Закрытое крыло', 'В палатах слышится движение. Сканер показывает десятки целей.',
                 'Зачистить входы', 'Рискнуть и проникнуть через подвал'),
    'bunker': ('Система карантина', 'Автоматика запирает бронедвери и включает сирену.',
               'Тихо отключить сигнализацию', 'Взломать дверь силой'),
}
EVENT_CHOICES = {
    'cautious': {'chance': 12, 'reward_percent': 85, 'label': 'ОСТОРОЖНО', 'hint': '+12% к шансу · 85% XP и крышек'},
    'risky': {'chance': -8, 'reward_percent': 135, 'label': 'РИСКОВАТЬ', 'hint': '−8% к шансу · 135% XP и крышек'},
}
EVENT_DELAY_HOURS = 4
ROLES = {'scout': 'Разведчик', 'guard': 'Защитник', 'medic': 'Медик', 'engineer': 'Техник'}
CLASS_AFFINITY = {'scout': 'thief', 'guard': 'soldier', 'medic': 'medic', 'engineer': 'assassin'}
MIN_PARTY = 3
MAX_PARTY = 10
LOBBY_HOURS = 6
RUN_HOURS = 12


class ExpeditionRun(Base):
    __tablename__ = 'expedition_runs'
    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(BigInteger, nullable=False, index=True)
    scenario = Column(String(30), nullable=False)
    status = Column(String(18), nullable=False, default='lobby', index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    lobby_expires_at = Column(DateTime(timezone=True), nullable=False)
    started_at = Column(DateTime(timezone=True))
    finishes_at = Column(DateTime(timezone=True))
    success_chance = Column(Integer)
    will_succeed = Column(Boolean)


class ExpeditionIncident(Base):
    __tablename__ = 'expedition_incidents'
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey('expedition_runs.id'), nullable=False, unique=True, index=True)
    key = Column(String(30), nullable=False)
    # Server-side roll, never exposed to the clients; one roll per run.
    roll = Column(Integer, nullable=False)
    choice = Column(String(20), nullable=True)
    reward_percent = Column(Integer, nullable=False, default=100)
    resolved_at = Column(DateTime(timezone=True), nullable=True)


class ExpeditionMember(Base):
    __tablename__ = 'expedition_members'
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey('expedition_runs.id'), nullable=False, index=True)
    player_id = Column(BigInteger, ForeignKey('players.id'), nullable=False, index=True)
    role = Column(String(20))
    rewarded = Column(Boolean, nullable=False, default=False)
    __table_args__ = (UniqueConstraint('run_id', 'player_id', name='unique_expedition_member'),)


class RunRequest(BaseModel):
    id: int = Field(gt=0, le=9223372036854775807)


class CreateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=30)


class PrepareRequest(RunRequest):
    role: str = Field(min_length=1, max_length=20)


class EventRequest(RunRequest):
    choice: str = Field(min_length=1, max_length=20)


def aware(value: datetime | None):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def current_run(db: Session, player_id: int):
    return db.scalar(select(ExpeditionRun).join(ExpeditionMember, ExpeditionMember.run_id == ExpeditionRun.id)
                     .where(ExpeditionMember.player_id == player_id,
                            ExpeditionRun.status.in_(['lobby', 'active']))
                     .order_by(ExpeditionRun.id.desc()).limit(1))


def settle(db: Session, run: ExpeditionRun, stamp: datetime):
    if run.status == 'lobby' and aware(run.lobby_expires_at) <= stamp:
        run.status = 'expired'
    elif run.status == 'active' and run.finishes_at and aware(run.finishes_at) <= stamp:
        run.status = 'cleared' if run.will_succeed else 'failed'


def settle_player(db: Session, player_id: int):
    """Settle only this player's run; old global backlogs cannot hide a result."""
    run = db.scalar(select(ExpeditionRun).join(ExpeditionMember,
        ExpeditionMember.run_id == ExpeditionRun.id).where(
        ExpeditionMember.player_id == player_id,
        ExpeditionRun.status.in_(['lobby', 'active'])).order_by(
        ExpeditionRun.id.desc()).limit(1).with_for_update(of=ExpeditionRun))
    if run:
        settle(db, run, now())
    db.flush()


def members(db: Session, run_id: int):
    return list(db.scalars(select(ExpeditionMember).where(ExpeditionMember.run_id == run_id)
                           .order_by(ExpeditionMember.id)))


def view(db: Session, run: ExpeditionRun, player_id: int):
    crew = members(db, run.id)
    names = {p.id: p.name for p in db.scalars(select(Player).where(Player.id.in_([m.player_id for m in crew])))}
    incident = db.scalar(select(ExpeditionIncident).where(ExpeditionIncident.run_id == run.id))
    event = None
    if incident and run.started_at:
        title, description, cautious, risky = INCIDENTS[incident.key]
        unlock = aware(run.started_at) + timedelta(hours=EVENT_DELAY_HOURS)
        event = {'title': title, 'description': description, 'available_at': unlock.isoformat(),
                 'ready': now() >= unlock, 'choice': incident.choice,
                 'choice_label': ({'cautious': cautious, 'risky': risky}.get(incident.choice)),
                 'reward_percent': incident.reward_percent,
                 'options': {'cautious': {**EVENT_CHOICES['cautious'], 'text': cautious},
                             'risky': {**EVENT_CHOICES['risky'], 'text': risky}}}
    return {'id': run.id, 'scenario': run.scenario, 'name': SCENARIOS[run.scenario]['name'],
            'event': event,
            'status': run.status, 'leader_id': run.creator_id, 'member_count': len(crew),
            'lobby_expires_at': aware(run.lobby_expires_at).isoformat(),
            'finishes_at': aware(run.finishes_at).isoformat() if run.finishes_at else None,
            'success_chance': run.success_chance,
            'mine': any(m.player_id == player_id for m in crew),
            'members': [{'id': m.player_id, 'name': names.get(m.player_id, 'Выживший'),
                         'role': m.role, 'rewarded': m.rewarded} for m in crew]}


def success_chance(db: Session, run: ExpeditionRun, crew: list[ExpeditionMember]):
    players = {p.id: p for p in db.scalars(select(Player).where(Player.id.in_([m.player_id for m in crew])))}
    config = SCENARIOS[run.scenario]
    if len(players) != len(crew):
        raise ValueError('Участник экспедиции не найден')
    average_level = sum(players[m.player_id].level for m in crew) / len(crew)
    affinity = sum(players[m.player_id].hero_class == CLASS_AFFINITY[m.role] for m in crew)
    gear = sum(sum(gear_stats(db, m.player_id).values()) for m in crew) / len(crew)
    chance = 44 + min(20, max(0, average_level - config['level']) * 1.5)
    chance += len({m.role for m in crew}) * 5 + affinity * 3 + min(10, gear / 7)
    return max(25, min(90, round(chance)))


def install_expeditions(app, with_player, ready):
    router = APIRouter(prefix='/api/expeditions', tags=['Expeditions'])

    def session():
        with SessionLocal() as db:
            yield db

    @router.get('')
    def list_expeditions(request: Request, db: Session = Depends(session)):
        with db.begin():
            player = with_player(request, db)
            settle_player(db, player.id)
            current = current_run(db, player.id)
            lobbies = db.scalars(select(ExpeditionRun).where(
                ExpeditionRun.status == 'lobby', ExpeditionRun.lobby_expires_at > now())
                                 .order_by(ExpeditionRun.id.desc()).limit(12)).all()
            recent = db.scalars(select(ExpeditionRun).join(ExpeditionMember,
                ExpeditionMember.run_id == ExpeditionRun.id).where(
                ExpeditionMember.player_id == player.id,
                ExpeditionRun.status.in_(['cleared', 'failed', 'expired']))
                .order_by(ExpeditionRun.id.desc()).limit(5)).all()
            # Keep older unclaimed rewards visible when the player has since
            # completed more missions. Claimed history stays small.
            unclaimed = db.scalars(select(ExpeditionRun).join(ExpeditionMember,
                ExpeditionMember.run_id == ExpeditionRun.id).where(
                ExpeditionMember.player_id == player.id,
                ExpeditionMember.rewarded == False,
                ExpeditionRun.status.in_(['cleared', 'failed']))
                .order_by(ExpeditionRun.id.desc()).limit(100)).all()
            recent = sorted({r.id: r for r in [*recent, *unclaimed]}.values(),
                            key=lambda run: run.id, reverse=True)
            return {'scenarios': SCENARIOS, 'roles': ROLES, 'duration_hours': RUN_HOURS,
                    'my_run': view(db, current, player.id) if current else None,
                    'lobbies': [view(db, r, player.id) for r in lobbies if r != current],
                    'recent': [view(db, r, player.id) for r in recent]}

    @router.post('/create')
    def create(body: CreateRequest, request: Request, db: Session = Depends(session)):
        with db.begin():
            player = with_player(request, db); ready(player); settle_player(db, player.id)
            config = SCENARIOS.get(body.key)
            if not config:
                raise ValueError('Экспедиция не найдена')
            if player.level < config['level']:
                raise ValueError(f'Нужен уровень {config["level"]}')
            if current_run(db, player.id):
                raise ValueError('Сначала заверши текущую экспедицию')
            run = ExpeditionRun(creator_id=player.id, scenario=body.key,
                                lobby_expires_at=now() + timedelta(hours=LOBBY_HOURS))
            db.add(run); db.flush()
            db.add(ExpeditionMember(run_id=run.id, player_id=player.id))
            return {'message': 'Группа создана. Выбери роль и пригласи ещё двоих.', 'id': run.id}

    @router.post('/join')
    def join(body: RunRequest, request: Request, db: Session = Depends(session)):
        with db.begin():
            player = with_player(request, db); ready(player); settle_player(db, player.id)
            run = db.scalar(select(ExpeditionRun).where(ExpeditionRun.id == body.id).with_for_update())
            if not run or run.status != 'lobby' or aware(run.lobby_expires_at) <= now():
                raise ValueError('Набор в группу закрыт')
            if player.level < SCENARIOS[run.scenario]['level']:
                raise ValueError('Не хватает уровня')
            if current_run(db, player.id):
                raise ValueError('Ты уже состоишь в экспедиции')
            count = db.scalar(select(func.count()).select_from(ExpeditionMember)
                              .where(ExpeditionMember.run_id == run.id))
            if count >= MAX_PARTY:
                raise ValueError('Группа заполнена')
            db.add(ExpeditionMember(run_id=run.id, player_id=player.id)); db.flush()
            return {'message': 'Ты в группе. Выбери роль до старта.'}

    @router.post('/prepare')
    def prepare(body: PrepareRequest, request: Request, db: Session = Depends(session)):
        with db.begin():
            player = with_player(request, db); ready(player)
            run = db.scalar(select(ExpeditionRun).where(ExpeditionRun.id == body.id).with_for_update())
            if not run or run.status != 'lobby' or aware(run.lobby_expires_at) <= now():
                raise ValueError('Подготовка группы завершена')
            member = db.scalar(select(ExpeditionMember).where(ExpeditionMember.run_id == run.id,
                            ExpeditionMember.player_id == player.id).with_for_update())
            if not member:
                raise ValueError('Ты не состоишь в этой группе')
            if body.role not in ROLES:
                raise ValueError('Неизвестная роль')
            member.role = body.role
            return {'message': f'Роль выбрана: {ROLES[body.role]}'}

    @router.post('/leave')
    def leave(body: RunRequest, request: Request, db: Session = Depends(session)):
        with db.begin():
            player = with_player(request, db)
            run = db.scalar(select(ExpeditionRun).where(ExpeditionRun.id == body.id).with_for_update())
            if not run or run.status != 'lobby' or aware(run.lobby_expires_at) <= now():
                raise ValueError('Выйти можно только до старта')
            member = db.scalar(select(ExpeditionMember).where(ExpeditionMember.run_id == run.id,
                            ExpeditionMember.player_id == player.id).with_for_update())
            if not member:
                raise ValueError('Ты не в этой группе')
            db.delete(member); db.flush()
            remaining = members(db, run.id)
            if not remaining:
                run.status = 'expired'
            elif run.creator_id == player.id:
                run.creator_id = remaining[0].player_id
            return {'message': 'Ты вышел из группы'}

    @router.post('/launch')
    def launch(body: RunRequest, request: Request, db: Session = Depends(session)):
        with db.begin():
            player = with_player(request, db); ready(player)
            run = db.scalar(select(ExpeditionRun).where(ExpeditionRun.id == body.id).with_for_update())
            if not run or run.status != 'lobby' or aware(run.lobby_expires_at) <= now():
                raise ValueError('Сбор группы завершён')
            if run.creator_id != player.id:
                raise ValueError('Запуск доступен только лидеру')
            crew = members(db, run.id)
            if not MIN_PARTY <= len(crew) <= MAX_PARTY:
                raise ValueError('Для старта нужно от 3 до 10 игроков')
            if any(not m.role for m in crew):
                raise ValueError('Каждый участник должен выбрать роль')
            if len({m.role for m in crew}) < 2:
                raise ValueError('Нужны минимум две разные роли')
            run.success_chance = success_chance(db, run, crew)
            roll = secrets.randbelow(100)
            run.will_succeed = roll < run.success_chance
            db.add(ExpeditionIncident(run_id=run.id, key=run.scenario, roll=roll))
            run.status = 'active'
            run.started_at = now()
            run.finishes_at = run.started_at + timedelta(hours=RUN_HOURS)
            scenario_name = SCENARIOS[run.scenario]['name']
            for member in crew:
                queue_notification(
                    db, member.player_id, f'expedition:{run.id}:launch:{member.player_id}',
                    'expeditions', 'expedition_started',
                    f'🧭 Экспедиция «{scenario_name}» началась. Возвращение через 12 часов.')
                queue_notification(
                    db, member.player_id, f'expedition:{run.id}:finish:{member.player_id}',
                    'expeditions', 'expedition_finished',
                    f'📦 Экспедиция «{scenario_name}» завершилась. Проверь результат и получи награду.',
                    scheduled_at=run.finishes_at)
            queue_notification(
                db, run.creator_id, f'expedition:{run.id}:incident:{run.creator_id}',
                'expeditions', 'expedition_incident',
                f'📻 В экспедиции «{scenario_name}» возникла проблема. Ты лидер: выбери решение для отряда.',
                scheduled_at=run.started_at + timedelta(hours=EVENT_DELAY_HOURS))
            return {'message': f'Отряд вышел. Возвращение через {RUN_HOURS} часов.'}

    @router.post('/event')
    def choose_event(body: EventRequest, request: Request, db: Session = Depends(session)):
        with db.begin():
            player = with_player(request, db); ready(player)
            run = db.scalar(select(ExpeditionRun).where(ExpeditionRun.id == body.id).with_for_update())
            if not run or run.status != 'active' or not run.finishes_at:
                raise ValueError('Эта экспедиция уже завершена или не началась')
            instant = now()
            if aware(run.finishes_at) <= instant:
                settle(db, run, instant)
                raise ValueError('Отряд уже вернулся, решение принять нельзя')
            if run.creator_id != player.id:
                raise ValueError('Решение принимает только лидер отряда')
            if not run.started_at or aware(run.started_at) + timedelta(hours=EVENT_DELAY_HOURS) > instant:
                raise ValueError('Инцидент появится через четыре часа после выхода отряда')
            event = db.scalar(select(ExpeditionIncident).where(ExpeditionIncident.run_id == run.id).with_for_update())
            if not event:
                raise ValueError('В этой экспедиции нет доступного инцидента')
            if event.choice:
                raise ValueError('Решение уже принято и не может быть изменено')
            if body.choice not in EVENT_CHOICES:
                raise ValueError('Неизвестное решение')
            effect = EVENT_CHOICES[body.choice]
            event.choice = body.choice
            event.reward_percent = effect['reward_percent']
            event.resolved_at = instant
            run.success_chance = max(15, min(95, run.success_chance + effect['chance']))
            run.will_succeed = event.roll < run.success_chance
            return {'message': f'Решение принято. Шанс успеха теперь {run.success_chance}%.',
                    'success_chance': run.success_chance, 'reward_percent': event.reward_percent}

    @router.post('/claim')
    def claim(body: RunRequest, request: Request, db: Session = Depends(session)):
        with db.begin():
            player = with_player(request, db)
            run = db.scalar(select(ExpeditionRun).where(ExpeditionRun.id == body.id).with_for_update())
            if not run:
                raise ValueError('Экспедиция не найдена')
            member = db.scalar(select(ExpeditionMember).where(ExpeditionMember.run_id == run.id,
                            ExpeditionMember.player_id == player.id).with_for_update())
            if not member:
                raise ValueError('Ты не участвовал в этой экспедиции')
            settle(db, run, now())
            if run.status not in ('cleared', 'failed'):
                raise ValueError('Экспедиция ещё не завершена или группа не вышла')
            if member.rewarded:
                raise ValueError('Награда уже получена')
            config = SCENARIOS[run.scenario]
            event = db.scalar(select(ExpeditionIncident).where(ExpeditionIncident.run_id == run.id))
            modifier = event.reward_percent if event and event.choice else 100
            xp = max(1, config['xp'] * modifier // 100)
            caps = max(1, config['caps'] * modifier // 100)
            if run.status == 'cleared':
                # Gear capacity is checked before the other rewards; a failure
                # rolls the entire transaction back, including the claim flag.
                item = create_gear(db, player.id, config['gear'], config['rarity'], 'expedition')
                gain_xp(player, xp)
                player.caps += caps
                give_item(db, player.id, 'metal', 3)
                message = f'Экспедиция успешна! +{xp} XP, +{caps} крышек, металл и снаряжение #{item.id}.'
            else:
                gain_xp(player, xp // 4)
                player.caps += caps // 4
                message = 'Отряд вернулся с потерями. Получена утешительная награда.'
            member.rewarded = True
            return {'message': message, 'status': run.status}

    app.include_router(router)
