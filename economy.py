"""Read-only economy flow diagnostics over committed ledger rows.

Never guesses lifetime issuance from post-release audit history. No live game
balance changes and no user-specific financial information exposed publicly.
"""
from datetime import timedelta
from sqlalchemy import case, func, select
from models import ResourceLedger, ClanTreasuryLedger, Player, Clan, now

def _flow(db, statement):
    rows=db.execute(statement).all()
    return [{'key':str(key),'inflow':int(inflow or 0),'outflow':int(outflow or 0),
             'net':int(inflow or 0)-int(outflow or 0),'operations':int(count or 0)}
            for key,inflow,outflow,count in rows]

def _rollup(model, key, cutoff):
    return (select(key,
        func.coalesce(func.sum(case((model.delta>0,model.delta),else_=0)),0),
        func.coalesce(func.sum(case((model.delta<0,-model.delta),else_=0)),0),
        func.count(model.id))
        .where(model.created_at>=cutoff).group_by(key).order_by(key))

def flow_report(db, days=7, *, at=None):
    """Aggregate wallet and clan movements, explicitly accounting for transfers.

    Source ledger starts from the first deployed release only. Net movement is
    NOT equal to printed currency (players can trade/donate and initial grants
    exist). A treasury-to-player transfer must be counted in both respective
    balances before deriving combined circulation.
    """
    if days not in (1,7,30,90):
        raise ValueError('Unsupported economy window')
    end=at or now()
    cutoff=end-timedelta(days=days)
    wallet=_flow(db,_rollup(ResourceLedger,
        ResourceLedger.kind+'|'+ResourceLedger.resource_key,cutoff))
    treasury=_flow(db,_rollup(ClanTreasuryLedger,
        ClanTreasuryLedger.clan_id,cutoff))
    def net(key):
        return next((row['net'] for row in wallet if row['key']==key),0)
    cap_wallets=db.scalar(select(func.coalesce(func.sum(Player.caps),0))) or 0
    clan_wallets=db.scalar(select(func.coalesce(func.sum(Clan.treasury),0))) or 0
    clan_delta=sum(x['net'] for x in treasury)
    first_seen=db.scalar(select(func.min(ResourceLedger.created_at)))
    last_seen=db.scalar(select(func.max(ResourceLedger.created_at)))
    return {
        'days':days, 'from':cutoff.isoformat(), 'to':end.isoformat(),
        'wallet_flows':wallet,'treasury_flows':treasury,
        'net_wallet_caps':net('currency|caps'),
        'net_clan_caps':clan_delta,
        'net_combined_caps':net('currency|caps')+clan_delta,
        'net_wallet_zombo':net('currency|zombo'),
        'net_xp':net('xp|lifetime'),
        'wallet_caps_now':int(cap_wallets),'treasury_caps_now':int(clan_wallets),
        'combined_caps_now':int(cap_wallets+clan_wallets),
        'ledger_first_seen':first_seen.isoformat() if first_seen else None,
        'ledger_last_seen':last_seen.isoformat() if last_seen else None,
        'warning': ('Журнал доступен только с даты его введения; net показывает '
                    'сумму наблюдаемых изменений, включая стартовые начисления, '
                    'сделки и переводы. Это не показатель чистой эмиссии.')
    }
