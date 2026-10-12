"""Standalone SQLite tests against actual gear_market module behavior.
The two existing model imports are faithfully represented by small SQLAlchemy models.
"""
import importlib.util
import sys
import types
from datetime import timedelta
from pathlib import Path
import pytest
from sqlalchemy import create_engine, Column, BigInteger, Integer, String, DateTime, Boolean, select
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timezone

Base = declarative_base()

def now(): return datetime.now(timezone.utc)

class Player(Base):
    __tablename__ = 'players'
    id = Column(BigInteger, primary_key=True)
    caps = Column(Integer, default=0)
    name = Column(String(90), default='Выживший')
    hero_class = Column(String(30), default='soldier')

class GearItem(Base):
    __tablename__ = 'gear_items'
    id = Column(Integer, primary_key=True)
    player_id = Column(BigInteger, nullable=False, index=True)
    base_key = Column(String(32), default='rifle')
    rarity = Column(String(16), default='rare')
    level = Column(Integer, default=3)
    equipped = Column(Boolean, default=False)
    source = Column(String(20), default='drop')
    obtained_at = Column(DateTime(timezone=True), default=now)

models = types.ModuleType('models')
models.Base, models.Player, models.now = Base, Player, now
models.SessionLocal = sessionmaker()
gear = types.ModuleType('gear')
gear.GearItem, gear.MAX_GEAR = GearItem, 80
gear.gear_view = lambda item: {'id':item.id,'name':'Автомат АК-47','rarity_name':'Редкий',
                              'rarity':item.rarity,'level':item.level,'slot':'weapon',
                              'power':30,'defense':0,'color':'#76aaff','icon':'🔫','equipped':item.equipped}
notifications_stub = types.ModuleType('notifications')
notifications_stub.queue_notification = lambda *args, **kwargs: False
previous = {name: sys.modules.get(name) for name in ('models', 'gear', 'notifications')}
try:
    sys.modules['models'] = models
    sys.modules['gear'] = gear
    sys.modules['notifications'] = notifications_stub
    spec = importlib.util.spec_from_file_location('gear_market_under_test', Path(__file__).resolve().parents[1] / 'gear_market.py')
    market = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(market)
finally:
    for name, module in previous.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module

@pytest.fixture
def db():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        session.add_all([Player(id=101,caps=5000,name='Продавец'), Player(id=202,caps=8000,name='Покупатель'), Player(id=303,caps=50,name='Бедняк')])
        session.add(GearItem(id=11,player_id=101,rarity='epic',level=7))
        session.commit()
        yield session
    engine.dispose()

def test_escrow_and_transfer_preserves_rarity_and_upgrade(db):
    sale=market.list_gear(db,db.get(Player,101),11,1000)
    assert db.get(GearItem,11).player_id==0
    assert market.browse_sales(db,202)['items'][0]['gear']['level']==7
    sale,item=market.buy_gear(db,db.get(Player,202),sale.id)
    assert item.player_id==202 and item.level==7 and item.rarity=='epic'
    assert db.get(Player,202).caps==7000
    assert db.get(Player,101).caps==5950
    assert sale.status=='sold' and sale.fee==50 and sale.buyer_id==202
    with pytest.raises(ValueError,match='продан|снят'):market.buy_gear(db,db.get(Player,303),sale.id)
    with pytest.raises(ValueError,match='закрыт'):market.cancel_sale(db,db.get(Player,101),sale.id)

def test_cancel_restores_identical_item_and_blocks_others(db):
    sale=market.list_gear(db,db.get(Player,101),11,400)
    with pytest.raises(ValueError,match='не твой'):market.cancel_sale(db,db.get(Player,202),sale.id)
    market.cancel_sale(db,db.get(Player,101),sale.id)
    assert db.get(GearItem,11).player_id==101
    assert sale.status=='cancelled' and sale.buyer_id is None
    with pytest.raises(ValueError,match='продан|снят'):market.buy_gear(db,db.get(Player,202),sale.id)
    newer=market.list_gear(db,db.get(Player,101),11,100)
    assert newer.id!=sale.id

