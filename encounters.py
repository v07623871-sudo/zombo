"""Persistent wasteland encounters: server-rolled choices with actual costs and loot.

No rewards are given for opening/reloading the screen. A player has one
durable encounter slot, and each choice resolves it in a locked SQL transaction.
Exploration costs stamina and has a cooldown; unresolved choices survive restarts.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, select
from sqlalchemy.orm import Session

from models import Base, Player, SessionLocal, Battle, now
from game import give_item, take_item, item_count, gain_xp, spend_stamina

EXPLORE_COST = 6
COOLDOWN_SECONDS = 60
MAX_CAPS = 2_000_000_000
ENCOUNTERS = {
    'survivor': {
        'danger': 1, 'min_level': 1, 'locations': ('forest', 'city', 'factory', 'hospital', 'wasteland'),
        'title': 'Выживший у костра',
        'description': 'Истощённый незнакомец просит банку консервов. Его припасы разбросаны у угасающего костра.',
        'choices': {
            'help': {'label': 'Поделиться консервами', 'hint': '−1 консервы · +2 металла · +35 XP · +4 кармы · зацепка для радиосигнала'},
            'leave': {'label': 'Продолжить путь', 'hint': 'Без затрат · без награды'},
        },
    },
    'ambulance': {
        'danger': 2, 'min_level': 1, 'locations': ('forest', 'city', 'hospital'),
        'title': 'Брошенная скорая',
        'description': 'Медицинская машина съехала в кювет. Дверцы заклинило, внутри слышится скрежет.',
        'choices': {
            'search': {'label': 'Попробовать открыть', 'hint': '65% успеха: +2 аптечки, +35 XP · иначе −15 HP'},
            'force': {'label': 'Силой вскрыть заднюю дверь', 'hint': '−6 энергии · 85% успеха: +1 аптечка, +20 XP · иначе −10 HP'},
            'leave': {'label': 'Не трогать машину', 'hint': 'Без затрат'},
        },
    },
    'checkpoint': {
        'danger': 3, 'min_level': 5, 'locations': ('city', 'factory', 'wasteland'),
        'title': 'Заброшенный блокпост',
        'description': 'Под сорванной армейской сеткой обнаружен герметичный ящик. Рядом свежие следы.',
        'choices': {
            'loot': {'label': 'Вскрыть ящик', 'hint': '70% успеха: +3 металла, +2 проволоки, +30 XP · иначе −12 HP'},
            'observe': {'label': 'Осмотреть следы', 'hint': '85% успеха: +15 XP и маршрут торговца · иначе −4 энергии'},
            'leave': {'label': 'Уйти незамеченной', 'hint': 'Без затрат'},
        },
    },
    'trader': {
        'danger': 1, 'min_level': 1, 'locations': ('forest', 'city', 'factory', 'hospital', 'wasteland'),
        'title': 'Торговец-скиталец',
        'description': 'Молчаливый торговец предлагает аптечку и воду. Взамен просит двадцать пять крышек.',
        'choices': {
            'buy': {'label': 'Купить набор', 'hint': '−25 крышек · +1 аптечка, +1 вода'},
            'trade_map': {'label': 'Продать маршрут', 'hint': 'Нужен маршрут с блокпоста · +1 аптечка, +1 вода'},
            'leave': {'label': 'Отказаться от покупки', 'hint': 'Без затрат'},
        },
    },
    'radio': {
        'danger': 3, 'min_level': 5, 'locations': ('city', 'factory', 'hospital', 'wasteland'),
        'title': 'Сигнал сквозь помехи',
        'description': 'Из разбитой рации доносится просьба о помощи. Кто-то называет координаты склада.',
        'choices': {
            'answer': {'label': 'Ответить на сигнал', 'hint': '60% успеха: +50 крышек, +25 XP · иначе −8 энергии'},
            'trace': {'label': 'Сверить частоту выжившего', 'hint': 'Нужна зацепка выжившего · 75% успеха: +55 крышек, +35 XP · иначе −6 энергии'},
            'leave': {'label': 'Отключить рацию', 'hint': 'Без затрат'},
        },
    },
    'door': {
        'danger': 4, 'min_level': 5, 'locations': ('city', 'hospital', 'wasteland'),
        'title': 'Шорох за железной дверью',
        'description': 'Из подвала слышится чей-то плач. Дверь удаётся приоткрыть, но внутри темно.',
        'choices': {
            'rescue': {'label': 'Попробовать помочь', 'hint': '60% успеха: +1 аптечка, +45 XP, +3 кармы · иначе −20 HP'},
            'listen': {'label': 'Прислушаться у двери', 'hint': 'Без риска · +10 XP за осторожную разведку'},
            'leave': {'label': 'Не рисковать', 'hint': 'Без затрат'},
        },
    },
}


class EncounterState(Base):
    __tablename__ = 'player_encounters'
    player_id = Column(BigInteger, ForeignKey('players.id'), primary_key=True)
    key = Column(String(25), nullable=False)
    location = Column(String(30), nullable=False)
    roll = Column(Integer, nullable=False)
    status = Column(String(12), nullable=False, default='pending')
    choice = Column(String(25))
    outcome = Column(String(650))
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    resolved_at = Column(DateTime(timezone=True))


class EncounterClue(Base):
    """One-use story leads. The player lock serializes earning and spending them."""
    __tablename__ = 'encounter_clues'
    player_id = Column(BigInteger, ForeignKey('players.id'), primary_key=True)
    code = Column(String(30), primary_key=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)


CLUE_LABELS = {'survivor_frequency': 'Частота выжившего',
               'trader_route': 'Маршрут торговца'}


def clue_codes(db: Session, pid: int):
    return set(db.scalars(select(EncounterClue.code).where(EncounterClue.player_id == pid)))


def add_clue(db: Session, pid: int, code: str):
    if db.get(EncounterClue, (pid, code)) is None:
        db.add(EncounterClue(player_id=pid, code=code))


def spend_clue(db: Session, pid: int, code: str):
    clue = db.get(EncounterClue, (pid, code))
    if clue is None:
        raise ValueError('Для этого решения не хватает зацепки из другой встречи')
    db.delete(clue)


def aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def pending_encounter(db: Session, pid: int) -> bool:
    return bool(db.scalar(select(EncounterState.player_id).where(
        EncounterState.player_id == pid, EncounterState.status == 'pending')))


def view(state: EncounterState | None, clues=()):
    if state is None:
        return None
    definition = ENCOUNTERS[state.key]
    clues = set(clues)
    choices = {key: {**option, 'locked': bool(
        (key == 'trace' and 'survivor_frequency' not in clues) or
        (key == 'trade_map' and 'trader_route' not in clues))}
        for key, option in definition['choices'].items()} if state.status == 'pending' else {}
    return {'title': definition['title'], 'description': definition['description'],
            'danger': definition['danger'], 'choices': choices,
            'status': state.status, 'location': state.location,
            'choice': state.choice, 'outcome': state.outcome,
            'created_at': aware(state.created_at).isoformat(),
            'resolved_at': aware(state.resolved_at).isoformat() if state.resolved_at else None}


def start(db: Session, player: Player, *, key: str | None = None, roll: int | None = None):
    """Use player lock acquired by with_player; do not expose roll to the client."""
    if player.location == 'base':
        raise ValueError('Сначала выбери локацию за пределами убежища')
    if db.scalar(select(Battle.id).where(Battle.player_id == player.id)):
        raise ValueError('Сначала заверши бой')
    state = db.scalar(select(EncounterState).where(EncounterState.player_id == player.id).with_for_update())
    if state and state.status == 'pending':
        raise ValueError('Сначала прими решение в текущей встрече')
    instant = now()
    if state and state.resolved_at and instant - aware(state.resolved_at) < timedelta(seconds=COOLDOWN_SECONDS):
        seconds = max(1, int((timedelta(seconds=COOLDOWN_SECONDS) - (instant - aware(state.resolved_at))).total_seconds()) + 1)
        raise ValueError(f'Следующую встречу можно искать через {seconds} сек.')
    eligible = [name for name, definition in ENCOUNTERS.items()
                if player.location in definition['locations'] and player.level >= definition['min_level']]
    keys = eligible.copy()
    if state and state.key in keys and len(keys) > 1:
        keys.remove(state.key)  # Avoid immediately repeating the same story.
    chosen = key if key is not None else secrets.choice(keys)
    if chosen not in ENCOUNTERS:
        raise ValueError('Неизвестная встреча')
    if chosen not in eligible:
        raise ValueError('Эта встреча недоступна в текущей локации или на текущем уровне')
    result_roll = secrets.randbelow(100) if roll is None else roll
    if not isinstance(result_roll, int) or not 0 <= result_roll < 100:
        raise ValueError('Неверный бросок встречи')
    spend_stamina(player, EXPLORE_COST)
    if state:
        state.key = chosen
        state.location = player.location
        state.roll = result_roll
        state.status = 'pending'
        state.choice = None
        state.outcome = None
        state.created_at = instant
        state.resolved_at = None
    else:
        state = EncounterState(player_id=player.id, key=chosen, location=player.location,
                               roll=result_roll, status='pending', created_at=instant)
        db.add(state)
    db.flush()
    return state


def finish(db: Session, player: Player, action: str):
    state = db.scalar(select(EncounterState).where(EncounterState.player_id == player.id).with_for_update())
    if not state or state.status != 'pending':
        raise ValueError('Нет незавершённой встречи')
    if action not in ENCOUNTERS[state.key]['choices']:
        raise ValueError('Неизвестное решение')
    key, roll = state.key, state.roll
    if action == 'leave':
        message = 'Ты решила не рисковать и спокойно продолжила путь.'
    elif key == 'survivor' and action == 'help':
        if item_count(db, player.id, 'food') < 1:
            raise ValueError('Нужна одна банка консервов. Можно выбрать другой вариант.')
        take_item(db, player.id, 'food', 1)
        give_item(db, player.id, 'metal', 2)
        player.karma += 4
        gain_xp(player, 35)
        add_clue(db, player.id, 'survivor_frequency')
        message = 'Незнакомец делится металлом и частотой рации: +2 металла, +35 XP, +4 кармы. Потрачены консервы.'
    elif key == 'ambulance' and action == 'search':
        if roll < 65:
            give_item(db, player.id, 'medkit', 2)
            gain_xp(player, 35)
            message = 'Вскрыт медицинский отсек: +2 аптечки и +35 XP.'
        else:
            player.hp = max(1, player.hp - 15)
            message = 'Из темноты вырвался заражённый. Потеряно до 15 HP; добычи нет.'
    elif key == 'ambulance' and action == 'force':
        spend_stamina(player, 6)
        if roll < 85:
            give_item(db, player.id, 'medkit', 1)
            gain_xp(player, 20)
            message = 'Дверь поддалась: +1 аптечка, +20 XP. Потрачено 6 энергии.'
        else:
            player.hp = max(1, player.hp - 10)
            message = 'Внутри засада: потеряно до 10 HP и 6 энергии.'
    elif key == 'checkpoint' and action == 'loot':
        if roll < 70:
            give_item(db, player.id, 'metal', 3)
            give_item(db, player.id, 'wire', 2)
            gain_xp(player, 30)
            message = 'Склад вскрыт: +3 металла, +2 проволоки и +30 XP.'
        else:
            player.hp = max(1, player.hp - 12)
            message = 'Ловушка сработала. Потеряно до 12 HP; ящик пуст.'
    elif key == 'checkpoint' and action == 'observe':
        if roll < 85:
            add_clue(db, player.id, 'trader_route')
            gain_xp(player, 15)
            message = 'По следам найден маршрут торговца: +15 XP. Зацепка пригодится при встрече с ним.'
        else:
            player.stamina = max(0, player.stamina - 4)
            message = 'Следы теряются в пыли. Потрачено до 4 энергии.'
    elif key == 'trader' and action == 'buy':
        if player.caps < 25:
            raise ValueError('Не хватает 25 крышек. Можно отказаться от сделки.')
        player.caps -= 25
        give_item(db, player.id, 'medkit', 1)
        give_item(db, player.id, 'water', 1)
        message = 'Куплен дорожный набор: −25 крышек, +1 аптечка и +1 вода.'
    elif key == 'trader' and action == 'trade_map':
        spend_clue(db, player.id, 'trader_route')
        give_item(db, player.id, 'medkit', 1)
        give_item(db, player.id, 'water', 1)
        message = 'Торговец забрал маршрут: +1 аптечка и +1 вода. Зацепка использована.'
    elif key == 'radio' and action == 'answer':
        if roll < 60:
            if player.caps > MAX_CAPS - 50:
                raise ValueError('Кошелёк заполнен. Можно выбрать другой вариант.')
            player.caps += 50
            gain_xp(player, 25)
            message = 'Сигнал оказался настоящим! Найден тайник: +50 крышек и +25 XP.'
        else:
            player.stamina = max(0, player.stamina - 8)
            message = 'В эфире был только шум. Поиски потратили до 8 энергии.'
    elif key == 'radio' and action == 'trace':
        if roll < 75 and player.caps > MAX_CAPS - 55:
            raise ValueError('Кошелёк заполнен. Можно выбрать другой вариант.')
        spend_clue(db, player.id, 'survivor_frequency')
        if roll < 75:
            player.caps += 55
            gain_xp(player, 35)
            message = 'Частота привела к тайнику: +55 крышек, +35 XP. Зацепка использована.'
        else:
            player.stamina = max(0, player.stamina - 6)
            message = 'Сигнал оборвался. Потрачено до 6 энергии; зацепка использована.'
    elif key == 'door' and action == 'rescue':
        if roll < 60:
            give_item(db, player.id, 'medkit', 1)
            player.karma += 3
            gain_xp(player, 45)
            message = 'Человек спасён! +1 аптечка, +45 XP и +3 кармы.'
        else:
            player.hp = max(1, player.hp - 20)
            message = 'В подвале оказалась ловушка. Потеряно до 20 HP.'
    elif key == 'door' and action == 'listen':
        gain_xp(player, 10)
        message = 'Ты замечаешь опасность за дверью и отмечаешь путь: +10 XP.'
    else:
        raise ValueError('Неизвестное решение')
    state.status = 'resolved'
    state.choice = action
    state.outcome = message
    state.resolved_at = now()
    db.flush()
    return message


class EncounterChoice(BaseModel):
    action: str = Field(min_length=2, max_length=25)


def install_encounters(app, with_player, ready):
    router = APIRouter(prefix='/api/encounters', tags=['Encounters'])

    def session():
        with SessionLocal() as db:
            yield db

    @router.get('')
    def current(request: Request, db: Session = Depends(session)):
        with db.begin():
            p = with_player(request, db)
            state = db.get(EncounterState, p.id)
            clues = clue_codes(db, p.id)
            return {'encounter': view(state, clues), 'clues': [CLUE_LABELS[code] for code in sorted(clues)],
                    'pending': bool(state and state.status == 'pending'),
                    'explore_cost': EXPLORE_COST, 'cooldown_seconds': COOLDOWN_SECONDS}

    @router.post('/explore')
    def explore(request: Request, db: Session = Depends(session)):
        with db.begin():
            p = with_player(request, db)
            ready(p)
            state = start(db, p)
            return {'message': 'На пути обнаружена неожиданная встреча. Выбери, как поступить.',
                    'encounter': view(state, clue_codes(db, p.id))}

    @router.post('/resolve')
    def resolve(body: EncounterChoice, request: Request, db: Session = Depends(session)):
        with db.begin():
            p = with_player(request, db)
            ready(p)
            message = finish(db, p, body.action)
            return {'message': message, 'resolved': True}

    app.include_router(router)
