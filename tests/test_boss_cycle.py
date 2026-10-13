"""World boss rotation must work even when nobody opens its screen first."""
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, func

from tests.test_game import app
from models import BossHit, Player, SessionLocal, WorldBoss, now


def test_attack_starts_new_boss_cycle_without_get_request():
    pid = 94001
    headers = {'Authorization': f'demo:{pid}'}
    with TestClient(app) as client:
        assert client.post('/api/class', headers=headers, json={'key': 'soldier'}).status_code == 200
        with SessionLocal.begin() as db:
            player = db.get(Player, pid)
            player.stamina = 500
            boss = db.get(WorldBoss, 1)
            if not boss:
                boss = WorldBoss(id=1, name='Гниющий колосс', max_hp=500000)
                db.add(boss)
            boss.hp = 0
            boss.spawn_at = now() - timedelta(days=4)
            db.flush()
            old_cycle = str(int(boss.spawn_at.timestamp()))
            old_count = db.scalar(select(func.count()).select_from(BossHit).where(BossHit.spawn_at == old_cycle)) or 0
            db.add(BossHit(player_id=pid, spawn_at=old_cycle, damage=123))
        hit = client.post('/api/boss/hit', headers=headers)
        assert hit.status_code == 200, hit.text
        assert hit.json()['damage'] > 0
        current = client.get('/api/boss').json()
        assert current['top'][0]['damage'] == hit.json()['damage']
        with SessionLocal() as db:
            boss = db.get(WorldBoss, 1)
            assert boss.hp == boss.max_hp - hit.json()['damage']
            hits = db.scalars(select(BossHit).where(BossHit.player_id == pid)).all()
            assert len(hits) == 2
            assert {h.spawn_at for h in hits} != {old_cycle}
            assert db.scalar(select(func.count()).select_from(BossHit).where(BossHit.spawn_at == old_cycle)) == old_count + 1
