"""Additive migration smoke on the disposable PostgreSQL used by CI only."""
import os
from sqlalchemy import insert, select
from sqlalchemy.engine.url import make_url

assert os.getenv('ZOMBO_TEST_DATABASE') == '1', 'Disposable DB marker required'
assert os.getenv('DATABASE_URL', '').startswith('postgresql'), 'PostgreSQL required'
assert make_url(os.environ['DATABASE_URL']).database.endswith(('_ci', '_test')), 'Disposable DB name required'
assert os.getenv('DEMO_MODE') == '1' and not os.getenv('BOT_TOKEN'), 'Demo auth only'

import app  # noqa: F401 - register all models before creating the legacy table set
from models import Base, Player, engine
from scripts.migrate import CORE_TABLES, MIGRATIONS, migrate, status, schema_migrations


with engine.begin() as connection:
    for table in Base.metadata.sorted_tables:
        if table.name in CORE_TABLES:
            table.create(bind=connection, checkfirst=True)
    connection.execute(insert(Player).values(id=9926000001, name='Migration survivor', caps=77))
    plan = status(connection)
    assert set(plan['pending_tables']) == {
        'notification_category_optins', 'clan_season_contributions',
        'clan_season_settlements', 'clan_season_results', 'clan_season_reward_claims',
        'encounter_clues', 'resource_ledger', 'clan_treasury_ledger',
        'gear_condition'}
    assert len(plan['pending_versions']) == len(MIGRATIONS)
    created = migrate(connection)
    assert set(plan['pending_tables']) <= set(created)
    assert 'schema_migrations' in created
    assert migrate(connection) == []
    assert connection.execute(select(Player.name, Player.caps).where(
        Player.id == 9926000001)).one() == ('Migration survivor', 77)
    assert len(connection.execute(select(schema_migrations.c.version)).all()) == len(MIGRATIONS)

print('PostgreSQL: legacy table set migrated, player preserved, versions idempotent: PASS')
