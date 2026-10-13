"""World-boss 0.29: real phases, class mitigation, anti-farm payouts."""
from datetime import timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select, func

from tests.test_game import app
from boss_combat import boss_counterattack, boss_profile, combat_phase
from game import WORLD_BOSS_ROTATION
from models import BossHit, Player, SessionLocal, WorldBoss, now
from gear import GearItem


class FixedRng:
    def randint(self,low,high):return 0
    def random(self):return .99


def headers(pid):
    return {'Authorization':f'demo:{pid}'}


def setup_player(api,pid,klass='soldier'):
    res=api.post('/api/class',headers=headers(pid),json={'key':klass})
    assert res.status_code==200,res.text


def test_all_five_bosses_counterattack_with_different_special_effects():
    pid=99329001
    with TestClient(app) as api:
        setup_player(api,pid)
        outcomes=[]
        with SessionLocal.begin() as db:
            p=db.get(Player,pid)
            p.level=50
            p.stats={**p.stats,'endurance':300}
            for data in WORLD_BOSS_ROTATION:
                boss=WorldBoss(name=data['name'],max_hp=data['max_hp'],
                               hp=data['max_hp']//4)
                p.hp=1000;p.stamina=200;p.thirst=20;p.hunger=20
                output=boss_counterattack(db,p,boss,3,rng=FixedRng())
                assert output['special'] and output['phase']=='Опасная'
                assert output['damage_received']>0
                assert output['message'].startswith(data['name'])
                assert p.hp<1000
                outcomes.append((output['stamina_drained'],p.thirst,p.hunger))
        assert outcomes[0][0]==0
        assert outcomes[1][0]==4
        assert outcomes[2][0]==8 and outcomes[2][1]>20
        assert outcomes[3][0]==10 and outcomes[3][1]>20 and outcomes[3][2]>20
        assert outcomes[4][0]==0


def test_boss_armor_dodge_and_death_penalty():
    pid=99329002
    with TestClient(app) as api:
        setup_player(api,pid,'soldier')
        with SessionLocal.begin() as db:
            p=db.get(Player,pid)
            p.caps=1000;p.xp=100;p.hp=1
            boss=WorldBoss(name='Жнец пустоши',max_hp=1000,hp=1000)
            out=boss_counterattack(db,p,boss,1,rng=FixedRng())
            assert out['defeated'] and out['damage_received']>0
            assert out['losses']['caps']==200
            assert out['losses']['xp']==30
            assert p.location=='base'
            assert p.cooldown is not None
        # New actions respect the cooldown set after a defeat.
        denied=api.post('/api/boss/hit',headers=headers(pid))
        assert denied.status_code==400


def test_boss_api_hit_replies_and_preserves_30_second_cooldown():
    pid=99329003
    with TestClient(app) as api:
        setup_player(api,pid,'soldier')
        with SessionLocal.begin() as db:
            p=db.get(Player,pid);p.stamina=500;p.hp=100
            b=db.get(WorldBoss,1)
            if b is None:
                b=WorldBoss(id=1,name='Гниющий колосс',max_hp=500000,
                            hp=500000,spawn_at=now())
                db.add(b)
            b.name='Гниющий колосс';b.max_hp=500000
            b.hp=500000;b.spawn_at=now()
        first=api.post('/api/boss/hit',headers=headers(pid))
        assert first.status_code==200,first.text
        data=first.json()
        assert data['damage']>0
        assert data['damage_received']>0
        assert data['turn']==1
        assert data['player_hp']<100
        assert data['phase']=='Обычная'
        second=api.post('/api/boss/hit',headers=headers(pid))
        assert second.status_code==400
        for expected in (2,3):
            with SessionLocal.begin() as db:
                db.scalar(select(BossHit).where(BossHit.player_id==pid)).last_hit=now()-timedelta(minutes=1)
                p=db.get(Player,pid);p.hp=100;p.stamina=500
            current=api.post('/api/boss/hit',headers=headers(pid))
            assert current.status_code==200,current.text
            assert current.json()['turn']==expected
            assert current.json()['special']==(expected==3)
        info=api.get('/api/boss')
        assert info.status_code==200 and info.json()['mechanic']
        assert 'только если' in info.json()['top_prize']


def test_no_legendary_for_failed_boss_even_with_a_leader():
    pid=99329004
    with TestClient(app) as api:
        setup_player(api,pid)
        with SessionLocal.begin() as db:
            b=db.get(WorldBoss,1)
            if b is None:
                b=WorldBoss(id=1,name='Гниющий колосс',hp=500000,
                            max_hp=500000)
                db.add(b)
            b.name='Гниющий колосс'
            b.hp=1000;b.max_hp=500000
            b.spawn_at=now()-timedelta(days=7,seconds=17)
            db.flush()
            db.add(BossHit(player_id=pid,
                spawn_at=str(int(b.spawn_at.timestamp())),damage=499000))
            before=db.scalar(select(func.count()).select_from(GearItem)
                       .where(GearItem.player_id==pid,GearItem.source=='boss')) or 0
        result=api.get('/api/boss')
        assert result.status_code==200,result.text
        assert result.json()['name']=='Матерь заражённых'
        with SessionLocal() as db:
            after=db.scalar(select(func.count()).select_from(GearItem)
                       .where(GearItem.player_id==pid,GearItem.source=='boss')) or 0
            assert after==before


def test_phase_thresholds_and_special_attack_names():
    for profile in WORLD_BOSS_ROTATION:
        b=WorldBoss(name=profile['name'],max_hp=1000,hp=1000)
        assert combat_phase(b)=='Обычная'
        b.hp=500
        assert combat_phase(b)=='Опасная'
        b.hp=200
        assert combat_phase(b)=='Ярость'
        assert boss_profile(b)['attack_name']==profile['attack_name']
        assert boss_profile(b)['mechanic']


def test_expired_boss_never_reuses_existing_recent_cycle_id():
    pid=99329005
    with TestClient(app) as api:
        setup_player(api,pid)
        candidate=str(int(now().timestamp()))
        with SessionLocal.begin() as db:
            b=db.get(WorldBoss,1)
            if b is None:
                b=WorldBoss(id=1,name='Гниющий колосс',max_hp=500000,hp=1)
                db.add(b)
            b.name='Гниющий колосс'
            b.max_hp=500000;b.hp=1
            b.spawn_at=now()-timedelta(days=4)
            db.add(BossHit(player_id=pid,spawn_at=candidate,damage=999))
        output=api.get('/api/boss')
        assert output.status_code==200,output.text
        assert output.json()['spawn_at']!=candidate
        # Old damage from a colliding epoch-second cannot carry into the new boss.
        assert output.json()['top']==[]