def test_cannot_sell_equipped_or_unowned_or_twice(db):
    item=db.get(GearItem,11)
    item.equipped=True
    with pytest.raises(ValueError,match='Сначала сними'):market.list_gear(db,db.get(Player,101),11,100)
    item.equipped=False
    with pytest.raises(ValueError,match='нет в твоём'):market.list_gear(db,db.get(Player,202),11,100)
    sale=market.list_gear(db,db.get(Player,101),11,100)
    with pytest.raises(ValueError,match='нет в твоём'):market.list_gear(db,db.get(Player,101),11,100)
    assert sale.status=='active'

def test_insufficient_funds_rollback_buy(db):
    sale=market.list_gear(db,db.get(Player,101),11,400)
    with pytest.raises(ValueError,match='Недостаточно'):market.buy_gear(db,db.get(Player,303),sale.id)
    assert sale.status=='active' and db.get(GearItem,11).player_id==0
    assert db.get(Player,101).caps==5000

def test_list_limits_and_price_validation(db):
    seller=db.get(Player,101)
    for price in [10,250001,-1]:
        with pytest.raises(ValueError):market.list_gear(db,seller,11,price)
    for idx in range(11,17):
        if idx!=11:db.add(GearItem(id=idx,player_id=101))
    db.flush()
    for idx in range(11,16):market.list_gear(db,seller,idx,150)
    with pytest.raises(ValueError,match='пяти'):market.list_gear(db,seller,16,150)

def test_expiration_idempotent_and_returnable(db):
    sale=market.list_gear(db,db.get(Player,101),11,300)
    sale.expires_at=now()-timedelta(seconds=1)
    db.flush()
    assert market.expire_sales(db)==1
    assert market.expire_sales(db)==0
    assert sale.status=='expired' and db.get(GearItem,11).player_id==101
    assert not market.browse_sales(db,202)['items']
    market.list_gear(db,db.get(Player,101),11,100)

def test_buyer_at_gear_capacity_rejected(db):
    sale=market.list_gear(db,db.get(Player,101),11,450)
    for idx in range(100,180): db.add(GearItem(id=idx,player_id=202))
    db.flush()
    with pytest.raises(ValueError,match='заполнен'):market.buy_gear(db,db.get(Player,202),sale.id)
    assert sale.status=='active'

def test_market_http_routes_authenticated_and_validated(db):
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient
    engine=db.get_bind()
    def _factory():return sessionmaker(bind=engine,expire_on_commit=False)()
    market.SessionLocal=_factory
    def user(request,session):
        if request.headers.get('authorization')!='test':
            from fastapi import HTTPException
            raise HTTPException(401,'Unauthorized')
        return session.get(Player,101)
    app=FastAPI()
    market.install_gear_market(app,user,lambda p:None)
    client=TestClient(app)
    assert client.get('/api/gear-market').status_code==401
    assert client.get('/api/gear-market',headers={'Authorization':'test'}).status_code==200
    assert client.post('/api/gear-market/list',headers={'Authorization':'test'},json={'gear_id':11,'price':300}).status_code==200
    assert client.post('/api/gear-market/list',headers={'Authorization':'test'},json={'gear_id':11,'price':-10}).status_code==422
    assert client.get('/api/gear-market',headers={'Authorization':'test'}).json()['my_sales'][0]['status']=='active'

def test_history_survives_buyer_dismantling_item(db):
    sale=market.list_gear(db,db.get(Player,101),11,650)
    market.buy_gear(db,db.get(Player,202),sale.id)
    db.delete(db.get(GearItem,11))
    db.flush()
    row=market.browse_sales(db,101)['my_sales'][0]
    assert row['status']=='sold'
    assert row['gear']['rarity']=='epic'
    assert row['gear']['level']==7
    assert row['price']==650
