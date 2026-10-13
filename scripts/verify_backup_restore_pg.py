"""End-to-end PostgreSQL dump/restore drill on the disposable CI database.

This must NEVER be pointed at production. The restore target is a freshly
created, isolated database on CI's localhost PostgreSQL service, deleted
whether the test succeeds or fails. No backups or credentials are published.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import psycopg
from psycopg import sql
from sqlalchemy.engine.url import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ops' / 'backup'))
from worker import database_command  # noqa: E402

url = make_url(os.environ.get('DATABASE_URL', ''))
assert os.getenv('ZOMBO_TEST_DATABASE') == '1', 'Disposable database flag required'
assert os.getenv('DEMO_MODE') == '1' and not os.getenv('BOT_TOKEN'), 'Demo-only drill'
assert url.drivername.startswith('postgresql'), 'PostgreSQL only'
assert url.host in ('localhost', '127.0.0.1'), 'Only local, disposable CI host is allowed'
assert url.database and url.database.endswith('_ci'), 'Only CI test database is allowed'

TARGET = url.database + '_restore_test'
TABLES = ('players', 'items', 'star_invoices', 'payment_reviews',
          'resource_ledger', 'clan_treasury_ledger')


def connect(dbname):
    return psycopg.connect(
        host=url.host, port=url.port or 5432, dbname=dbname,
        user=url.username, password=url.password, autocommit=True)


def snapshot(dbname):
    with connect(dbname) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            names = {row[0] for row in cursor.fetchall()}
            assert set(TABLES) <= names, ('Missing required tables', set(TABLES) - names)
            counts = {}
            for name in TABLES:
                cursor.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(name)))
                counts[name] = cursor.fetchone()[0]
            cursor.execute('SELECT id, level, caps, xp FROM players ORDER BY id LIMIT 20')
            sample = cursor.fetchall()
    return names, counts, sample


def execute(argv, *, env=None, timeout=180):
    # Password is carried in PGPASSWORD, never in the subprocess arguments.
    proc = subprocess.run(argv, env=env, capture_output=True, text=True,
                          timeout=timeout, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f'{argv[0]} failed (exit {proc.returncode}); '
            f'last output: {(proc.stderr or proc.stdout)[-1200:]}')
    return proc


def main():
    source, env = database_command(os.environ['DATABASE_URL'])
    target, _ = database_command(
        url.set(database=TARGET).render_as_string(hide_password=False))
    created = False
    try:
        with connect('postgres') as connection:
            with connection.cursor() as cursor:
                # A stale target must not be overwritten: prevents hidden data loss.
                cursor.execute('SELECT 1 FROM pg_database WHERE datname = %s', (TARGET,))
                if cursor.fetchone():
                    raise RuntimeError('Restore test database already exists; refusing overwrite')
                cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(TARGET)))
                created = True

        before = snapshot(url.database)
        assert before[1]['players'] >= 1, 'CI database has no test players'

        with tempfile.TemporaryDirectory() as work:
            dump = str(Path(work) / 'zombo_ci.dump')
            execute(['pg_dump', *source, '--format=custom', '--no-owner',
                     '--no-acl', '--file', dump], env=env, timeout=180)
            assert Path(dump).stat().st_size > 0, 'Empty PostgreSQL backup'
            execute(['pg_restore', '--list', dump], env=env)
            execute(['pg_restore', '--exit-on-error', '--no-owner', '--no-acl',
                     *target, dump], env=env, timeout=300)
        after = snapshot(TARGET)
        assert before == after, (
            'Restored schema, financial rows, or player samples do not match')
        print('PASS: PostgreSQL dump/restore, schemas, 6 critical table counts '
              'and player samples match isolated CI source.')
    finally:
        if created:
            with connect('postgres') as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(TARGET)))


if __name__ == '__main__':
    main()
