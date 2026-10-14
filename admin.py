"""Authenticated admin API. Every mutation is audited in the same DB transaction."""
from uuid import UUID
from typing import Literal
from collections import defaultdict
from datetime import timedelta
from io import StringIO
import csv
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, func, or_, select
from sqlalchemy.orm import Session

from models import (Base, SessionLocal, Player, ItemStack, Clan, Battle, MarketLot, ResourceLedger, ClanTreasuryLedger, tag_resource_operation,
                    PvPMatch, Payment, PaymentReview, TerritoryWar, now)
from gear import GearItem, gear_view
from gear_market import GearSale
from raids import RaidRun, RaidMember
from expeditions import ExpeditionRun
from notifications import NotificationOutbox, CATEGORIES
from story import StoryProgress
from game import ITEMS, gain_xp, give_item, item_count, take_item, pet_status
from admin_grants import gift_catalog, grant_to_player


class AdminAudit(Base):
    __tablename__ = 'admin_audit'
    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(36), nullable=False, unique=True)
    actor_id = Column(BigInteger, nullable=False, index=True)
    target_id = Column(BigInteger, ForeignKey('players.id'), nullable=False, index=True)
    action = Column(String(24), nullable=False)
    field = Column(String(60), nullable=False)
    before = Column(String(40), nullable=False)
    after = Column(String(40), nullable=False)
    reason = Column(String(300), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)


class StatusChange(BaseModel):
    field: str = Field(pattern=r'^(banned|frozen)$')
    value: bool
    reason: str = Field(min_length=5, max_length=300)
    request_id: UUID


class GrantChange(BaseModel):
    kind: Literal['currency','item','gear','pet','premium']
    key: str = Field(min_length=1, max_length=55)
    amount: int = Field(default=1, ge=1, le=1000000)
    rarity: str = 'common'
    level: int = Field(default=0, ge=0, le=10)
    reason: str = Field(min_length=5, max_length=300)
    request_id: UUID


class ResourceChange(BaseModel):
    field: Literal['caps','xp','material']
    item_key: str | None = Field(default=None, max_length=55)
    amount: int = Field(ge=-100000, le=100000)
    reason: str = Field(min_length=5, max_length=300)
    request_id: UUID


