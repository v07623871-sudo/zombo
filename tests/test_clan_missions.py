from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from models import Base, Player, Clan
from clan_missions import (ClanMission, ClanMissionMember, ClanRenown, ClanSeasonScore,
    ClanSeasonContribution, ClanSeasonResult, ClanSeasonRewardClaim, TASKS,
    record_clan_progress, board, claim_clan_reward, claim_season_reward,
    settle_seasons, week_key, next_week)
from notifications import NotificationCategoryOptIn, NotificationOutbox, _eligible

NOW=datetime(2026,10,11,13,tzinfo=timezone.utc)

@pytest.fixture
def db(monkeypatch):
    db_engine=create_engine('sqlite:///:memory:')
    Base.metadata.create_all(db_engine)
    with Session(db_engine, expire_on_commit=False) as session:
        session.add_all([Clan(id=50,name='Lohi',leader_id=101,treasury=100,level=1),
            Player(id=101,name='Tester',hero_class='soldier',clan_id=50,caps=20,level=4),
            Player(id=102,name='Member',hero_class='medic',clan_id=50,caps=90,level=4),
            Player(id=103,name='Wanderer',hero_class='thief',caps=20,level=4)])
        session.commit()
        yield session
    db_engine.dispose()


def test_week_rollover_and_calendar():
    assert week_key(NOW)=='2026-W41'
    assert week_key(NOW+timedelta(days=1))=='2026-W42'
    assert next_week(NOW)=='2026-10-12T00:00:00+00:00'


def test_no_clan_never_contributes(db):
    record_clan_progress(db,103,'kills',100,at=NOW)
    assert db.scalar(select(ClanMission)) is None
    assert board(db,db.get(Player,103),at=NOW)['missions']==[]


def test_collective_completion_credits_treasury_exactly_once(db):
    start=db.get(Clan,50).treasury
    record_clan_progress(db,101,'kills',20,at=NOW)
    record_clan_progress(db,102,'kills',5,at=NOW)
    record_clan_progress(db,101,'kills',100,at=NOW)
    db.flush()
    mission=db.scalar(select(ClanMission).where(ClanMission.code=='kills'))
    assert mission.amount==25 and mission.completed_at
    assert db.get(Clan,50).treasury==start+TASKS['kills']['treasury']
    assert db.get(ClanRenown,50).xp==TASKS['kills']['renown']
    assert db.get(ClanSeasonScore,(50,'2026-10')).completed==1
    assert board(db,db.get(Player,101),at=NOW)['missions'][0]['mine']==120


def test_claim_exactly_once_and_member_minimum(db,monkeypatch):
    import game
    monkeypatch.setattr(game,'gain_xp',lambda player,amount:setattr(player,'xp',(player.xp or 0)+amount))
    record_clan_progress(db,101,'kills',23,at=NOW)
    record_clan_progress(db,102,'kills',2,at=NOW)
    with pytest.raises(ValueError,match='Недостаточный'):
        claim_clan_reward(db,db.get(Player,102),'kills',at=NOW)
    got=claim_clan_reward(db,db.get(Player,101),'kills',at=NOW)
    assert got['caps']==35 and got['xp']==55
    assert db.get(Player,101).caps==55
    with pytest.raises(ValueError,match='уже получена'):
        claim_clan_reward(db,db.get(Player,101),'kills',at=NOW)
    assert db.get(Player,101).caps==55


def test_new_week_new_goals_and_mission_paid_once(db):
    tomorrow=NOW+timedelta(days=1)
    record_clan_progress(db,101,'scavenge',35,at=NOW)
    record_clan_progress(db,101,'scavenge',35,at=tomorrow)
    db.flush()
    assert db.scalar(select(ClanSeasonScore).where(ClanSeasonScore.clan_id==50)).completed==2
    assert len(db.scalars(select(ClanMission)).all())==2
    assert board(db,db.get(Player,101),at=tomorrow)['missions'][1]['mine']==35


