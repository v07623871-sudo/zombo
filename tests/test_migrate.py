from sqlalchemy import create_engine, text
from scripts.migrate import migrate


def test_migration_preserves_existing_player_row_and_is_idempotent():
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE players (id BIGINT PRIMARY KEY, name VARCHAR(90), username VARCHAR(90), hero_class VARCHAR(30), level INTEGER, xp INTEGER, stat_points INTEGER, skill_points INTEGER, stats JSON, skills JSON, hp INTEGER, stamina INTEGER, hunger INTEGER, thirst INTEGER, caps INTEGER, zombo INTEGER, location VARCHAR(50), kills INTEGER, rating INTEGER, karma INTEGER, clan_id INTEGER, pvp_wins INTEGER, last_daily VARCHAR(16), last_tick DATETIME, cooldown DATETIME, vip_until DATETIME, xp_boost_until DATETIME, loot_boost_until DATETIME, banned BOOLEAN, frozen BOOLEAN, created_at DATETIME)'))
        conn.execute(text("INSERT INTO players (id, name, caps) VALUES (123, 'survivor', 77)"))
        assert 'admin_audit' in migrate(conn)
        assert 'star_invoices' in set(conn.dialect.get_table_names(conn))
        assert 'payment_reviews' in set(conn.dialect.get_table_names(conn))
        assert migrate(conn) == []
        assert conn.execute(text('SELECT name, caps FROM players WHERE id=123')).one() == ('survivor', 77)
    engine.dispose()
