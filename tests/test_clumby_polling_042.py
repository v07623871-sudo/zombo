"""Regression tests for Clumby polling transport and Railway webhook coexistence."""
import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def test_clumby_entrypoint_requires_no_server_or_database():
    script=(ROOT/'clumby_polling.py').read_text(encoding='utf-8')
    tree=ast.parse(script)
    imports=[node.module or '' for node in ast.walk(tree)
             if isinstance(node,ast.ImportFrom)]
    assert not any(x in imports for x in ('fastapi','sqlalchemy','psycopg','uvicorn'))
    assert "getUpdates" in script
    assert "deleteWebhook" in script
    assert "pre_checkout_query" in script
    assert "'message'" in script
    assert "'drop_pending_updates': False" in script
    assert "BACKEND + '/telegram/webhook'" in script
    assert "'X-Telegram-Bot-Api-Secret-Token': SECRET" in script
    assert "offset = uid + 1" not in script  # script uses update_id variable
    assert "offset = update_id + 1" in script
    assert "def run()" in script


def test_railway_does_not_restore_webhook_in_external_mode():
    script=(ROOT/'app.py').read_text(encoding='utf-8')
    assert "TELEGRAM_UPDATES_TRANSPORT" in script
    assert "transport=='webhook' and BOT_TOKEN and PUBLIC_URL and SECRET" in script
    assert "transport=='external_polling'" in script
    assert "TELEGRAM_WEBHOOK_SECRET" in script


def test_clumby_guide_warns_shared_db_and_revoking_compromised_token():
    entry=(ROOT/'main.py').read_text(encoding='utf-8')
    guide=(ROOT/'CLUMBY_HOST.md').read_text(encoding='utf-8')
    assert "from clumby_polling import run" in entry
    assert "TELEGRAM_UPDATES_TRANSPORT=external_polling" in guide
    assert "python main.py" in guide
    assert "ZOMBO_API_URL" in guide
    assert "PostgreSQL" in guide
    assert "BotFather" in guide
