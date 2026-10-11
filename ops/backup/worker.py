"""Railway cron backup job: pg_dump -> verify -> private S3-compatible bucket.

No plaintext database dump or credentials are stored in GitHub or committed to
Railway volumes. This job runs to completion and exits nonzero on any failure.
Restoration on a *separate* PostgreSQL instance must be tested by an operator.
"""
import os
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit


PREFIX = 'zombo-postgres/'


def database_command(url):
    parsed = urlsplit(url.replace('postgresql+psycopg://', 'postgresql://', 1))
    if parsed.scheme not in ('postgres', 'postgresql') or not parsed.hostname or not parsed.path.strip('/'):
        raise ValueError('PostgreSQL DATABASE_URL is required')
    env = os.environ.copy()
    if parsed.password:
        env['PGPASSWORD'] = unquote(parsed.password)
    if 'sslmode' in parse_qs(parsed.query):
        env['PGSSLMODE'] = parse_qs(parsed.query)['sslmode'][0]
    args = ['--host', parsed.hostname, '--port', str(parsed.port or 5432),
            '--username', unquote(parsed.username or ''),
            '--dbname', unquote(parsed.path.lstrip('/'))]
    return args, env


def retention(client, bucket, *, cutoff, prefix=PREFIX):
    """Prune only previously uploaded backups in our private prefix."""
    paginator = client.get_paginator('list_objects_v2')
    removed = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get('Contents', []):
            if obj['Key'].startswith(prefix) and obj['Key'].endswith('.dump') and obj['LastModified'] < cutoff:
                client.delete_object(Bucket=bucket, Key=obj['Key'])
                removed += 1
    return removed


def run():
    required = ['DATABASE_URL', 'S3_ENDPOINT', 'S3_BUCKET', 'S3_REGION',
                'S3_ACCESS_KEY_ID', 'S3_SECRET_ACCESS_KEY']
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise RuntimeError('Missing backup configuration variables: ' + ', '.join(missing))
    args, env = database_command(os.environ['DATABASE_URL'])
    import boto3
    from botocore.config import Config
    client = boto3.client('s3', endpoint_url=os.environ['S3_ENDPOINT'],
        region_name=os.environ['S3_REGION'], aws_access_key_id=os.environ['S3_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['S3_SECRET_ACCESS_KEY'],
        config=Config(s3={'addressing_style':os.getenv('S3_ADDRESSING_STYLE','virtual')},
                      retries={'max_attempts':3,'mode':'standard'}))
    bucket = os.environ['S3_BUCKET']
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    key = f'{PREFIX}{stamp}.dump'
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'zombo.dump'
        subprocess.run(['pg_dump', *args, '--format=custom', '--no-owner', '--no-acl',
                        '--file', str(path)], env=env, capture_output=True, check=True,
                        timeout=3600)
        if path.stat().st_size == 0:
            raise RuntimeError('pg_dump produced an empty file')
        subprocess.run(['pg_restore', '--list', str(path)], env=env,
                       check=True, capture_output=True, timeout=90)
        client.upload_file(str(path), bucket, key)
        head = client.head_object(Bucket=bucket, Key=key)
        if int(head.get('ContentLength', -1)) != path.stat().st_size:
            raise RuntimeError('Uploaded backup size mismatch; original retained for retry')
        print(f'Backup uploaded and verified: s3://{bucket}/{key} ({path.stat().st_size} bytes)')
    keep_days = max(7, min(365, int(os.getenv('BACKUP_RETENTION_DAYS', '30'))))
    removed = retention(client, bucket, cutoff=datetime.now(timezone.utc)-timedelta(days=keep_days))
    print(f'Backup retention: {keep_days} days; removed old objects: {removed}')


if __name__ == '__main__':
    run()
