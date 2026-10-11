"""Add missing tables without altering or dropping existing player data.

Run after making a PostgreSQL backup. Existing columns are checked first so
deployment fails clearly if the live schema has drifted from these models.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app  # noqa: F401 - imports every module registering SQLAlchemy tables
from sqlalchemy import inspect
from models import Base, engine


def migrate(connection):
    inspector = inspect(connection)
    existing = set(inspector.get_table_names())
    for name, table in Base.metadata.tables.items():
        if name not in existing:
            continue
        live = {column['name'] for column in inspector.get_columns(name)}
        missing = set(table.columns.keys()) - live
        if missing:
            raise RuntimeError(f'{name}: missing columns {sorted(missing)}; stop and review schema before deploying')
    Base.metadata.create_all(bind=connection, checkfirst=True)
    created = sorted(set(inspect(connection).get_table_names()) - existing)
    return created


if __name__ == '__main__':
    with engine.begin() as conn:
        print('New tables:', ', '.join(migrate(conn)) or 'none')
