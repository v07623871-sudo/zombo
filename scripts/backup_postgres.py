"""Create and validate a PostgreSQL custom-format backup with pg_dump.

Reads DATABASE_URL from the environment; never prints the password. Requires
pg_dump and pg_restore from PostgreSQL client tools in PATH.
"""
import argparse
import os
from pathlib import Path
import subprocess
from urllib.parse import unquote, urlsplit


def backup(output: Path, database_url: str):
    parsed = urlsplit(database_url.replace('postgresql+psycopg://', 'postgresql://', 1))
    if parsed.scheme not in ('postgresql', 'postgres') or not parsed.path.strip('/'):
        raise ValueError('DATABASE_URL must point to PostgreSQL')
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f'Refusing to overwrite {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + '.partial')
    env = os.environ.copy()
    if parsed.password:
        env['PGPASSWORD'] = unquote(parsed.password)
    if parsed.query:
        from urllib.parse import parse_qs
        sslmode = parse_qs(parsed.query).get('sslmode', [None])[0]
        if sslmode:
            env['PGSSLMODE'] = sslmode
    base = ['--host', parsed.hostname or 'localhost', '--port', str(parsed.port or 5432),
            '--username', unquote(parsed.username or ''), '--dbname', unquote(parsed.path.lstrip('/'))]
    try:
        subprocess.run(['pg_dump', *base, '--format=custom', '--no-owner', '--no-acl', '--file', str(temp)],
                       env=env, check=True, capture_output=True)
        subprocess.run(['pg_restore', '--list', str(temp)], env=env, check=True, capture_output=True)
        temp.replace(output)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    url = os.getenv('DATABASE_URL', '')
    print('Backup validated:', backup(args.output, url))