def install_admin(app, identify, admin_ids):
    router = APIRouter(prefix='/api/admin', tags=['Admin'])

    def session():
        with SessionLocal() as db:
            yield db

    def actor(request: Request, db: Session) -> Player:
        tag_resource_operation(db, f'{request.method}:{request.url.path}')
        pid = int(identify(request.headers.get('authorization', ''))['id'])
        if pid not in admin_ids:
            raise HTTPException(403, 'Только администратор')
        user = db.get(Player, pid)
        if not user or user.banned or user.frozen:
            raise HTTPException(403, 'Учётная запись администратора недоступна')
        return user

    def target(db: Session, pid: int) -> Player:
        if not 0 < pid <= 9223372036854775807:
            raise HTTPException(422, 'Неверный ID игрока')
        player = db.scalar(select(Player).where(Player.id == pid).with_for_update())
        if not player:
            raise HTTPException(404, 'Игрок не найден')
        return player

    def prior(db: Session, uid: UUID):
        log = db.scalar(select(AdminAudit).where(AdminAudit.request_id == str(uid)))
        if log:
            return {'message': 'Операция уже выполнена', 'audit_id': log.id,
                    'before': log.before, 'after': log.after, 'replayed': True}
        return None

    def log_change(db, uid, admin, player, action, field, before, after, reason):
        log = AdminAudit(request_id=str(uid), actor_id=admin.id, target_id=player.id,
                         action=action, field=field, before=str(before), after=str(after), reason=reason.strip())
        db.add(log)
        db.flush()
        return {'message': 'Изменение сохранено в журнале', 'audit_id': log.id,
                'before': log.before, 'after': log.after, 'replayed': False}

    @router.get('/access')
    def access(request: Request, db: Session = Depends(session)):
        return {'admin': True, 'id': actor(request, db).id}

    @router.get('/grant-catalog')
    def admin_catalog(request: Request, db: Session = Depends(session)):
        actor(request, db)
        return gift_catalog()

    @router.post('/players/{pid}/grant')
    def grant_everything(pid: int, body: GrantChange, request: Request,
                         db: Session = Depends(session)):
        """Issue every gameplay asset; audit and grant commit atomically."""
        with db.begin():
            admin=actor(request,db)
            if len(body.reason.strip())<5:
                raise HTTPException(422,'Укажи причину выдачи')
            player=target(db,pid)
            previous=prior(db,body.request_id)
            if previous:return previous
            tag_resource_operation(db,f'admin-grant:{body.request_id}',stable=True)
            result=grant_to_player(db,player,kind=body.kind,key=body.key,
                                   amount=body.amount,rarity=body.rarity,
                                   level=body.level)
            audit=log_change(db,body.request_id,admin,player,'grant',
                             result['field'],result['before'],result['after'],
                             body.reason)
            audit['message']=f'Выдано игроку #{pid}: {body.key} ×{body.amount}'
            if 'gear_ids' in result:audit['gear_ids']=result['gear_ids']
            return audit

    @router.get('/summary')
    def summary(request: Request, db: Session = Depends(session)):
        actor(request, db)
        count = lambda model: db.scalar(select(func.count()).select_from(model)) or 0
        return {
            'players': count(Player), 'active_7d': db.scalar(select(func.count()).select_from(Player).where(Player.last_tick >= now() - timedelta(days=7))) or 0,
            'zombie_kills': db.scalar(select(func.coalesce(func.sum(Player.kills), 0))) or 0,
            'pvp_matches': count(PvPMatch), 'raids': count(RaidRun),
            'wars': count(TerritoryWar), 'clans': count(Clan),
            'barter_active': db.scalar(select(func.count()).select_from(MarketLot).where(MarketLot.active.is_(True))) or 0,
            'gear_sales': count(GearSale), 'gear_sold': db.scalar(select(func.count()).select_from(GearSale).where(GearSale.status == 'sold')) or 0,
            'payments': count(Payment), 'stars_received': db.scalar(select(func.coalesce(func.sum(Payment.stars), 0))) or 0,
            'payments_for_review': count(PaymentReview),
            'caps_in_wallets': db.scalar(select(func.coalesce(func.sum(Player.caps), 0))) or 0,
            'zombo_in_wallets': db.scalar(select(func.coalesce(func.sum(Player.zombo), 0))) or 0,
        }

    @router.get('/operations')
    def operations(request: Request, db: Session = Depends(session)):
        """Bounded support counters; no message bodies or payment secrets."""
        actor(request, db)
        instant = now()
        count = lambda model, *conditions: db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0
        oldest = db.scalar(select(func.min(NotificationOutbox.scheduled_at)).where(
            NotificationOutbox.status == 'pending', NotificationOutbox.scheduled_at <= instant))
        return {
            'raids_lobby': count(RaidRun, RaidRun.status == 'lobby'),
            'raids_active': count(RaidRun, RaidRun.status == 'active'),
            'raids_overdue': count(RaidRun, RaidRun.status == 'active', RaidRun.expires_at < instant),
            'expeditions_active': count(ExpeditionRun, ExpeditionRun.status == 'active'),
            'expeditions_overdue': count(ExpeditionRun, ExpeditionRun.status == 'active', ExpeditionRun.finishes_at < instant),
            'notifications_pending': count(NotificationOutbox, NotificationOutbox.status == 'pending'),
            'notifications_due': count(NotificationOutbox, NotificationOutbox.status == 'pending', NotificationOutbox.scheduled_at <= instant),
            'notifications_sending': count(NotificationOutbox, NotificationOutbox.status == 'sending'),
            'notifications_stuck': count(NotificationOutbox, NotificationOutbox.status == 'sending', NotificationOutbox.lease_until < instant),
            'notifications_failed_24h': count(NotificationOutbox, NotificationOutbox.status == 'failed', NotificationOutbox.finished_at >= instant - timedelta(days=1)),
            'oldest_due_at': oldest.isoformat() if oldest else None,
            'payment_reviews': count(PaymentReview),
            'checked_at': instant.isoformat(),
        }

    @router.get('/notifications')
    def notification_log(request: Request, status: str = '', category: str = '',
                         player_id: int | None = None, page: int = 1,
                         db: Session = Depends(session)):
        actor(request, db)
        if status and status not in ('pending', 'sending', 'sent', 'skipped', 'failed'):
            raise HTTPException(422, 'Неизвестный статус доставки')
        if category and category not in CATEGORIES:
            raise HTTPException(422, 'Неизвестная категория уведомлений')
        if player_id is not None and not 0 < player_id <= 9223372036854775807:
            raise HTTPException(422, 'Неверный ID игрока')
        page = max(1, min(500, page))
        query = select(NotificationOutbox)
        if status: query = query.where(NotificationOutbox.status == status)
        if category: query = query.where(NotificationOutbox.category == category)
        if player_id is not None: query = query.where(NotificationOutbox.player_id == player_id)
        rows = db.scalars(query.order_by(NotificationOutbox.id.desc())
                          .offset((page - 1) * 30).limit(31)).all()
        return {'page': page, 'has_next': len(rows) > 30,
                'items': [{'id': row.id, 'player_id': row.player_id,
                           'category': row.category, 'kind': row.kind,
                           'status': row.status, 'attempts': row.attempts,
                           'scheduled_at': row.scheduled_at.isoformat(),
                           'finished_at': row.finished_at.isoformat() if row.finished_at else None,
                           'last_error': row.last_error} for row in rows[:30]]}

    @router.get('/players')
    def players(request: Request, q: str = '', hero_class: str = '', min_level: int = 1,
                page: int = 1, db: Session = Depends(session)):
        actor(request, db)
        page = max(1, min(500, page))
        query = select(Player).where(Player.level >= max(1, min(1000, min_level)))
        if hero_class:
            query = query.where(Player.hero_class == hero_class)
        q = q.strip()[:90]
        if q:
            if q.isdigit() and int(q) <= 9223372036854775807:
                query = query.where(or_(Player.id == int(q), Player.name.ilike(f'%{q}%'), Player.username.ilike(f'%{q}%')))
            else:
                query = query.where(or_(Player.name.ilike(f'%{q}%'), Player.username.ilike(f'%{q}%')))
        rows = db.scalars(query.order_by(Player.id.desc()).offset((page - 1) * 20).limit(21)).all()
        return {'page': page, 'has_next': len(rows) > 20,
                'items': [{'id': p.id, 'name': p.name, 'username': p.username, 'class': p.hero_class,
                           'level': p.level, 'caps': p.caps, 'banned': p.banned, 'frozen': p.frozen}
                          for p in rows[:20]]}

    @router.get('/players/{pid}')
    def player_detail(pid: int, request: Request, db: Session = Depends(session)):
        actor(request, db)
        if not 0 < pid <= 9223372036854775807:
            raise HTTPException(422, 'Неверный ID игрока')
        p = db.get(Player, pid)
        if not p:
            raise HTTPException(404, 'Игрок не найден')
        clan = db.get(Clan, p.clan_id) if p.clan_id else None
        gear = db.scalars(select(GearItem).where(GearItem.player_id == pid).order_by(GearItem.id).limit(100)).all()
        stacks = db.scalars(select(ItemStack).where(ItemStack.player_id == pid, ItemStack.quantity > 0).order_by(ItemStack.item_key)).all()
        story = db.get(StoryProgress, pid)
        return {'id': p.id, 'name': p.name, 'username': p.username, 'class': p.hero_class,
                'level': p.level, 'xp': p.xp, 'caps': p.caps, 'zombo': p.zombo,
                'hp': p.hp, 'stamina': p.stamina, 'kills': p.kills, 'rating': p.rating,
                'karma': p.karma, 'banned': p.banned, 'frozen': p.frozen,
                'clan': clan.name if clan else None, 'location': p.location,
                'story_chapter': story.chapter if story else 0,
                 'pet': pet_status(p),
                 'vip_until': p.vip_until.isoformat() if p.vip_until else None,
                'gear': [gear_view(item) for item in gear],
                'inventory': [{'key': i.item_key, 'quantity': i.quantity, 'equipped': i.equipped} for i in stacks]}

    @router.post('/players/{pid}/status')
    def change_status(pid: int, body: StatusChange, request: Request, db: Session = Depends(session)):
        with db.begin():
            admin = actor(request, db)
            if len(body.reason.strip()) < 5:
                raise HTTPException(422, 'Укажи содержательную причину')
            p = target(db, pid)
            existing = prior(db, body.request_id)
            if existing:
                return existing
            if body.value and p.id in admin_ids:
                active = db.scalar(select(func.count()).select_from(Player).where(
                    Player.id.in_(admin_ids), Player.banned.is_(False), Player.frozen.is_(False))) or 0
                if active <= 1:
                    raise HTTPException(409, 'Нельзя заблокировать последнего администратора')
            old = bool(getattr(p, body.field))
            if old == body.value:
                raise HTTPException(409, 'Статус уже установлен')
            setattr(p, body.field, body.value)
            return log_change(db, body.request_id, admin, p, 'moderation', body.field,
                              int(old), int(body.value), body.reason)

    @router.post('/players/{pid}/resources')
    def change_resources(pid: int, body: ResourceChange, request: Request, db: Session = Depends(session)):
        with db.begin():
            admin = actor(request, db)
            if len(body.reason.strip()) < 5:
                raise HTTPException(422, 'Укажи содержательную причину')
            p = target(db, pid)
            existing = prior(db, body.request_id)
            if existing:
                return existing
            if body.amount == 0:
                raise HTTPException(400, 'Количество должно быть ненулевым')
            tag_resource_operation(db, f'admin-resource:{body.request_id}', stable=True)
            if body.field == 'material':
                key = body.item_key or ''
                if key not in ITEMS or ITEMS[key].get('type') not in ('material', 'resource'):
                    raise HTTPException(400, 'Разрешены только материалы')
                before = item_count(db, pid, key)
                if before + body.amount < 0 or before + body.amount > 1000000:
                    raise HTTPException(400, 'Количество вне допустимого диапазона')
                if body.amount > 0:
                    give_item(db, pid, key, body.amount)
                else:
                    take_item(db, pid, key, -body.amount)
                after = before + body.amount
                field = f'material:{key}'
            elif body.field == 'caps':
                before = p.caps
                after = before + body.amount
                if not 0 <= after <= 2_000_000_000:
                    raise HTTPException(400, 'Баланс вне допустимого диапазона')
                p.caps = after
                field = 'caps'
            else:
                if body.amount < 0:
                    raise HTTPException(400, 'Списание XP запрещено: уровень не пересчитывается назад')
                before = f'LVL {p.level}, XP {p.xp}'
                gain_xp(p, body.amount)
                after = f'LVL {p.level}, XP {p.xp}'
                field = 'xp'
            return log_change(db, body.request_id, admin, p, 'resource', field,
                              before, after, body.reason)

    @router.get('/audit')
    def audit(request: Request, page: int = 1, db: Session = Depends(session)):
        actor(request, db)
        page = max(1, min(500, page))
        logs = db.scalars(select(AdminAudit).order_by(AdminAudit.id.desc()).offset((page - 1) * 30).limit(31)).all()
        return {'page': page, 'has_next': len(logs) > 30,
                'items': [{'id': x.id, 'actor_id': x.actor_id, 'target_id': x.target_id,
                           'action': x.action, 'field': x.field, 'before': x.before,
                           'after': x.after, 'reason': x.reason, 'created_at': x.created_at.isoformat()}
                          for x in logs[:30]]}

    @router.get('/audit/export')
    def export_audit(request: Request, limit: int = 1000, db: Session = Depends(session)):
        """Export a bounded, authenticated UTF-8 audit CSV; no public download URL."""
        actor(request, db)
        limit = max(1, min(limit, 5000))
        rows = db.scalars(select(AdminAudit).order_by(AdminAudit.id.desc()).limit(limit)).all()
        output = StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow(('id','created_at','actor_id','target_id','action','field',
                         'before','after','reason'))

        def safe(value):
            # CSV values are opened as spreadsheet cells; neutralize formulas,
            # including fields beginning with leading whitespace.
            raw = str(value if value is not None else '')
            if raw.lstrip(' \t\r\n').startswith(('=', '+', '-', '@')):
                return "'" + raw
            return raw

        for log in rows:
            writer.writerow([safe(value) for value in
                            (log.id, log.created_at.isoformat(), log.actor_id,
                             log.target_id, log.action, log.field, log.before,
                             log.after, log.reason)])
        data = '\ufeff' + output.getvalue()
        return Response(content=data, media_type='text/csv; charset=utf-8',
                        headers={'Content-Disposition': 'attachment; filename="zombo-admin-audit.csv"',
                                 'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})

    @router.get('/risk')
    def risk_report(request: Request, db: Session = Depends(session)):
        """Read-only signals for a human to review, never an automatic ban."""
        actor(request, db)
        instant = now()
        cutoff = instant - timedelta(days=7)
        sales = db.scalars(select(GearSale).where(
            GearSale.status == 'sold', GearSale.closed_at >= cutoff,
            GearSale.buyer_id.is_not(None))
            .order_by(GearSale.id.desc()).limit(500)).all()
        reviews = db.scalars(select(PaymentReview)
            .order_by(PaymentReview.created_at.desc()).limit(30)).all()
        changes = db.scalars(select(AdminAudit).where(
            AdminAudit.field == 'caps', AdminAudit.created_at >= cutoff)
            .order_by(AdminAudit.id.desc()).limit(500)).all()

        findings = []
        pairs = defaultdict(list)
        for sale in sales:
            if sale.seller_id == sale.buyer_id:
                findings.append({'type':'self_trade','severity':'high',
                    'title':'Продавец совпадает с покупателем',
                    'description':f'Сделка #{sale.id} на {sale.price} крышек.',
                    'player_id':sale.seller_id, 'related_player_id':sale.buyer_id,
                    'reference_id':sale.id, 'created_at':sale.closed_at.isoformat()})
            if sale.price >= 150000:
                findings.append({'type':'large_sale','severity':'medium',
                    'title':'Крупная сделка с экипировкой',
                    'description':f'Лот #{sale.id}: {sale.price} крышек. Проверь контекст продажи.',
                    'player_id':sale.seller_id, 'related_player_id':sale.buyer_id,
                    'reference_id':sale.id, 'created_at':sale.closed_at.isoformat()})
            pair = tuple(sorted((sale.seller_id, sale.buyer_id)))
            pairs[pair].append(sale)
        for pair, deals in pairs.items():
            if len(deals) >= 4:
                last = max(deals, key=lambda x: x.id)
                findings.append({'type':'repeated_trades','severity':'medium',
                    'title':'Повторяющиеся сделки между двумя игроками',
                    'description':f'{len(deals)} закрытых сделок за 7 дней (из 500 последних).',
                    'player_id':pair[0], 'related_player_id':pair[1],
                    'reference_id':last.id, 'created_at':last.closed_at.isoformat()})

        for entry in reviews:
            findings.append({'type':'payment_review','severity':'high',
                'title':'Платёж Telegram требует сверки',
                'description':f'{entry.amount} {entry.currency}: {entry.reason}. Не зачислять без сверки.',
                'player_id':entry.player_id, 'related_player_id':None,
                'reference_id':None, 'created_at':entry.created_at.isoformat()})

        for log in changes:
            try:
                difference = int(log.after) - int(log.before)
            except (TypeError, ValueError):
                continue
            if abs(difference) >= 50000:
                findings.append({'type':'large_admin_adjustment','severity':'medium',
                    'title':'Крупное изменение крышек администратором',
                    'description':f'Журнал #{log.id}: {difference:+d} крышек, админ #{log.actor_id}.',
                    'player_id':log.target_id, 'related_player_id':None,
                    'reference_id':log.id, 'created_at':log.created_at.isoformat()})

        findings.sort(key=lambda f: f['created_at'], reverse=True)
        return {'window_days':7, 'transactions_examined':len(sales),
                'limited_to_latest_transactions':500, 'total_findings':len(findings),
                'findings':findings[:100], 'disclaimer':'Сигналы для ручной проверки, не доказательства нарушений.'}

    @router.get('/transactions')
    def transactions(request: Request, db: Session = Depends(session)):
        actor(request, db)
        sales = db.scalars(select(GearSale).order_by(GearSale.id.desc()).limit(30)).all()
        payments = db.scalars(select(Payment).order_by(Payment.created_at.desc()).limit(30)).all()
        reviews = db.scalars(select(PaymentReview).order_by(PaymentReview.created_at.desc()).limit(30)).all()
        raids = db.scalars(select(RaidMember).where(RaidMember.rewarded.is_(True)).order_by(RaidMember.id.desc()).limit(30)).all()
        return {'sales': [{'id': s.id, 'seller_id': s.seller_id, 'buyer_id': s.buyer_id,
                           'price': s.price, 'fee': s.fee, 'status': s.status} for s in sales],
                'payments': [{'player_id': p.player_id, 'stars': p.stars, 'zombo': p.zombo,
                              'created_at': p.created_at.isoformat()} for p in payments],
                'payment_reviews': [{'charge_id': p.charge_id, 'player_id': p.player_id,
                                     'currency': p.currency, 'amount': p.amount, 'reason': p.reason,
                                     'created_at': p.created_at.isoformat()} for p in reviews],
                'raid_rewards': [{'run_id': r.run_id, 'player_id': r.player_id,
                                  'contribution': r.contribution} for r in raids]}

    @router.get('/ledger')
    def resource_ledger(request: Request, player_id: int | None = Query(default=None, ge=1, le=9223372036854775807),
                        kind: str | None = Query(default=None, pattern=r'^(currency|item|gear|xp)$'),
                        page: int = Query(default=1, ge=1, le=1000),
                        db: Session = Depends(session)):
        actor(request, db)
        statement = select(ResourceLedger)
        if player_id is not None:
            statement = statement.where(ResourceLedger.player_id == player_id)
        if kind:
            statement = statement.where(ResourceLedger.kind == kind)
        rows = db.scalars(statement.order_by(ResourceLedger.id.desc())
                          .offset((page - 1) * 50).limit(51)).all()
        return {'items': [{'id': row.id, 'source_event': row.source_event,
                           'player_id': row.player_id, 'kind': row.kind,
                           'resource_key': row.resource_key, 'delta': row.delta,
                           'balance_after': row.balance_after,
                           'created_at': row.created_at.isoformat()} for row in rows[:50]],
                'page': page, 'has_next': len(rows) > 50}

    @router.get('/economy/flows')
    def economy_flows(request: Request,
                      days: int = Query(default=7, ge=1, le=90),
                      db: Session = Depends(session)):
        """Read-only period report; never returns private payments or player rows."""
        actor(request, db)
        from economy import flow_report
        if days not in (1, 7, 30, 90):
            raise HTTPException(422, 'Выбери период: 1, 7, 30 или 90 дней')
        return flow_report(db, days)

    @router.get('/treasury-ledger')
    def treasury_ledger(request: Request,
                        clan_id: int | None = Query(default=None, ge=1, le=2147483647),
                        page: int = Query(default=1, ge=1, le=1000),
                        db: Session = Depends(session)):
        """Admin-only chronological treasury changes; no player-ID conflation."""
        actor(request, db)
        statement = select(ClanTreasuryLedger)
        if clan_id is not None:
            statement = statement.where(ClanTreasuryLedger.clan_id == clan_id)
        rows = db.scalars(statement.order_by(ClanTreasuryLedger.id.desc())
                          .offset((page - 1) * 50).limit(51)).all()
        return {'items': [{'id': row.id, 'clan_id': row.clan_id,
                           'source_event': row.source_event, 'delta': row.delta,
                           'balance_after': row.balance_after,
                           'created_at': row.created_at.isoformat()}
                          for row in rows[:50]],
                'page': page, 'has_next': len(rows) > 50}

    app.include_router(router)
