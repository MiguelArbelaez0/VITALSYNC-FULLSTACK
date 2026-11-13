"""Read-only fingerprints for verifying preservation; emits no row values or password hashes."""
import json
from sqlalchemy import text
from app.db.session import engine
out={}
with engine.connect() as db:
 for name in db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename NOT IN ('sessions','alembic_version') ORDER BY tablename")).scalars():
  out[name]=list(db.execute(text('SELECT md5(to_jsonb(r)::text) FROM "'+name+'" r ORDER BY 1')).scalars())
print(json.dumps(out))
