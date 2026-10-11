"""Persistent, multi-worker safe controls for Telegram updates and API abuse.

All reservations and counters are stored in the game's existing database.
The PostgreSQL/SQLite UPSERT is atomic and works with multiple app workers.
No player progress or wallet fields are changed here.
"""
import secrets
from sqlalchemy import BigInteger, Column, Integer, String, select, delete, text
from sqlalchemy.orm import Session
from models import Base, now


class ApiQuota(Base):
    __tablename__ = 'api_quotas'
    player_id = Column(BigInteger, primary_key=True)
    scope = Column(String(12), primary_key=True)
    window = Column(BigInteger, nullable=False)
    count = Column(Integer, nullable=False, default=0)


class TelegramReceipt(Base):
    __tablename__ = 'telegram_receipts'
    update_id = Column(BigInteger, primary_key=True)
    state = Column(String(16), nullable=False, default='processing')
    touched_at = Column(Integer, nullable=False)
    lease = Column(String(32), nullable=False)


class TooManyActions(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__('Слишком много действий. Подожди немного.')


def enforce_quota(db: Session, player_id: int, scope: str, *, limit: int, timestamp: int | None = None):
    """Charge one request using an atomic UPSERT, including on first use.

    Use the user's authenticated Telegram ID, not a client-controlled header.
    No counting based on in-memory state: Railway horizontal workers agree.
    """
    if not 0 < int(player_id) <= 9223372036854775807:
        raise ValueError('Неверный идентификатор игрока')
    if scope not in ('write', 'economy'):
        raise ValueError('Неверная область ограничения')
    timestamp = int(now().timestamp()) if timestamp is None else int(timestamp)
    window = timestamp // 60
    result = db.execute(text('''
        INSERT INTO api_quotas (player_id, scope, "window", count)
        VALUES (:player_id, :scope, :window, 1)
        ON CONFLICT (player_id, scope) DO UPDATE SET
            count = CASE WHEN api_quotas."window" = :window
                THEN api_quotas.count + 1 ELSE 1 END,
            "window" = :window
        RETURNING count
    '''), {'player_id': int(player_id), 'scope': scope, 'window': window})
    count = result.scalar_one()
    if count > limit:
        # The transaction rolls back on rejection; gameplay never runs.
        raise TooManyActions(60 - (timestamp % 60))
    return count


def claim_update(db: Session, update_id: int, *, timestamp: int | None = None):
    """Try to claim a Telegram update. Returns 'claimed', 'duplicate', or 'busy'.

    Busy updates must receive HTTP 503 so Telegram retries, not an OK ACK.
    A 5-minute stale lease allows recovery if a Railway worker dies mid-update.
    """
    timestamp = int(now().timestamp()) if timestamp is None else int(timestamp)
    if type(update_id) is not int or not 0 <= update_id <= 9223372036854775807:
        raise ValueError('Некорректный update_id Telegram')
    lease = secrets.token_hex(16)
    status = db.execute(text('''
        INSERT INTO telegram_receipts (update_id, state, touched_at, lease)
        VALUES (:id, 'processing', :timestamp, :lease)
        ON CONFLICT (update_id) DO UPDATE SET
            state = CASE
                WHEN telegram_receipts.state='processing'
                    AND telegram_receipts.touched_at < :stale
                THEN 'processing' ELSE telegram_receipts.state END,
            touched_at = CASE
                WHEN telegram_receipts.state='processing'
                    AND telegram_receipts.touched_at < :stale
                THEN :timestamp ELSE telegram_receipts.touched_at END,
            lease = CASE
                WHEN telegram_receipts.state='processing'
                    AND telegram_receipts.touched_at < :stale
                THEN :lease ELSE telegram_receipts.lease END
        RETURNING state, lease
    '''), {'id': update_id, 'timestamp': timestamp, 'stale': timestamp - 300, 'lease':lease}).one()
    if status.state == 'done':
        return ('duplicate', None)
    if status.lease != lease:
        return ('busy', None)
    return ('claimed', lease)


def finish_update(db: Session, update_id: int, *, completed: bool, lease: str):
    """On exception release the claim; on success record an immutable receipt."""
    receipt = db.get(TelegramReceipt, update_id, with_for_update=True)
    if not receipt or receipt.lease != lease:
        return
    if completed:
        receipt.state = 'done'
        receipt.touched_at = int(now().timestamp())
    else:
        db.delete(receipt)


def prune_update_receipts(db: Session, *, timestamp: int | None = None):
    timestamp = int(now().timestamp()) if timestamp is None else int(timestamp)
    # Only remove completed receipts; stale in-flight update IDs remain recoverable.
    db.execute(delete(TelegramReceipt).where(
        TelegramReceipt.state == 'done', TelegramReceipt.touched_at < timestamp - 7 * 86400
    ))
