"""One-shot restore drill into a disposable, isolated PostgreSQL database.

NEVER point RESTORE_TEST_URL at production. The script rejects a matching
production host/database pair before reading or writing any SQL.
"""
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from worker import PREFIX, database_command


def restore_target_is_safe(source_url: str, target_url: str):
    source = urlsplit(source_url.replace('postgresql+psycopg://', 'postgresql://', 1))
    target = urlsplit(target_url.replace('postgresql+psycopg://', 'postgresql://', 1))
    if not target.hostname or not target.path.strip('/'):
        raise ValueError('Restore target database must be explicitly configured')
    if (source.hostname or '').lower() == (target.hostname or '').lower():
        raise ValueError('Restore target must use a different PostgreSQL host from production')
    return True


def run():
    import boto3
    from botocore.config import Config
    keys = ['DATABASE_URL','RESTORE_TEST_URL','S3_ENDPOINT','S3_BUCKET','S3_REGION',
            'S3_ACCESS_KEY_ID','S3_SECRET_ACCESS_KEY']
    missing = [k for k in keys if not os.getenv(k)]
    if missing:
        raise RuntimeError('Missing restore drill configuration: ' + ', '.join(missing))
    restore_target_is_safe(os.environ['DATABASE_URL'], os.environ['RESTORE_TEST_URL'])
    s3 = boto3.client('s3', endpoint_url=os.environ['S3_ENDPOINT'],
        region_name=os.environ['S3_REGION'], aws_access_key_id=os.environ['S3_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['S3_SECRET_ACCESS_KEY'],
        config=Config(s3={'addressing_style':os.getenv('S3_ADDRESSING_STYLE','virtual')}))
    bucket = os.environ['S3_BUCKET']
    listing = s3.list_objects_v2(Bucket=bucket, Prefix=PREFIX)
    candidates = [obj for obj in listing.get('Contents', [])
                  if obj['Key'].startswith(PREFIX) and obj['Key'].endswith('.dump')]
    if not candidates:
        raise RuntimeError('No verified PostgreSQL backup found in S3')
    chosen = max(candidates,key=lambda x:x['LastModified'])
    args,env = database_command(os.environ['RESTORE_TEST_URL'])
    # Important: db password only in PGPASSWORD env, never in shell arguments.
    with tempfile.TemporaryDirectory() as work:
        path = Path(work) / 'restore-test.dump'
        s3.download_file(bucket, chosen['Key'], str(path))
        subprocess.run(['pg_restore','--list',str(path)],env=env,check=True,capture_output=True,timeout=90)
        subprocess.run(['pg_restore','--exit-on-error','--no-owner','--no-acl',
                        *args, str(path)],env=env,check=True,capture_output=True,timeout=1800)
        # Count players and confirm core financial tables exist. Avoid logging PII.
        check = "SELECT count(*) FROM players; SELECT count(*) FROM star_invoices; SELECT count(*) FROM payment_reviews;"
        out = subprocess.run(['psql',*args,'--no-psqlrc','--tuples-only','--command',check],
                             env=env,check=True,capture_output=True,text=True,timeout=60)
        counts = [int(s.strip()) for s in out.stdout.splitlines() if s.strip().isdigit()]
        if len(counts)!=3:
            raise RuntimeError('Restore sanity check did not return all three table counts')
        print(f'Restore drill succeeded: downloaded and restored {path.stat().st_size} bytes; '
              f'checked 3 critical tables, player rows: {counts[0]}.')

if __name__ == '__main__':
    run()
