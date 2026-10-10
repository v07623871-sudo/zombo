import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, BigInteger, String, Float, Boolean, Text, ForeignKey, DateTime, UniqueConstraint, JSON
from sqlalchemy.orm import declarative_base, sessionmaker

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