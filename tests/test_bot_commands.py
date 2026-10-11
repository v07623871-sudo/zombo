"""Ensure Telegram bot commands are functional and never leak secrets."""
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from tests.test_game import app
from models import SessionLocal, Player
from models import QuestProgress
from models import now
from raids import RaidRun, RaidMember
from expeditions import ExpeditionRun, ExpeditionMember
from datetime import timedelta


def test_telegram_commands(monkeypatch):
    import app as module
    sender=AsyncMock(return_value={'ok':True})
    monkeypatch.setattr(module,'telegram_api',sender)
    monkeypatch.setattr(module,'SECRET','in-test-secret')
    monkeypatch.setattr(module,'PUBLIC_URL','https://example.test')
    with TestClient(app) as client:
        pid=57716
        user={'Authorization':f'demo:{pid}'}
        assert client.post('/api/class',headers=user,json={'key':'thief'}).status_code==200
        for command in ('/start','/help','/profile','/skills','/map','/enemies','/bag','/clan','/daily'):
            sender.reset_mock()
            res=client.post('/telegram/webhook',json={'message':{'chat':{'id':pid},'from':{'id':pid},'text':command}},headers={'X-Telegram-Bot-Api-Secret-Token':'in-test-secret'})
            assert res.status_code==200,(command,res.text)
            sent=[c for c in sender.call_args_list if c.args[0]=='sendMessage']
            assert sent,command
            data=sent[-1].args[1]
            assert data['chat_id']==pid and data['text']
            assert data['reply_markup']['inline_keyboard'][0][0]['web_app']['url']=='https://example.test'
            if command=='/skills':assert 'Очки талантов' in data['text']
            if command=='/enemies':assert 'Обнаружено:' in data['text']
            if command=='/clan':assert 'КЛАНОВЫЕ ВОЙНЫ' in data['text']
        assert client.post('/telegram/webhook',json={'message':{'chat':{'id':pid},'from':{'id':pid},'text':'/help'}},headers={'X-Telegram-Bot-Api-Secret-Token':'invalid'}).status_code==403
        with SessionLocal.begin() as db:
            db.get(Player,pid).frozen=True
        frozen=client.post('/telegram/webhook',json={'message':{'chat':{'id':pid},'from':{'id':pid},'text':'/daily'}},headers={'X-Telegram-Bot-Api-Secret-Token':'in-test-secret'})
        assert frozen.status_code==200
        assert 'заблокирован' in sender.call_args.args[1]['text']


def test_rankings_and_new_text_commands(monkeypatch):
    import app as module
    sender=AsyncMock(return_value={'ok':True})
    monkeypatch.setattr(module,'telegram_api',sender)
    monkeypatch.setattr(module,'SECRET','test-bot-commands')
    monkeypatch.setattr(module,'PUBLIC_URL','https://example.test')
    ids=[57801,57802,57803,57804]
    with TestClient(app) as client:
        for pid in ids:
            assert client.post('/api/class',headers={'Authorization':f'demo:{pid}'},json={'key':'soldier'}).status_code==200
        with SessionLocal.begin() as db:
            for pid,level,kills,rating,wins in zip(ids,[8,15,11,99],[30,3,20,100],[1000,900,1450,2000],[1,0,9,100]):
                p=db.get(Player,pid);p.name=f'Выживший {pid}';p.level=level;p.kills=kills;p.rating=rating;p.pvp_wins=wins
            db.get(Player,ids[3]).banned=True
            db.add(QuestProgress(player_id=ids[0],code='kills',amount=5,claimed=False))
        level=client.get('/api/leaderboard?sort=level').json()
        kills=client.get('/api/leaderboard?sort=kills').json()
        pvp=client.get('/api/leaderboard?sort=pvp').json()
        assert [x['id'] for x in level if x['id'] in ids]==[ids[1],ids[2],ids[0]]
        assert [x['id'] for x in kills if x['id'] in ids]==[ids[0],ids[2],ids[1]]
        assert [x['id'] for x in pvp if x['id'] in ids]==[ids[2],ids[0],ids[1]]
        assert client.get('/api/leaderboard?sort=wrong').status_code==400

        def command(value):
            sender.reset_mock()
            result=client.post('/telegram/webhook',json={'message':{'chat':{'id':ids[0]},
                'from':{'id':ids[0]},'text':value}},
                headers={'X-Telegram-Bot-Api-Secret-Token':'test-bot-commands'})
            assert result.status_code==200,result.text
            sent=[call.args[1]['text'] for call in sender.call_args_list if call.args[0]=='sendMessage']
            assert len(sent)==1
            return sent[0]

        assert 'ТОП-10' in command('/top')
        assert '57804' not in command('/top kills')
        assert 'АРЕНА' in command('/top@ZomboBot pvp')
        assert 'награда готова' in command('/quests')
        assert 'МИРОВОЙ БОСС' in command('/boss')
        assert 'не состоишь' in command('/raid')
        assert 'нет дальней экспедиции' in command('/expedition')
        assert '/top pvp' in command('/help')
        with SessionLocal.begin() as db:
            raid=RaidRun(creator_id=ids[0],scenario='outpost',status='active',stage=0,
                         expires_at=now()+timedelta(hours=1),log=[])
            db.add(raid);db.flush()
            db.add(RaidMember(run_id=raid.id,player_id=ids[0],hp=100,max_hp=100,contribution=12,actions=1))
            trip=ExpeditionRun(creator_id=ids[0],scenario='relay',status='active',
                lobby_expires_at=now()+timedelta(hours=1),started_at=now(),
                finishes_at=now()+timedelta(hours=12),success_chance=70,will_succeed=True)
            db.add(trip);db.flush()
            db.add(ExpeditionMember(run_id=trip.id,player_id=ids[0],role='guard'))
        assert 'этап 1/3' in command('/raid')
        assert 'отряд в пути' in command('/expedition')
