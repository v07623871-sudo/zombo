"""Regression coverage for Telegram modal clicks and clan writes.

The regressions caught in production on 2026-10-11:
- SQLAlchemy SQLite accepted an unquoted PostgreSQL reserved identifier (window).
- An inline stopPropagation() on the modal blocked delegated button clicks.
"""
import inspect
from pathlib import Path

from fastapi.testclient import TestClient

from models import Player, SessionLocal
from security import enforce_quota
from tests.test_game import app


def test_postgresql_quota_uses_quoted_reserved_identifier():
    query = inspect.getsource(enforce_quota)
    assert 'scope, "window", count' in query
    assert 'api_quotas."window"' in query
    assert '"window" = :window' in query


def test_modal_clicks_reach_delegated_handler():
    frontend = (Path(__file__).resolve().parents[1] / 'static' / 'app.js').read_text(encoding='utf-8')
    modal = frontend.split('function modalView(){', 1)[1].split('function showModal', 1)[0]
    assert 'onclick="event.stopPropagation()"' not in modal
    assert 'data-action="close"' in modal
    assert "if(b.classList.contains('modal-bg')&&e.target!==b)return" in frontend
    assert "if(action==='submit-clan')" in frontend
    assert "if(result){modal=null;await nav('clan')}" in frontend


def test_can_create_clan_with_257_caps_and_no_double_charge():
    player_id = 916420578101
    headers = {'Authorization': f'demo:{player_id}'}
    with TestClient(app) as client:
        # Creating a hero is a write request and passes through the quota middleware.
        character = client.post('/api/class', json={'key': 'soldier'}, headers=headers)
        assert character.status_code == 200, character.text
        with SessionLocal.begin() as db:
            db.get(Player, player_id).caps = 257
        create = client.post('/api/clans/create', json={'name': 'Lohi'}, headers=headers)
        assert create.status_code == 200, create.text
        assert create.json()['id'] > 0
        profile = client.get('/api/me', headers=headers)
        assert profile.status_code == 200
        assert profile.json()['caps'] == 7
        assert profile.json()['clan_id'] == create.json()['id']

        repeat = client.post('/api/clans/create', json={'name': 'Lohi'}, headers=headers)
        assert repeat.status_code == 400
        assert client.get('/api/me', headers=headers).json()['caps'] == 7
