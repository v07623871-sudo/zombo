"""Server-side PvP Elo and protected daily match economy.

No new tables: the counters are persisted in Player.stats JSON inside the
same SQL transaction as the final PvP state and resource ledger entries.
"""
from datetime import datetime, timezone

DAILY_REWARDED_DUELS=5
ELO_K=32
LEAGUES=(
    (1850,'diamond','Алмазная'),
    (1550,'platinum','Платиновая'),
    (1300,'gold','Золотая'),
    (1100,'silver','Серебряная'),
    (0,'bronze','Бронзовая'),
)


def league(rating):
    rating=max(0,int(rating or 0))
    for minimum,key,name in LEAGUES:
        if rating>=minimum:
            return {'key':key,'name':name,'min_rating':minimum}


def elo_change(winner_rating,loser_rating):
    """Classic Elo K=32; symmetrical delta and 1 point minimum."""
    difference=max(-800,min(800,int(loser_rating)-int(winner_rating)))
    expected=1/(1+10**(difference/400))
    return max(1,round(ELO_K*(1-expected)))


def _daily_data(player,day):
    candidate=(player.stats or {}).get('_pvp_rewards')
    if not isinstance(candidate,dict) or candidate.get('day')!=day:
        return {'day':day,'count':0,'pairs':{}}
    pairs=candidate.get('pairs',{})
    if not isinstance(pairs,dict):
        pairs={}
    return {'day':day,'count':max(0,int(candidate.get('count',0))),
            'pairs':pairs}


def settle_rated_duel(winner,loser,at):
    """Mark both accounts; repeated pairs and 6th daily win don't mint value.

    Returns (rated, delta). A real PvP victory still increases lifetime
    win count outside this function; capped daily bonuses affect only
    the economy and competitive rating.
    """
    day=at.astimezone(timezone.utc).date().isoformat()
    win=_daily_data(winner,day)
    lose=_daily_data(loser,day)
    pair_used=(str(loser.id) in win['pairs']
               or str(winner.id) in lose['pairs'])
    # Require BOTH players to have a daily competitive slot. This prevents
    # boosted alts from repeatedly donating rating to one account.
    if pair_used or win['count']>=DAILY_REWARDED_DUELS or lose['count']>=DAILY_REWARDED_DUELS:
        return False,0
    delta=elo_change(winner.rating,loser.rating)
    actual_loss=min(max(0,loser.rating),delta)
    winner.rating+=actual_loss
    loser.rating-=actual_loss
    win['pairs'][str(loser.id)]=1
    lose['pairs'][str(winner.id)]=1
    win['count']+=1
    lose['count']+=1
    winner.stats={**(winner.stats or {}),'_pvp_rewards':win}
    loser.stats={**(loser.stats or {}),'_pvp_rewards':lose}
    return True,actual_loss


def daily_remaining(player,at):
    day=at.astimezone(timezone.utc).date().isoformat()
    return max(0,DAILY_REWARDED_DUELS-_daily_data(player,day)['count'])
