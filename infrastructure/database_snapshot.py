"""Read-only table counts/digests; pipe into the unified backend Python interpreter.

Get-Content infrastructure/database_snapshot.py -Raw | docker compose -p vitalsync exec -T backend python -
No row contents, credentials, or session tokens are emitted.
"""
import json
from sqlalchemy import text
from app.db.session import engine

result = {}
with engine.connect() as connection:
    tables = connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'sessions' ORDER BY tablename")).scalars().all()
    for table in tables:
        quoted = '"' + table.replace('"', '""') + '"'
        sql = "SELECT count(*), md5(COALESCE(jsonb_agg(to_jsonb(r) ORDER BY to_jsonb(r)::text)::text,'[]')) FROM " + quoted + ' r'
        row = connection.execute(text(sql)).one()
        result[table] = {'count': row[0], 'digest': row[1]}
print(json.dumps(result, sort_keys=True))
