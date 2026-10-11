import sys
from pathlib import Path
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models import Base, Player, ItemStack
from story import CHAPTERS, StoryProgress, get_progress, story_view, perform


@pytest.fixture()
def state():
    e = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    Base.metadata.create_all(e)
    with Session(e) as db:
        p = Player(id=76390088,name='Тестер',hero_class='medic',level=40,xp=0,
                   hp=3000, stamina=12000,caps=100,karma=0,stats={'strength':0,'agility':0,'endurance':0,'accuracy':0,'regen':0,'luck':0},skills=[])
        db.add(p)
        db.flush()
        s = get_progress(db,p.id)
        yield db,p,s
        db.rollback()
    e.dispose()


def test_chapters_have_distinct_stories_and_valid_actions():
    assert len(CHAPTERS)==10
    assert len(set(c['key'] for c in CHAPTERS))==10
    assert all(c['level']<=CHAPTERS[i+1]['level'] for i,c in enumerate(CHAPTERS[:-1]))
    assert all(len(c['dilemma'])==4 and c['dilemma'][2][2]=='help' and c['dilemma'][3][2]=='take' for c in CHAPTERS)


def test_story_quest_progress_and_choices_are_unique(state):
    db,p,s=state
    assert story_view(p,s)['chapter_index']==1
    old=p.stamina
    outcome=perform(db,p,s,'scout')
    assert outcome['success'] and s.stage==1 and p.stamina<old
    with pytest.raises(ValueError,match='Сначала разберись'):
        perform(db,p,s,'scout')
    assert perform(db,p,s,'fight')['success'] and s.stage==2
    cap=p.caps
    assert perform(db,p,s,'help')['success']
    assert s.chapter==1 and s.stage==0 and s.trust==1 and p.karma==1
    assert p.caps>cap and len(s.decisions)==1
    with pytest.raises(ValueError,match='Сначала проведи разведку'):
        perform(db,p,s,'help')
    assert len(s.decisions)==1
    assert db.scalar(select(ItemStack).where(ItemStack.player_id==p.id,ItemStack.item_key=='medkit')).quantity==1


def test_chapter_level_required_is_enforced_before_spending(state):
    db,p,s=state
    p.level=1
    s.chapter=6
    old=(p.stamina,p.caps)
    with pytest.raises(ValueError,match='уровень 18'):
        perform(db,p,s,'scout')
    assert (p.stamina,p.caps)==old
    assert not story_view(p,s)['available']


def test_fight_damage_and_low_hp_do_not_advance(state):
    db,p,s=state
    perform(db,p,s,'scout')
    p.hp=2
    energy=p.stamina
    x=perform(db,p,s,'fight')
    assert not x['success'] and s.stage==1 and p.hp==1 and p.stamina<energy
    p.hp=180
    assert perform(db,p,s,'fight')['success'] and s.stage==2 and p.kills==1


def test_trust_affects_scouting_and_shadow_route_affects_money(state):
    db,p,s=state
    s.chapter=3;s.trust=3
    old=p.stamina
    x=perform(db,p,s,'scout')
    assert x['success'] and old-p.stamina==5   # 6 + 3//2 - 2
    s.stage=1;s.trust=-3;p.hp=3000
    before=p.caps
    assert perform(db,p,s,'fight')['success']
    assert p.caps-before==13+3*6+20+3*5


def test_ten_chapters_two_endings_and_no_repeat_rewards(state):
    db,p,s=state
    for index in range(10):
        assert s.chapter==index
        assert perform(db,p,s,'scout')['success']
        assert perform(db,p,s,'fight')['success']
        assert perform(db,p,s,'take')['success']
    d=story_view(p,s)
    assert d['finished'] and d['completed_count']==10 and len(s.decisions)==10
    assert d['ending']=='Одинокая крепость'
    before=(p.caps,p.xp,p.karma)
    with pytest.raises(ValueError,match='уже завершена'):
        perform(db,p,s,'take')
    assert (p.caps,p.xp,p.karma)==before
    assert s.trust==-10


def test_invalid_action_does_not_charge_stamina(state):
    db,p,s=state
    before=p.stamina
    for bad in ('kill','take','help','scout-not-real'):
        with pytest.raises(ValueError):perform(db,p,s,bad)
    assert p.stamina==before


def test_story_http_api_and_single_claim(state, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import story as module
    from sqlalchemy.orm import sessionmaker
    db, player, _ = state
    monkeypatch.setattr(module, 'SessionLocal', sessionmaker(bind=db.get_bind(), expire_on_commit=False))
    app = FastAPI()
    from fastapi.responses import JSONResponse
    @app.exception_handler(ValueError)
    async def invalid_action(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=400)
    module.install_story(app, lambda _request, session: session.get(Player,player.id), lambda _player: None)
    client = TestClient(app)
    initial = client.get('/api/story')
    assert initial.status_code==200
    assert initial.json()['chapter_index']==1
    first = client.post('/api/story/act',json={'action':'scout'})
    assert first.status_code==200 and first.json()['story']['stage']==1
    wrong = client.post('/api/story/act',json={'action':'scout'})
    assert wrong.status_code==400
    assert client.get('/api/story').json()['stage']==1