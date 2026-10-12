from sqlalchemy import create_engine, text
import pytest
from scripts.migrate import MIGRATIONS, migrate, status


def test_migration_preserves_existing_player_row_and_is_idempotent():
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE players (id BIGINT PRIMARY KEY, name VARCHAR(90), username VARCHAR(90), hero_class VARCHAR(30), level INTEGER, xp INTEGER, stat_points INTEGER, skill_points INTEGER, stats JSON, skills JSON, hp INTEGER, stamina INTEGER, hunger INTEGER, thirst INTEGER, caps INTEGER, zombo INTEGER, location VARCHAR(50), kills INTEGER, rating INTEGER, karma INTEGER, clan_id INTEGER, pvp_wins INTEGER, last_daily VARCHAR(16), last_tick DATETIME, cooldown DATETIME, vip_until DATETIME, xp_boost_until DATETIME, loot_boost_until DATETIME, banned BOOLEAN, frozen BOOLEAN, created_at DATETIME)'))
        conn.execute(text("INSERT INTO players (id, name, caps) VALUES (123, 'survivor', 77)"))
        assert 'admin_audit' in migrate(conn)
        assert 'star_invoices' in set(conn.dialect.get_table_names(conn))
        assert 'payment_reviews' in set(conn.dialect.get_table_names(conn))
        assert 'notification_category_optins' in set(conn.dialect.get_table_names(conn))
        assert {'clan_season_contributions','clan_season_settlements',
                'clan_season_results','clan_season_reward_claims'} <= set(conn.dialect.get_table_names(conn))
        assert 'encounter_clues' in set(conn.dialect.get_table_names(conn))
        assert 'resource_ledger' in set(conn.dialect.get_table_names(conn))
        assert migrate(conn) == []
        assert conn.execute(text('SELECT name, caps FROM players WHERE id=123')).one() == ('survivor', 77)
        assert set(conn.execute(text('SELECT version FROM schema_migrations')).scalars()) == {
            version for version, _ in MIGRATIONS}
        assert status(conn)['pending_versions'] == []
    engine.dispose()


def test_migration_check_is_read_only():
    engine = create_engine('sqlite://')
    with engine.connect() as conn:
        plan = status(conn)
        assert 'players' in plan['pending_tables']
        assert len(plan['pending_versions']) == len(MIGRATIONS)
        assert conn.dialect.get_table_names(conn) == []
    engine.dispose()


def test_migration_rejects_missing_columns_before_any_ddl():
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE players (id BIGINT PRIMARY KEY, name VARCHAR(90))'))
        with pytest.raises(RuntimeError, match='missing columns'):
            migrate(conn)
        assert set(conn.dialect.get_table_names(conn)) == {'players'}
    engine.dispose()


def test_migration_rejects_missing_unique_and_index():
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE items (id INTEGER PRIMARY KEY, player_id BIGINT, item_key VARCHAR(55), quantity INTEGER, equipped BOOLEAN)'))
        with pytest.raises(RuntimeError, match='missing unique constraint'):
            migrate(conn)
        assert 'schema_migrations' not in conn.dialect.get_table_names(conn)
    engine.dispose()

    from models import Base
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        Base.metadata.create_all(conn)
        conn.execute(text('DROP INDEX ix_items_player_id'))
        with pytest.raises(RuntimeError, match='missing index ix_items_player_id'):
            migrate(conn)
        assert 'schema_migrations' not in conn.dialect.get_table_names(conn)
    engine.dispose()


def test_recorded_migration_does_not_recreate_lost_table():
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        migrate(conn)
        conn.execute(text('DROP TABLE clan_season_results'))
        with pytest.raises(RuntimeError, match='recorded migration has missing tables'):
            migrate(conn)
        assert 'clan_season_results' not in conn.dialect.get_table_names(conn)
    engine.dispose()
