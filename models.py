import os
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, BigInteger, String, Float, Boolean, Text, ForeignKey, DateTime, UniqueConstraint, JSON, event, insert, inspect
from sqlalchemy.orm import declarative_base, sessionmaker, Session

URL = os.getenv('DATABASE_URL', 'sqlite:///./zombo.db')
if URL.startswith('postgres://'):
    URL = URL.replace('postgres://', 'postgresql+psycopg://', 1)
elif URL.startswith('postgresql://'):
    URL = URL.replace('postgresql://', 'postgresql+psycopg://', 1)
engine = create_engine(URL, pool_pre_ping=True, connect_args={'check_same_thread': False, 'timeout': 30} if URL.startswith('sqlite') else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()

def now(): return datetime.now(timezone.utc)

class Player(Base):
    __tablename__ = 'players'
    id = Column(BigInteger, primary_key=True)
    name = Column(String(90), default='Выживший')
    username = Column(String(90), default='')
    hero_class = Column(String(30), nullable=True)
    level = Column(Integer, default=1)
    xp = Column(Integer, default=0)
    stat_points = Column(Integer, default=0)
    skill_points = Column(Integer, default=0)
    stats = Column(JSON, default=lambda: {'strength':0,'agility':0,'endurance':0,'accuracy':0,'regen':0,'luck':0})
    skills = Column(JSON, default=list)
    hp = Column(Integer, default=100)
    stamina = Column(Integer, default=200)
    hunger = Column(Integer, default=0)
    thirst = Column(Integer, default=0)
    caps = Column(Integer, default=150)
    zombo = Column(Integer, default=0)
    location = Column(String(50), default='base')
    kills = Column(Integer, default=0)
    rating = Column(Integer, default=1000)
    karma = Column(Integer, default=0)
    clan_id = Column(Integer, nullable=True)
    pvp_wins = Column(Integer, default=0)
    last_daily = Column(String(16), default='')
    last_tick = Column(DateTime(timezone=True), default=now)
    cooldown = Column(DateTime(timezone=True), nullable=True)
    vip_until = Column(DateTime(timezone=True), nullable=True)
    xp_boost_until = Column(DateTime(timezone=True), nullable=True)
    loot_boost_until = Column(DateTime(timezone=True), nullable=True)
    banned = Column(Boolean, default=False)
    frozen = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=now)

class ItemStack(Base):
    __tablename__ = 'items'
    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(BigInteger, ForeignKey('players.id'), index=True)
    item_key = Column(String(55), nullable=False)
    quantity = Column(Integer, default=1)
    equipped = Column(Boolean, default=False)
    __table_args__ = (UniqueConstraint('player_id', 'item_key', 'equipped', name='unique_inventory_stack'),)


class ResourceLedger(Base):
    """Committed resource movements. source_event groups rows from one transaction."""
    __tablename__ = 'resource_ledger'
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_event = Column(String(160), nullable=False)
    sequence = Column(Integer, nullable=False)
    player_id = Column(BigInteger, nullable=False, index=True)
    kind = Column(String(12), nullable=False)  # currency | item | gear
    resource_key = Column(String(80), nullable=False)
    delta = Column(Integer, nullable=False)
    balance_after = Column(Integer)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (UniqueConstraint('source_event', 'sequence', name='uq_resource_ledger_event_sequence'),)


class ClanTreasuryLedger(Base):
    """Committed clan treasury movements. Separate owner IDs from player ledger."""
    __tablename__ = 'clan_treasury_ledger'
    id = Column(Integer, primary_key=True, autoincrement=True)
    clan_id = Column(Integer, nullable=False, index=True)
    source_event = Column(String(160), nullable=False)
    sequence = Column(Integer, nullable=False)
    delta = Column(Integer, nullable=False)
    balance_after = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (UniqueConstraint('source_event', 'sequence', name='uq_clan_treasury_ledger_event_sequence'),)


