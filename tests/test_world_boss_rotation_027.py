"""World-boss campaign: five rotations and non-repeatable top-1 rewards."""
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, func

from tests.test_game import app
from game import WORLD_BOSS_ROTATION
from gear import GearItem
from models import BossHit, Player, SessionLocal, WorldBoss, now


def auth(pid):
    return {'Authorization':f'demo:{pid}'}


def test_five_bosses_have_distinct_names_and_scaled_hp():
    assert len(WORLD_BOSS_ROTATION)==5
    assert len(set(b['name'] for b in WORLD_BOSS_ROTATION))==5
    assert [b['max_hp'] for b in WORLD_BOSS_ROTATION]==[
        500000,1500000,3000000,6000000,10000000]


def test_expired_boss_pays_top_damage_once_then_rotates():
    leader=99327001
    runner_up=99327002
    with TestClient(app) as api:
        for pid in (leader,runner_up):
            assert api.post('/api/class',headers=auth(pid),
                            json={'key':'soldier'}).status_code==200
        with SessionLocal.begin() as db:
            boss=db.get(WorldBoss,1)
            if boss is None:
                boss=WorldBoss(id=1,name=WORLD_BOSS_ROTATION[0]['name'],
                               hp=0,max_hp=500000)
                db.add(boss)
            boss.name=WORLD_BOSS_ROTATION[0]['name']
            boss.hp=0
            boss.max_hp=500000
            boss.spawn_at=now()-timedelta(days=4,seconds=2)
            db.flush()
            cycle=str(int(boss.spawn_at.timestamp()))
            for pid,points in ((leader,1200),(runner_up,200)):
                db.add(BossHit(player_id=pid,spawn_at=cycle,damage=points))
        before=lambda pid: None
        with SessionLocal() as db:
            first=db.scalar(select(func.count()).select_from(GearItem)
                .where(GearItem.player_id==leader,GearItem.source=='boss'))
        view=api.get('/api/boss')
        assert view.status_code==200,view.text
        result=view.json()
        assert result['name']==WORLD_BOSS_ROTATION[1]['name']
        assert result['max_hp']==WORLD_BOSS_ROTATION[1]['max_hp']
        assert result['hp']==result['max_hp']
        assert result['cycle_bosses']==5
        assert 'винтовка' in result['top_prize']
        with SessionLocal() as db:
            amount=db.scalar(select(func.count()).select_from(GearItem)
                .where(GearItem.player_id==leader,GearItem.source=='boss'))
            assert amount==first+1
            reward=db.scalar(select(GearItem).where(
                GearItem.player_id==leader,GearItem.source=='boss')
                .order_by(GearItem.id.desc()))
            assert reward.base_key=='rifle' and reward.rarity=='legendary'
            other=db.scalar(select(func.count()).select_from(GearItem)
                .where(GearItem.player_id==runner_up,GearItem.source=='boss'))
            assert other==0
        again=api.get('/api/boss')
        assert again.json()['name']==WORLD_BOSS_ROTATION[1]['name']
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(GearItem)
                .where(GearItem.player_id==leader,GearItem.source=='boss'))==first+1


def test_all_bosses_rotate_in_order_with_existing_schema():
    with TestClient(app) as api:
        names=[cfg['name'] for cfg in WORLD_BOSS_ROTATION]
        with SessionLocal.begin() as db:
            boss=db.get(WorldBoss,1)
            if boss is None:
                boss=WorldBoss(id=1,name=names[0],
                               hp=500000,max_hp=500000)
                db.add(boss)
            boss.name=names[0]
            boss.spawn_at=now()
            boss.hp=boss.max_hp=500000
        for index in range(1,6):
            with SessionLocal.begin() as db:
                boss=db.get(WorldBoss,1)
                boss.spawn_at=now()-timedelta(days=4)
            result=api.get('/api/boss').json()
            expected=WORLD_BOSS_ROTATION[index%5]
            assert result['name']==expected['name']
            assert result['max_hp']==expected['max_hp']
