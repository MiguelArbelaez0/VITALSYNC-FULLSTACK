"""Rebuild only a fresh audit database. Credentials go to a private file."""
import json, os, secrets
from pathlib import Path
from sqlalchemy import text, select
from app.db.session import engine, SessionLocal, Base
from app.models.entities import User
from app.seed import seed
from app.services.doctor_accounts import provision, temporary_password
from app.services.clinical_history import seed_histories
from app.core.security import passwords

def main():
    test_database = os.getenv('VITALSYNC_TEST_DATABASE_NAME', 'vitalsync_test_audit_unconfigured')
    assert engine.url.database == test_database and test_database.startswith('vitalsync_test_audit_'), 'Never reset an existing application or test database'
    with engine.begin() as db:
        tables=', '.join('"'+t.name+'"' for t in Base.metadata.sorted_tables)
        db.execute(text(f'TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE'))
    seed()
    with SessionLocal.begin() as db:
        admin=db.scalar(select(User).where(User.role=='ADMIN'))
        result=provision(db,admin)
        patient = db.scalar(select(User).where(User.email=='paciente@vitalsync.demo'))
        patient_secret=secrets.token_urlsafe(32)+'Aa1!'
        patient.password_hash = passwords.hash(patient_secret)
        result['patient']={'email':patient.email,'password':patient_secret}
        admin_secret=secrets.token_urlsafe(24)+'Aa1!'
        admin.password_hash=passwords.hash(admin_secret)
        result['admin']={'email':admin.email,'password':admin_secret}
        seed_histories(db,True)
        # This account was JUST recreated in the disposable database, never an existing user.
        doctor=db.scalar(select(User).where(User.email=='medico@vitalsync.demo'))
        secret=temporary_password();doctor.password_hash=passwords.hash(secret)
        result['legacy']={'email':doctor.email,'password':secret}
        with os.fdopen(os.open('/tmp/e2e.credentials.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as f:
            json.dump(result,f)
    print('Disposable database prepared; credentials exported privately')
if __name__=='__main__':main()
