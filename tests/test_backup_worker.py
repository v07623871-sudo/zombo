"""The separate Railway backup job must never leak credentials or delete unrelated objects."""
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('worker', Path(__file__).parents[1] / 'ops' / 'backup' / 'worker.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def test_backup_command_has_no_database_password(monkeypatch):
    monkeypatch.delenv('PGPASSWORD', raising=False)
    args, env = worker.database_command('postgresql+psycopg://zombo:top%40secret@host.internal:5432/game?sslmode=require')
    assert args == ['--host','host.internal','--port','5432','--username','zombo','--dbname','game']
    assert env['PGPASSWORD'] == 'top@secret'
    assert env['PGSSLMODE'] == 'require'
    assert 'secret' not in repr(args)
    with pytest.raises(ValueError):worker.database_command('sqlite:///game.db')


def test_backup_retention_never_deletes_other_prefixes():
    before = datetime.now(timezone.utc) - timedelta(days=45)
    recent = datetime.now(timezone.utc) - timedelta(days=1)
    deleted=[]
    class Paginator:
        def paginate(self, **kwargs):
            yield {'Contents':[
                {'Key':worker.PREFIX+'old.dump','LastModified':before},
                {'Key':worker.PREFIX+'recent.dump','LastModified':recent},
                {'Key':worker.PREFIX+'notes.txt','LastModified':before},
                {'Key':'other/old.dump','LastModified':before},
            ]}
    class FakeS3:
        def get_paginator(self, operation):
            assert operation=='list_objects_v2'
            return Paginator()
        def delete_object(self, **kw):deleted.append(kw['Key'])
    out = worker.retention(FakeS3(),'zombo-test',cutoff=datetime.now(timezone.utc)-timedelta(days=30))
    assert out==1 and deleted==[worker.PREFIX+'old.dump']
