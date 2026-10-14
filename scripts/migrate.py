"""Forward-only additive schema migrations for an existing ZOMBO database.

Run only after a PostgreSQL backup. The preflight checks all existing managed
tables before any DDL. Unknown column changes require a reviewed migration;
this script never drops or rewrites player/economy data.
"""
from pathlib import Path
import argparse
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import (Column, DateTime, MetaData, String, Table, inspect,
                        UniqueConstraint, select, insert, text)
from models import Base, engine, now


CORE_TABLES = frozenset('''
admin_audit api_quotas battles boss_hits clan_mission_members clan_missions
clan_officers clan_renown clan_seasons clans expedition_incidents
expedition_members expedition_runs gear_items gear_sales items lots
notification_outbox notification_preferences payment_reviews payments
player_encounters players pvp_matches quest_progress raid_members raid_runs
star_invoices story_progress telegram_receipts territories territory_taxes
territory_wars war_fighters world_boss world_event_participants world_events
'''.split())
MIGRATIONS = (
    ('20261012_01_baseline', CORE_TABLES),
    ('20261012_02_notification_categories', frozenset({'notification_category_optins'})),
    ('20261012_03_clan_seasons', frozenset({
        'clan_season_contributions', 'clan_season_settlements',
        'clan_season_results', 'clan_season_reward_claims'})),
    ('20261012_04_encounter_clues', frozenset({'encounter_clues'})),
    ('20261012_05_resource_ledger', frozenset({'resource_ledger'})),
    ('20261012_06_clan_treasury_ledger', frozenset({'clan_treasury_ledger'})),
    ('20261014_07_gear_condition', frozenset({'gear_condition'})),
)
registry = MetaData()
schema_migrations = Table('schema_migrations', registry,
    Column('version', String(70), primary_key=True),
    Column('applied_at', DateTime(timezone=True), nullable=False))


def expected_tables():
    import app  # noqa: F401 - register every SQLAlchemy model after environment setup
    registered = set().union(*(names for _, names in MIGRATIONS))
    if registered != set(Base.metadata.tables):
        raise RuntimeError(f'Migration registry mismatch: missing {sorted(set(Base.metadata.tables)-registered)}, '
                           f'unknown {sorted(registered-set(Base.metadata.tables))}')
    return registered


def preflight(connection):
    """Reject unsafe drift before creating tables or marking migration versions."""
    expected_tables()
    inspector = inspect(connection)
    existing = set(inspector.get_table_names())
    for name, table in Base.metadata.tables.items():
        if name not in existing:
            continue
        live_columns = {column['name'] for column in inspector.get_columns(name)}
        missing = set(table.columns.keys()) - live_columns
        if missing:
            raise RuntimeError(f'{name}: missing columns {sorted(missing)}; stop and review schema before deploying')
        pk = inspector.get_pk_constraint(name).get('constrained_columns') or []
        expected_pk = [column.name for column in table.primary_key.columns]
        if pk != expected_pk:
            raise RuntimeError(f'{name}: primary key drift: expected {expected_pk}, found {pk}')
        live_indexes = inspector.get_indexes(name)
        live_unique = {tuple(entry.get('column_names') or ())
                       for entry in inspector.get_unique_constraints(name)}
        live_unique.update(tuple(entry.get('column_names') or ())
                           for entry in live_indexes if entry.get('unique'))
        for constraint in table.constraints:
            if isinstance(constraint, UniqueConstraint):
                columns = tuple(column.name for column in constraint.columns)
                if columns not in live_unique:
                    raise RuntimeError(f'{name}: missing unique constraint on {columns}')
        index_names = {entry['name'] for entry in live_indexes}
        for index in table.indexes:
            if index.name not in index_names:
                raise RuntimeError(f'{name}: missing index {index.name}')
    return existing


def status(connection):
    """Read-only plan: pending tables and recorded migrations."""
    existing = preflight(connection)
    recorded = set(connection.scalars(select(schema_migrations.c.version))) if 'schema_migrations' in existing else set()
    known = {version for version, _ in MIGRATIONS}
    unknown = recorded - known
    if unknown:
        raise RuntimeError(f'Unknown newer migrations: {sorted(unknown)}; use matching code')
    for version, names in MIGRATIONS:
        missing = names - existing
        if version in recorded and missing:
            raise RuntimeError(f'{version}: recorded migration has missing tables {sorted(missing)}; restore from backup')
    return {'pending_tables': sorted(set(Base.metadata.tables) - existing),
            'pending_versions': [version for version, _ in MIGRATIONS if version not in recorded],
            'recorded_versions': sorted(recorded)}


def migrate(connection):
    """Apply additive table batches and record each version atomically on PostgreSQL."""
    if connection.dialect.name == 'postgresql':
        # Serializes two manual migration runners, not gameplay transactions.
        connection.execute(text('SELECT pg_advisory_xact_lock(1515142466)'))
    before = preflight(connection)
    plan = status(connection)
    schema_migrations.create(bind=connection, checkfirst=True)
    recorded = set(plan['recorded_versions'])
    ordered = Base.metadata.sorted_tables
    for version, names in MIGRATIONS:
        for table in ordered:
            if table.name in names:
                table.create(bind=connection, checkfirst=True)
        if version not in recorded:
            connection.execute(insert(schema_migrations).values(version=version, applied_at=now()))
    # Also verify freshly created tables and indexes before committing.
    preflight(connection)
    return sorted(set(inspect(connection).get_table_names()) - before)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Inspect or apply additive ZOMBO migrations')
    parser.add_argument('--check', action='store_true', help='read-only schema preflight and pending plan')
    args = parser.parse_args()
    if args.check:
        with engine.connect() as conn:
            plan = status(conn)
        print('Pending tables:', ', '.join(plan['pending_tables']) or 'none')
        print('Pending versions:', ', '.join(plan['pending_versions']) or 'none')
    else:
        with engine.begin() as conn:
            print('New tables:', ', '.join(migrate(conn)) or 'none')
