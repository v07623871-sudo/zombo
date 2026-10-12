from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.test_game import app
from models import SessionLocal, Player, MarketLot, ResourceLedger
from game import give_item, item_count
from gear import GearItem, create_gear
from gear_market import GearSale


def h(pid):
    return {'Authorization':f'demo:{pid}'}


def test_market_buy_keeps_unique_item_and_closes_lot_once():
    seller, buyer = 988001, 988002
    with TestClient(app) as client:
        for pid in (seller,buyer):
            assert client.post('/api/class',headers=h(pid),json={'key':'soldier'}).status_code==200
        with SessionLocal.begin() as db:
            item=create_gear(db,seller,'rifle','epic','test')
            item.level=7
            gear_id=item.id
            seller_caps=db.get(Player,seller).caps
            buyer_caps=db.get(Player,buyer).caps
        listed=client.post('/api/gear-market/list',headers=h(seller),json={'gear_id':gear_id,'price':100})
        assert listed.status_code==200,listed.text
        sale_id=listed.json()['sale_id']
        bought=client.post('/api/gear-market/buy',headers=h(buyer),json={'id':sale_id})
        assert bought.status_code==200,bought.text
        assert client.post('/api/gear-market/buy',headers=h(buyer),json={'id':sale_id}).status_code==400
        with SessionLocal() as db:
            item=db.get(GearItem,gear_id)
            sale=db.get(GearSale,sale_id)
            assert item.player_id==buyer and item.rarity=='epic' and item.level==7
            assert sale.status=='sold' and sale.buyer_id==buyer and sale.fee==5
            assert db.get(Player,seller).caps==seller_caps+95
            assert db.get(Player,buyer).caps==buyer_caps-100
            trade_rows=db.scalars(select(ResourceLedger).where(
                ResourceLedger.source_event.like('POST:/api/gear-market/buy:%'))).all()
            assert {(row.player_id,row.kind,row.resource_key,row.delta) for row in trade_rows} == {
                (buyer,'currency','caps',-100), (seller,'currency','caps',95),
                (0,'gear',str(gear_id),-1), (buyer,'gear',str(gear_id),1)}


def test_reciprocal_barter_preserves_both_inventories():
    a, b = 988101, 988102
    with TestClient(app) as client:
        for pid in (a, b):
            assert client.post('/api/class', headers=h(pid), json={'key':'soldier'}).status_code == 200
        with SessionLocal.begin() as db:
            give_item(db, a, 'wood', 2)
            give_item(db, b, 'metal', 2)
            db.flush()
            before = {key: sum(item_count(db, pid, key) for pid in (a, b))
                      for key in ('wood', 'metal')}
        for pid, offer, want in ((a, 'wood', 'metal'), (b, 'metal', 'wood')):
            response = client.post('/api/market/create', headers=h(pid),
                                   json={'offer':offer, 'qty':1, 'want':want, 'want_qty':1})
            assert response.status_code == 200, response.text
        with SessionLocal() as db:
            lots = {lot.seller_id: lot.id for lot in db.query(MarketLot).filter(
                MarketLot.seller_id.in_([a, b]), MarketLot.active.is_(True))}
        for pid in (a, b):
            response = client.post('/api/market/buy', headers=h(pid),
                                   json={'id':lots[b if pid == a else a]})
            assert response.status_code == 200, response.text
        with SessionLocal() as db:
            assert all(db.get(MarketLot, lot_id).active is False for lot_id in lots.values())
            assert all(sum(item_count(db, pid, key) for pid in (a, b)) == before[key]
                       for key in before)
