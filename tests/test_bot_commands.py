"""Ensure Telegram bot commands are functional and never leak secrets."""
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from tests.test_game import app
from models import SessionLocal, Player


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