def _total_experience(level: int, xp: int) -> int:
    """Lifetime XP equivalent, handling level-up carry without negative phantom entries."""
    total = int(xp or 0)
    for current_level in range(1, max(1, int(level or 1))):
        total += int(150 * current_level ** 1.75 + 300 * current_level)
    return total


def tag_resource_operation(db: Session, label: str, *, stable: bool = False):
    """Give all movements in this transaction a traceable, unique source ID."""
    if stable:
        db.info['resource_source_event'] = label[:160]
    else:
        db.info.setdefault('resource_source_event', f'{label[:115]}:{uuid4().hex}')


def _before_value(obj, field):
    history = inspect(obj).attrs[field].history
    return history.deleted[0] if history.deleted else getattr(obj, field)


@event.listens_for(Session, 'after_flush')
def _record_resource_movements(db, _flush_context):
    """Core SQL insert shares the gameplay transaction and rolls back with it."""
    from gear import GearItem
    rows = []
    clan_rows = []

    def treasury_movement(clan_id, delta, balance):
        if clan_id is not None and delta:
            clan_rows.append({'clan_id': clan_id, 'delta': delta,
                              'balance_after': balance, 'created_at': now()})

    def movement(owner, kind, key, delta, balance=None):
        if owner is not None and delta:
            rows.append({'player_id': owner, 'kind': kind, 'resource_key': str(key),
                         'delta': delta, 'balance_after': balance, 'created_at': now()})

    for obj in db.new:
        if isinstance(obj, Player):
            movement(obj.id, 'currency', 'caps', obj.caps or 0, obj.caps)
            movement(obj.id, 'currency', 'zombo', obj.zombo or 0, obj.zombo)
            lifetime_xp = _total_experience(obj.level, obj.xp)
            movement(obj.id, 'xp', 'lifetime', lifetime_xp, lifetime_xp)
        elif isinstance(obj, Clan):
            treasury_movement(obj.id, obj.treasury or 0, obj.treasury or 0)
        elif isinstance(obj, ItemStack):
            movement(obj.player_id, 'item', obj.item_key, obj.quantity or 0)
        elif isinstance(obj, GearItem):
            movement(obj.player_id, 'gear', obj.id, 1)
    for obj in db.dirty:
        if isinstance(obj, Player):
            for field in ('caps', 'zombo'):
                if inspect(obj).attrs[field].history.has_changes():
                    before = _before_value(obj, field)
                    movement(obj.id, 'currency', field, obj.__dict__[field] - before, obj.__dict__[field])
            state = inspect(obj)
            if any(state.attrs[field].history.has_changes() for field in ('xp', 'level')):
                previous = _total_experience(_before_value(obj, 'level'), _before_value(obj, 'xp'))
                current = _total_experience(obj.level, obj.xp)
                movement(obj.id, 'xp', 'lifetime', current - previous, current)
        elif isinstance(obj, Clan):
            if inspect(obj).attrs.treasury.history.has_changes():
                before = _before_value(obj, 'treasury') or 0
                treasury_movement(obj.id, (obj.treasury or 0) - before, obj.treasury or 0)
        elif isinstance(obj, ItemStack):
            state = inspect(obj)
            if any(state.attrs[field].history.has_changes() for field in ('quantity', 'player_id', 'item_key')):
                old_owner, old_key, old_qty = (_before_value(obj, field) for field in ('player_id', 'item_key', 'quantity'))
                if (old_owner, old_key) == (obj.player_id, obj.item_key):
                    movement(obj.player_id, 'item', obj.item_key, obj.quantity - old_qty)
                else:
                    movement(old_owner, 'item', old_key, -old_qty)
                    movement(obj.player_id, 'item', obj.item_key, obj.quantity)
        elif isinstance(obj, GearItem) and inspect(obj).attrs.player_id.history.has_changes():
            movement(_before_value(obj, 'player_id'), 'gear', obj.id, -1)
            movement(obj.player_id, 'gear', obj.id, 1)
    for obj in db.deleted:
        if isinstance(obj, Player):
            movement(obj.id, 'currency', 'caps', -_before_value(obj, 'caps'), 0)
            movement(obj.id, 'currency', 'zombo', -_before_value(obj, 'zombo'), 0)
            movement(obj.id, 'xp', 'lifetime', -_total_experience(obj.level, obj.xp), 0)
        elif isinstance(obj, Clan):
            treasury_movement(obj.id, -(obj.treasury or 0), 0)
        elif isinstance(obj, ItemStack):
            movement(_before_value(obj, 'player_id'), 'item', _before_value(obj, 'item_key'),
                     -_before_value(obj, 'quantity'))
        elif isinstance(obj, GearItem):
            movement(_before_value(obj, 'player_id'), 'gear', obj.id, -1)
    if rows:
        source = db.info.setdefault('resource_source_event', f'system:{uuid4().hex}')
        start = db.info.get('resource_sequence', 0)
        for offset, row in enumerate(rows):
            row['source_event'] = source
            row['sequence'] = start + offset
        db.connection().execute(insert(ResourceLedger.__table__), rows)
        db.info['resource_sequence'] = start + len(rows)
    if clan_rows:
        source = db.info.setdefault('resource_source_event', f'system:{uuid4().hex}')
        start = db.info.get('treasury_sequence', 0)
        for offset, row in enumerate(clan_rows):
            row['source_event'] = source
            row['sequence'] = start + offset
        db.connection().execute(insert(ClanTreasuryLedger.__table__), clan_rows)
        db.info['treasury_sequence'] = start + len(clan_rows)


