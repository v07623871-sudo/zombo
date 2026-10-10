"""Talent upgrades, prerequisites, persistent ranks, respec and combat abilities."""
from tests.test_game import app, H
from fastapi.testclient import TestClient
from sqlalchemy import select
from models import Player, Battle, SessionLocal
from game import SKILL_TREES, gain_xp, talent_rank, talent_bonus, xp_needed, max_hp


def auth(idx):return {'Authorization':f'demo:{idx}'}


def set_character(idx, level=12, points=25):
    with SessionLocal.begin() as db:
        p=db.get(Player,idx)
        p.level=level;p.skill_points=points;p.stamina=500;p.hp=max_hp(p)


def test_talent_tree_shapes_and_old_skill_ids():
    for cls,branches in SKILL_TREES.items():
        assert len(branches)==3,(cls,branches)
        keys=[]
        for b in branches:
            assert len(b['nodes'])==3
            for tier,node in enumerate(b['nodes']):
                assert node['tier']==tier+1
                assert node['max_rank']==3
                keys.append(node['key'])
        assert len(set(keys))==9
        assert sum(n['kind']=='active' for b in branches for n in b['nodes'])==1


def test_class_skills_prerequisites_ranks_and_free_reset():
    with TestClient(app) as c:
        user=auth(54001)
        assert c.post('/api/class',headers=user,json={'key':'soldier'}).status_code==200
        start=c.get('/api/me',headers=user).json()
        assert start['skill_points']==2
        assert start['talent_spent']==0
        assert start['talent_reset_cost']==0
        meta=c.get('/api/config').json()
        assert len(meta['skill_trees']['soldier'])==3
        assert c.post('/api/skill',headers=user,json={'key':'double'}).status_code==400
        assert c.post('/api/skill',headers=user,json={'key':'sniper'}).status_code==400
        assert c.post('/api/skill',headers=user,json={'key':'aim'}).status_code==200
        assert c.post('/api/skill',headers=user,json={'key':'aim'}).status_code==200
        assert c.post('/api/skill',headers=user,json={'key':'aim'}).status_code==400
        assert c.post('/api/skill',headers=user,json={'key':'nonexistent'}).status_code==400
        set_character(54001)
        assert c.post('/api/skill',headers=user,json={'key':'double'}).status_code==200
        assert c.post('/api/skill',headers=user,json={'key':'sniper'}).status_code==400
        assert c.post('/api/skill',headers=user,json={'key':'double'}).status_code==200
        assert c.post('/api/skill',headers=user,json={'key':'sniper'}).status_code==200
        view=c.get('/api/me',headers=user).json()
        assert view['talent_ranks']['aim']==2
        assert view['talent_ranks']['double']==2
        assert view['talent_ranks']['sniper']==1
        assert view['talent_bonuses']['power']>.1
        assert view['talent_reset_cost']==0
        assert c.post('/api/skill/reset',headers=user).status_code==200
        after=c.get('/api/me',headers=user).json()
        assert not after['skills'] and after['skill_points']==27
        assert after['talent_reset_cost']==100
        assert c.post('/api/skill/reset',headers=user).status_code==400
        assert c.post('/api/skill',headers=user,json={'key':'aim'}).status_code==200
        assert c.post('/api/skill/reset',headers=user).status_code==200
        assert c.get('/api/me',headers=user).json()['caps']==25


def test_active_skill_is_server_checked_and_has_cooldown():
    with TestClient(app) as c:
        user=auth(54002)
        c.post('/api/class',headers=user,json={'key':'medic'})
        assert c.post('/api/travel',headers=user,json={'key':'forest'}).status_code==200
        assert c.post('/api/combat/start',headers=user).status_code==200
        assert c.post('/api/combat/turn',headers=user,json={'action':'skill','zone':'master'}).status_code==400
        # End fight before modifying talents, so respec can be tested separately.
        assert c.post('/api/combat/turn',headers=user,json={'action':'flee'}).status_code==200
        set_character(54002)
        assert c.post('/api/skill',headers=user,json={'key':'healer'}).status_code==200
        assert c.post('/api/skill',headers=user,json={'key':'healer'}).status_code==200
        assert c.post('/api/skill',headers=user,json={'key':'antidote'}).status_code==200
        assert c.post('/api/skill',headers=user,json={'key':'antidote'}).status_code==200
        assert c.post('/api/skill',headers=user,json={'key':'master'}).status_code==200
        assert c.post('/api/combat/start',headers=user).status_code==200
        # Enough enemy HP to prove the per-battle cooldown remains enforced.
        with SessionLocal.begin() as db:
            battle=db.scalar(select(Battle).where(Battle.player_id==54002))
            battle.enemy_hp=battle.enemy_max_hp=3000
            battle.enemy_damage=1
            p=db.get(Player,54002);p.hp=30
        result=c.post('/api/combat/turn',headers=user,json={'action':'skill','zone':'master'})
        assert result.status_code==200,result.text
        assert result.json()['finished']==False
        state=c.get('/api/me',headers=user).json()
        assert state['hp']>30
        assert state['battle']['ability_cooldowns']['master']==2
        assert all('!ability:' not in line for line in state['battle']['log'])
        assert c.post('/api/combat/turn',headers=user,json={'action':'skill','zone':'master'}).status_code==400
        for _ in range(2):
            assert c.post('/api/combat/turn',headers=user,json={'action':'defend'}).status_code==200
        assert c.post('/api/combat/turn',headers=user,json={'action':'skill','zone':'master'}).status_code==200
        assert c.post('/api/skill/reset',headers=user).status_code==400


def test_legacy_progress_conversion_and_level_grants():
    with TestClient(app) as c:
        u=auth(54003)
        c.post('/api/class',headers=u,json={'key':'thief'})
        with SessionLocal.begin() as db:
            p=db.get(Player,54003)
            p.level=11;p.skill_points=1;p.skills=['dodge','silent','loot']
            stats=dict(p.stats);stats.pop('_talent_v2',None);p.stats=stats
        a=c.get('/api/me',headers=u).json()
        assert a['talent_ranks']['loot']==1
        # At 11, new total 2+(10//2)+(10//5)=9, old grants 11//5=2, so 1+7=8
        assert a['skill_points']==8
        b=c.get('/api/me',headers=u).json()
        assert b['skill_points']==8
        with SessionLocal.begin() as db:
            p=db.get(Player,54003);p.level=11;p.xp=xp_needed(11)-1
            gain_xp(p,1)
            assert p.level==12 and p.skill_points==9