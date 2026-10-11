from fastapi.testclient import TestClient
from tests.test_game import app
from models import SessionLocal, Player
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