@event.listens_for(Session, 'after_transaction_end')
def _clear_resource_operation(db, transaction):
    if transaction.parent is None:
        db.info.pop('resource_source_event', None)
        db.info.pop('resource_sequence', None)
        db.info.pop('treasury_sequence', None)

class Battle(Base):
    __tablename__ = 'battles'
    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(BigInteger, index=True, unique=True)
    kind = Column(String(20), default='zombie')
    enemy = Column(String(90), default='Ходячий')
    enemy_hp = Column(Integer, default=50)
    enemy_max_hp = Column(Integer, default=50)
    enemy_damage = Column(Integer, default=8)
    turn = Column(Integer, default=0)
    log = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), default=now)

class Clan(Base):
    __tablename__ = 'clans'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(55), unique=True)
    leader_id = Column(BigInteger)
    treasury = Column(Integer, default=0)
    level = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), default=now)

class Territory(Base):
    __tablename__ = 'territories'
    id = Column(String(30), primary_key=True)
    clan_id = Column(Integer, nullable=True)
    strength = Column(Integer, default=25)
    next_attack = Column(DateTime(timezone=True), nullable=True)

class WorldBoss(Base):
    __tablename__ = 'world_boss'
    id = Column(Integer, primary_key=True)
    name = Column(String(90), default='Гниющий колосс')
    hp = Column(Integer, default=500000)
    max_hp = Column(Integer, default=500000)
    spawn_at = Column(DateTime(timezone=True), default=now)

class BossHit(Base):
    __tablename__ = 'boss_hits'
    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(BigInteger, index=True)
    spawn_at = Column(String(64), index=True)
    damage = Column(Integer, default=0)
    last_hit = Column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint('player_id', 'spawn_at', name='unique_boss_player'),)

class MarketLot(Base):
    __tablename__ = 'lots'
    id = Column(Integer, primary_key=True, autoincrement=True)
    seller_id = Column(BigInteger, index=True)
    offered_key = Column(String(55))
    offered_qty = Column(Integer)
    wanted_key = Column(String(55))
    wanted_qty = Column(Integer)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=now)

class QuestProgress(Base):
    __tablename__ = 'quest_progress'
    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(BigInteger, index=True)
    code = Column(String(50))
    amount = Column(Integer, default=0)
    claimed = Column(Boolean, default=False)
    __table_args__ = (UniqueConstraint('player_id', 'code', name='unique_quest'),)

