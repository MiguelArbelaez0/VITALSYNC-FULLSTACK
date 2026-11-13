import os
import subprocess
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text, select

# Solo se permite una BD de pruebas separada; nunca truncar la de demostración.
os.environ['DATABASE_URL'] = os.getenv('TEST_DATABASE_URL', 'postgresql+psycopg://vitalsync:local_demo_change_me@db:5432/vitalsync_test')
os.environ['DEMO_MODE'] = 'true'
from app.main import app
from app.db.session import SessionLocal, engine
from app.models.entities import *
from app.seed import seed
from app.core.security import passwords
ADMIN_TEST_PASSWORD=uuid4().hex+'Aa1!'

@pytest.fixture(scope='session', autouse=True)
def migrated_database():
    assert engine.url.database == 'vitalsync_test', 'Las pruebas requieren la base aislada vitalsync_test'
    subprocess.run(['alembic', 'upgrade', 'head'], check=True)

@pytest.fixture(autouse=True)
def clean_database(migrated_database):
    with engine.begin() as connection:
        tables = ', '.join('"' + t.name + '"' for t in Base.metadata.sorted_tables)
        connection.execute(text(f'TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE'))
    seed()
    with SessionLocal.begin() as db:
        db.scalar(select(User).where(User.role=='ADMIN')).password_hash=passwords.hash(ADMIN_TEST_PASSWORD)

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture
def patient(client):
    r = client.post('/api/auth/login', json={'email':'paciente@vitalsync.demo','password':'Paciente2026!'})
    assert r.status_code == 200, r.text
    return client

def registration_data(name, email, password, document_number=None, **overrides):
    parts = name.strip().split(maxsplit=1)
    document = document_number if document_number is not None else str(uuid4().int % 10_000_000_000).zfill(10)
    return {
        'given_names': parts[0],
        'surnames': parts[1] if len(parts) > 1 else 'Paciente',
        'document_type': 'CC',
        'document_number': document,
        'email': email,
        'phone': '+57 300 123 4567',
        'password': password,
        'privacy_accepted': True,
        **overrides,
    }

def register_patient(client, name, email, password, document_number=None, **overrides):
    return client.post(
        '/api/auth/register',
        json=registration_data(name, email, password, document_number, **overrides),
    )

def activate(c, plan_name='Básico', status='APPROVED'):
    plan = next(p for p in c.get('/api/plans').json() if p['name'] == plan_name)
    r = c.post('/api/payments', json={'kind':'PLAN','target_id':plan['id'],'status':status,'idempotency_key':uuid4().hex})
    assert r.status_code == 200, r.text
    return r.json()

def free_slot(c, doctor_id=1):
    return next(s for s in c.get(f'/api/doctors/{doctor_id}/availability').json() if s['available'])

def hold(c, doctor_id=1):
    r = c.post('/api/holds', json={'availability_id':free_slot(c, doctor_id)['id']})
    assert r.status_code == 201, r.text
    return r.json()

def copay(c, h, status='APPROVED', key=None):
    return c.post('/api/payments', json={'kind':'COPAY','target_id':h['id'],'status':status,'idempotency_key':key or uuid4().hex})

def appointment(c, plan_name='Básico'):
    activate(c, plan_name)
    h = hold(c)
    if h['copay']:
        assert copay(c,h).status_code == 200
    r = c.post(f"/api/holds/{h['id']}/confirm")
    assert r.status_code == 200, r.text
    return c.get('/api/appointments/'+str(r.json()['id'])).json()