def test_nonexistent_and_early_claim(db):
    p=db.get(Player,101)
    for code in ('kills','scavenge'):
        with pytest.raises(ValueError):claim_clan_reward(db,p,code,at=NOW)
    with pytest.raises(ValueError,match='Неизвестное'):
        claim_clan_reward(db,p,'other',at=NOW)


def test_season_ranking_and_level(db):
    for code,task in TASKS.items():
        record_clan_progress(db,101,code,task['target'],at=NOW)
    db.flush()
    v=board(db,db.get(Player,101),at=NOW)
    assert v['season_points']==sum(x['renown'] for x in TASKS.values())
    assert v['clan_level']>=2
    assert v['ranking'][0]['name']=='Lohi'
    assert len(v['missions'])==3 and all(x['completed'] for x in v['missions'])


def test_season_snapshot_reward_and_idempotency(db):
    next_month=datetime(2026,11,1,1,5,tzinfo=timezone.utc)
    record_clan_progress(db,101,'kills',20,at=NOW)
    record_clan_progress(db,102,'kills',5,at=NOW)
    assert db.get(ClanSeasonContribution,('2026-10',50,101)).amount==20
    settle_seasons(db,datetime(2026,11,1,0,30,tzinfo=timezone.utc))
    assert db.get(ClanSeasonResult,('2026-10',50)) is None
    with pytest.raises(ValueError,match='01:00'):
        claim_season_reward(db,db.get(Player,101),at=datetime(2026,11,1,0,30,tzinfo=timezone.utc))
    settle_seasons(db,next_month)
    result=db.get(ClanSeasonResult,('2026-10',50))
    assert result.place==1 and result.points==TASKS['kills']['renown']
    assert result.clan_name=='Lohi'
    # A retry of the settlement cannot change the closed result.
    db.get(ClanSeasonScore,(50,'2026-10')).points+=999
    settle_seasons(db,next_month+timedelta(minutes=1))
    assert db.get(ClanSeasonResult,('2026-10',50)).points==TASKS['kills']['renown']
    view=board(db,db.get(Player,101),at=next_month)
    assert view['season_reward']['can_claim']
    assert view['season_history'][0]['name']=='Lohi'
    with pytest.raises(ValueError,match='Недостаточный'):
        claim_season_reward(db,db.get(Player,102),at=next_month)
    initial=db.get(Player,101).caps
    award=claim_season_reward(db,db.get(Player,101),at=next_month)
    assert award['caps']==120 and db.get(Player,101).caps==initial+120
    assert db.get(ClanSeasonRewardClaim,('2026-10',101)).caps==120
    with pytest.raises(ValueError,match='уже получена'):
        claim_season_reward(db,db.get(Player,101),at=next_month)
    assert board(db,db.get(Player,101),at=next_month)['season_reward']['claimed']


def test_season_reward_requires_current_clan_membership(db):
    record_clan_progress(db,101,'scavenge',35,at=NOW)
    after=datetime(2026,11,1,1,5,tzinfo=timezone.utc)
    settle_seasons(db,after)
    db.get(Player,101).clan_id=None
    with pytest.raises(ValueError,match='состоять'):
        claim_season_reward(db,db.get(Player,101),at=after)
    assert db.get(ClanSeasonRewardClaim,('2026-10',101)) is None


def test_weekly_reset_signal_is_unique_and_stale_after_week(db):
    db.add(NotificationCategoryOptIn(player_id=101,category='clans'))
    db.flush()
    record_clan_progress(db,101,'kills',1,at=NOW)
    record_clan_progress(db,101,'kills',1,at=NOW)
    db.flush()
    rows=db.scalars(select(NotificationOutbox).where(
        NotificationOutbox.kind=='weekly_reset')).all()
    assert len(rows)==1
    assert not _eligible(db,rows[0],NOW)
    assert _eligible(db,rows[0],NOW+timedelta(days=1))
    assert not _eligible(db,rows[0],NOW+timedelta(days=8))
    db.get(Player,101).clan_id=None
    assert not _eligible(db,rows[0],NOW+timedelta(days=1))
