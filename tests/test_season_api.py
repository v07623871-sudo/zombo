"""HTTP path for one-time season rewards and saved ranking history."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from tests.test_game import app
from models import SessionLocal, Clan, Player
from clan_missions import record_clan_progress


def test_season_reward_api_and_replay(monkeypatch):
    from clan_missions import now as original_now
    import clan_missions

    pid = 989701
    work = datetime(2030, 3, 11, 12, tzinfo=timezone.utc)
    payout = datetime(2030, 4, 1, 1, 5, tzinfo=timezone.utc)
    with TestClient(app) as client:
        with SessionLocal.begin() as db:
            clan = Clan(name='Сезонный тест 2030', leader_id=pid, treasury=0, level=1)
            db.add(clan)
            db.flush()
            player = Player(id=pid, name='Сезонный игрок', hero_class='soldier',
                            clan_id=clan.id, level=5, caps=50, stats={
                                'strength': 0, 'agility': 0, 'endurance': 0,
                                'accuracy': 0, 'regen': 0, 'luck': 0}, skills=[])
            db.add(player)
            db.flush()
            record_clan_progress(db, pid, 'kills', 25, at=work)
        monkeypatch.setattr(clan_missions, 'now', lambda: payout)
        headers = {'Authorization': f'demo:{pid}'}
        assert client.post('/api/clan-missions/season-claim').status_code == 401
        view = client.get('/api/clan-missions', headers=headers)
        assert view.status_code == 200, view.text
        assert view.json()['season_reward']['can_claim']
        assert view.json()['season_history'][0]['season'] == '2030-03'
        first = client.post('/api/clan-missions/season-claim', headers=headers)
        assert first.status_code == 200, first.text
        assert first.json()['caps'] == 120
        second = client.post('/api/clan-missions/season-claim', headers=headers)
        assert second.status_code == 400
        assert client.get('/api/clan-missions', headers=headers).json()['season_reward']['claimed']
    monkeypatch.setattr(clan_missions, 'now', original_now)
