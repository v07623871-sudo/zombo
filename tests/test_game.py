import os, sys, importlib, tempfile
from pathlib import Path
os.environ['DATABASE_URL']='sqlite:///'+str(Path(tempfile.gettempdir())/('zombo_test_'+__import__('uuid').uuid4().hex+'.db'))
os.environ['DEMO_MODE']='1'
os.environ.pop('BOT_TOKEN',None)
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from app import app

H={'Authorization':'demo:1001'}
H2={'Authorization':'demo:1002'}

def test_full_game():
    with TestClient(app) as c:
        assert c.get('/health').json()['status']=='ok'
        assert c.get('/api/me').status_code==401
        assert c.post('/api/class',json={'key':'soldier'},headers=H).status_code==200
        assert c.post('/api/class',json={'key':'medic'},headers=H).status_code==400
        a=c.get('/api/me',headers=H).json();assert a['class']=='soldier'
        assert c.post('/api/travel',json={'key':'forest'},headers=H).status_code==200
        fight=c.post('/api/combat/start',headers=H)
        assert fight.status_code==200, fight.text
        for i in range(30):
            result=c.post('/api/combat/turn',json={'action':'attack','zone':'body'},headers=H)
            assert result.status_code==200,result.text
            if result.json()['finished']:break
        a=c.get('/api/me',headers=H).json()
        assert a['battle'] is None
        assert c.get('/api/quests',headers=H).status_code==200
        assert c.post('/api/daily',headers=H).status_code==200
        assert c.post('/api/daily',headers=H).status_code==400
        assert c.post('/api/craft',json={'key':'medkit'},headers=H).status_code in (200,400)
        assert c.post('/api/class',json={'key':'medic'},headers=H2).status_code==200
        assert c.get('/api/leaderboard').status_code==200
        assert c.get('/api/boss').status_code==200
        assert c.post('/api/boss/hit',headers=H).status_code==200
        assert c.post('/api/pvp/challenge',json={'player_id':1002},headers=H).status_code==200
        m=c.get('/api/pvp',headers=H2).json()['match'];assert m['state']=='pending'
        assert c.post('/api/pvp/act',json={'id':m['id'],'action':'accept'},headers=H2).status_code==200
        assert c.post('/api/pvp/act',json={'id':m['id'],'action':'attack'},headers=H2).status_code==400
        assert c.get('/api/market').status_code==200
        assert c.get('/api/territories').status_code==200
        assert c.get('/api/clans',headers=H).status_code==200

def test_signed_auth():
    import hmac,hashlib,json,time
    import app as module
    old=module.BOT_TOKEN
    try:
        module.BOT_TOKEN='12345:testing'
        user=json.dumps({'id':998877,'first_name':'Выживший'},separators=(',',':'))
        params={'auth_date':str(int(time.time())),'user':user,'query_id':'abc'}
        check='\n'.join(f'{k}={v}' for k,v in sorted(params.items()))
        k=hmac.new(b'WebAppData',module.BOT_TOKEN.encode(),hashlib.sha256).digest()
        signature=hmac.new(k,check.encode(),hashlib.sha256).hexdigest()
        from urllib.parse import urlencode
        good=urlencode({**params,'hash':signature})
        assert module.identify('tma '+good)['id']==998877
        try:
            module.identify('tma '+good.replace('Выживший','Хакер'))
            assert False,'tampered hash was accepted'
        except Exception:pass
    finally:module.BOT_TOKEN=old