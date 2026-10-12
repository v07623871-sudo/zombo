"""ZOMBO 0.8: safe player-to-player fixed-price marketplace for unique gear.

A listed item is escrowed with player_id=0: it cannot be equipped, dismantled,
upgraded or listed again until the sale ends. No schema changes to legacy items.
For PostgreSQL, row locks make cancellation and buying a single-winner race.
"""
from datetime import timedelta, timezone
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Index, JSON, select, func
from sqlalchemy.orm import Session

from notifications import queue_notification
from models import Base, Player, SessionLocal, now
from gear import GearItem, MAX_GEAR, gear_view

FEE_PERCENT = 5
MIN_PRICE = 50
MAX_PRICE = 250000
MAX_LISTINGS = 5
LISTING_LIFETIME = timedelta(days=7)
ESCROW_OWNER = 0
MAX_CAPS = 2_000_000_000


class GearSale(Base):
    __tablename__ = 'gear_sales'
    id = Column(Integer, primary_key=True, autoincrement=True)
    # Do not FK to gear_items: the buyer may later dismantle an item.
    # The permanent item_snapshot keeps transaction history readable.
    gear_id = Column(Integer, nullable=False, index=True)
    item_snapshot = Column(JSON, nullable=False)
    seller_id = Column(BigInteger, ForeignKey('players.id'), nullable=False, index=True)
    buyer_id = Column(BigInteger, nullable=True, index=True)
    price = Column(Integer, nullable=False)
    fee = Column(Integer, nullable=False, default=0)
    status = Column(String(15), nullable=False, default='active')
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    closed_at = Column(DateTime(timezone=True))
    __table_args__ = (Index('ix_gear_sales_status_expires', 'status', 'expires_at'),)


def aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def fee_for(price: int) -> int:
    return max(1, (price * FEE_PERCENT + 99) // 100)


def expire_sales(db: Session, limit: int = 100) -> int:
    """Refund expired escrow in a transaction; safe to rerun after restarts."""
    instant = now()
    query = (select(GearSale).where(GearSale.status == 'active', GearSale.expires_at <= instant)
             .order_by(GearSale.expires_at, GearSale.id).limit(limit).with_for_update(skip_locked=True))
    count = 0
    for sale in db.scalars(query).all():
        item = db.scalar(select(GearItem).where(GearItem.id == sale.gear_id).with_for_update())
        if item and item.player_id == ESCROW_OWNER:
            item.player_id = sale.seller_id
        sale.status = 'expired'
        sale.closed_at = instant
        queue_notification(
            db, sale.seller_id, f'gear-sale:{sale.id}:expired',
            'market', 'gear_sale_expired',
            f'📦 Срок продажи лота #{sale.id} истёк. Снаряжение вернулось в арсенал.')
        count += 1
    return count


def list_gear(db: Session, seller: Player, gear_id: int, price: int) -> GearSale:
    if not MIN_PRICE <= price <= MAX_PRICE:
        raise ValueError(f'Цена должна быть от {MIN_PRICE} до {MAX_PRICE} крышек')
    expire_sales(db)
    count = db.scalar(select(func.count(GearSale.id)).where(GearSale.seller_id == seller.id, GearSale.status == 'active')) or 0
    if count >= MAX_LISTINGS:
        raise ValueError('Одновременно можно продавать не более пяти предметов')
    item = db.scalar(select(GearItem).where(GearItem.id == gear_id, GearItem.player_id == seller.id).with_for_update())
    if not item:
        raise ValueError('Такого снаряжения нет в твоём арсенале')
    if item.equipped:
        raise ValueError('Сначала сними снаряжение, затем выставляй на продажу')
    item.player_id = ESCROW_OWNER
    sale = GearSale(gear_id=item.id, item_snapshot=gear_view(item), seller_id=seller.id, price=price, status='active',
                    expires_at=now() + LISTING_LIFETIME)
    db.add(sale)
    db.flush()
    return sale


def buy_gear(db: Session, buyer: Player, sale_id: int) -> tuple[GearSale, GearItem]:
    sale = db.scalar(select(GearSale).where(GearSale.id == sale_id).with_for_update())
    if not sale or sale.status != 'active':
        raise ValueError('Предмет уже продан или снят с продажи')
    if sale.seller_id == buyer.id:
        raise ValueError('Нельзя покупать собственное снаряжение')
    if aware(sale.expires_at) <= now():
        raise ValueError('Срок продажи истёк — вещь возвращается продавцу')
    if buyer.caps < sale.price:
        raise ValueError('Недостаточно крышек')
    owned = db.scalar(select(func.count(GearItem.id)).where(GearItem.player_id == buyer.id)) or 0
    if owned >= MAX_GEAR:
        raise ValueError('Арсенал заполнен: сначала освободи место')
    item = db.scalar(select(GearItem).where(GearItem.id == sale.gear_id).with_for_update())
    if not item or item.player_id != ESCROW_OWNER or item.equipped:
        raise ValueError('Предмет находится вне продажи. Обратись к администрации')
    seller = db.scalar(select(Player).where(Player.id == sale.seller_id).with_for_update())
    if not seller:
        raise ValueError('Продавец недоступен')
    fee = fee_for(sale.price)
    proceeds = sale.price - fee
    if seller.caps + proceeds > MAX_CAPS:
        raise ValueError('Баланс продавца достиг максимума')
    # All money and ownership changes occur in the caller's single transaction.
    buyer.caps -= sale.price
    seller.caps += proceeds
    item.player_id = buyer.id
    sale.fee = fee
    sale.buyer_id = buyer.id
    sale.status = 'sold'
    sale.closed_at = now()
    queue_notification(
        db, sale.seller_id, f'gear-sale:{sale.id}:sold',
        'market', 'gear_sale_sold',
        f'🪙 Снаряжение из лота #{sale.id} продано за {sale.price} крышек. '
        f'На баланс начислено {proceeds} крышек (комиссия {fee}).')
    return sale, item


def cancel_sale(db: Session, seller: Player, sale_id: int) -> GearSale:
    sale = db.scalar(select(GearSale).where(GearSale.id == sale_id).with_for_update())
    if not sale or sale.seller_id != seller.id:
        raise ValueError('Это не твой лот')
    if sale.status != 'active':
        raise ValueError('Лот уже закрыт')
    item = db.scalar(select(GearItem).where(GearItem.id == sale.gear_id).with_for_update())
    if not item or item.player_id != ESCROW_OWNER:
        raise ValueError('Экипировка недоступна для возврата')
    item.player_id = seller.id
    sale.status = 'cancelled'
    sale.closed_at = now()
    return sale


def sale_view(sale: GearSale, seller_name: str, player_id: int) -> dict:
    return {
        'id': sale.id, 'seller_id': sale.seller_id, 'seller_name': seller_name,
        'price': sale.price, 'fee': fee_for(sale.price), 'status': sale.status,
        'is_mine': sale.seller_id == player_id, 'gear': sale.item_snapshot,
        'created_at': aware(sale.created_at).isoformat(),
        'expires_at': aware(sale.expires_at).isoformat(),
        'closed_at': aware(sale.closed_at).isoformat() if sale.closed_at else None,
    }


def browse_sales(db: Session, player_id: int, page: int = 1) -> dict:
    expire_sales(db)
    page = max(1, min(40, page))
    active = (select(GearSale, Player.name)
              .join(Player, Player.id == GearSale.seller_id)
              .where(GearSale.status == 'active')
              .order_by(GearSale.created_at.desc(), GearSale.id.desc())
              .offset((page - 1) * 20).limit(21))
    rows = db.execute(active).all()
    mine = (select(GearSale, Player.name)
            .join(Player, Player.id == GearSale.seller_id)
            .where(GearSale.seller_id == player_id)
            .order_by(GearSale.created_at.desc(), GearSale.id.desc()).limit(30))
    owned = db.execute(mine).all()
    return {
        'items': [sale_view(s, name, player_id) for s, name in rows[:20]],
        'my_sales': [sale_view(s, name, player_id) for s, name in owned],
        'has_next': len(rows) > 20, 'page': page, 'commission_percent': FEE_PERCENT,
        'max_listings': MAX_LISTINGS, 'max_price': MAX_PRICE,
    }


class SellBody(BaseModel):
    gear_id: int = Field(gt=0, le=9223372036854775807)
    price: int = Field(ge=MIN_PRICE, le=MAX_PRICE)


class SaleId(BaseModel):
    id: int = Field(gt=0, le=9223372036854775807)


def install_gear_market(app, with_player, ready, identify_user=None):
    router = APIRouter(prefix='/api/gear-market', tags=['Gear Market'])

    def session():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    @router.get('')
    def browse(request: Request, page: int = 1, db: Session = Depends(session)):
        with db.begin():
            player = with_player(request, db)
            ready(player)
            return browse_sales(db, player.id, page)

    @router.post('/list')
    def sell(body: SellBody, request: Request, db: Session = Depends(session)):
        with db.begin():
            player = with_player(request, db)
            ready(player)
            sale = list_gear(db, player, body.gear_id, body.price)
            return {'message': f'Предмет выставлен за {sale.price} крышек на 7 дней', 'sale_id': sale.id}

    @router.post('/buy')
    def buy(body: SaleId, request: Request, db: Session = Depends(session)):
        with db.begin():
            if identify_user is not None:
                buyer_id=int(identify_user(request.headers.get('authorization',''))['id'])
                seller_id=db.scalar(select(GearSale.seller_id).where(GearSale.id==body.id))
                if seller_id is not None:
                    # Lock both wallets before the sale/item rows. Reciprocal
                    # purchases otherwise lock buyer A then seller B in reverse.
                    list(db.scalars(select(Player).where(Player.id.in_([buyer_id,seller_id]))
                                    .order_by(Player.id).with_for_update()))
            player = with_player(request, db)
            ready(player)
            sale, item = buy_gear(db, player, body.id)
            return {'message': f'Куплено: {gear_view(item)["name"]} +{item.level} за {sale.price} крышек',
                    'gear_id': item.id}

    @router.post('/cancel')
    def cancel(body: SaleId, request: Request, db: Session = Depends(session)):
        with db.begin():
            player = with_player(request, db)
            ready(player)
            sale = cancel_sale(db, player, body.id)
            return {'message': 'Лот снят с продажи, предмет вернулся в арсенал', 'sale_id': sale.id}

    app.include_router(router)