class PvPMatch(Base):
    __tablename__ = 'pvp_matches'
    id = Column(Integer, primary_key=True, autoincrement=True)
    challenger_id = Column(BigInteger, index=True)
    defender_id = Column(BigInteger, index=True)
    state = Column(String(20), default='pending')
    current_id = Column(BigInteger, nullable=True)
    hp_a = Column(Integer, default=100)
    hp_b = Column(Integer, default=100)
    log = Column(JSON, default=list)
    updated_at = Column(DateTime(timezone=True), default=now)

class Payment(Base):
    __tablename__ = 'payments'
    id = Column(String(120), primary_key=True)
    player_id = Column(BigInteger, index=True)
    stars = Column(Integer)
    zombo = Column(Integer)
    created_at = Column(DateTime(timezone=True), default=now)

class StarInvoice(Base):
    """Server-issued Stars invoice. Receipts remain unique by Telegram charge ID."""
    __tablename__ = 'star_invoices'
    payload = Column(String(128), primary_key=True)
    player_id = Column(BigInteger, ForeignKey('players.id'), nullable=False, index=True)
    offer_key = Column(String(55), nullable=False)
    stars = Column(Integer, nullable=False)
    zombo = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    expires_at = Column(DateTime(timezone=True), nullable=False)

class PaymentReview(Base):
    """Authenticated payment updates requiring operator reconciliation."""
    __tablename__ = 'payment_reviews'
    charge_id = Column(String(120), primary_key=True)
    player_id = Column(BigInteger, nullable=False, index=True)
    payload = Column(String(128), nullable=False)
    currency = Column(String(8), nullable=False)
    amount = Column(Integer, nullable=False)
    reason = Column(String(60), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)

class ClanOfficer(Base):
    """Additional clan permission (leader is stored in Clan)."""
    __tablename__ = 'clan_officers'
    clan_id = Column(Integer, ForeignKey('clans.id'), primary_key=True)
    player_id = Column(BigInteger, ForeignKey('players.id'), primary_key=True)
    role = Column(String(20), nullable=False, default='warlord')

class TerritoryTax(Base):
    __tablename__ = 'territory_taxes'
    territory_id = Column(String(30), ForeignKey('territories.id'), primary_key=True)
    pending = Column(BigInteger, nullable=False, default=0)
    collected = Column(BigInteger, nullable=False, default=0)
    remainder = Column(Integer, nullable=False, default=0)
    last_collection = Column(DateTime(timezone=True), default=now, nullable=False)

class TerritoryWar(Base):
    __tablename__ = 'territory_wars'
    id = Column(Integer, primary_key=True, autoincrement=True)
    territory_id = Column(String(30), ForeignKey('territories.id'), nullable=False, index=True)
    war_date = Column(String(10), nullable=False)
    attacker_clan_id = Column(Integer, nullable=True)
    defender_clan_id = Column(Integer, nullable=True)
    bid = Column(Integer, nullable=False, default=0)
    status = Column(String(20), default='bidding', nullable=False)
    round = Column(Integer, default=0, nullable=False)
    winner_clan_id = Column(Integer, nullable=True)
    log = Column(JSON, default=list)
    __table_args__ = (UniqueConstraint('territory_id','war_date',name='uq_war_territory_date'),)

class WarFighter(Base):
    __tablename__ = 'war_fighters'
    id = Column(Integer, primary_key=True, autoincrement=True)
    war_id = Column(Integer, ForeignKey('territory_wars.id'), nullable=False, index=True)
    player_id = Column(BigInteger, ForeignKey('players.id'), nullable=False)
    side = Column(String(12), nullable=False)  # attacker | defender
    hp = Column(Integer, nullable=False)
    max_hp = Column(Integer, nullable=False)
    damage = Column(Integer, nullable=False, default=0)
    last_action_round = Column(Integer, default=-1, nullable=False)
    guarding_round = Column(Integer, default=-1, nullable=False)
    __table_args__ = (UniqueConstraint('war_id','player_id',name='uq_war_fighter'),)
