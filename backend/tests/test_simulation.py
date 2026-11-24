from datetime import timedelta

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import Appointment, Payment, SimulationRoom, now
from app.routers import simulation
from test_livekit_consultations import configure_livekit, doctor_client
from conftest import register_patient
from test_admin_portal import login_admin


def test_shared_room_is_private_rejoinable_and_independent(patient, monkeypatch):
    configure_livekit(monkeypatch)
    closed = []
    monkeypatch.setattr(simulation.livekit, 'close_room', closed.append)
    response = patient.post('/api/simulation/rooms', json={'shared': True})
    assert response.status_code == 201, response.text
    room = response.json()
    path = f"/api/simulation/rooms/{room['id']}"
    with TestClient(app) as outsider:
        assert outsider.post(path + '/token').status_code == 401
        assert register_patient(outsider, 'Paciente Externo', 'outside@example.com', 'ExternalPass123').status_code == 201
        assert outsider.post('/api/simulation/join', json={'invitation': room['invitation']}).status_code == 403
    doctor, _, _ = doctor_client()
    with doctor:
        assert doctor.post(path + '/token').status_code == 404
        assert doctor.post('/api/simulation/join', json={'invitation': 'incorrecta'}).status_code == 404
        assert doctor.post('/api/simulation/join', json={'invitation': room['invitation']}).json()['id'] == room['id']
        for _ in range(2):
            token = doctor.post(path + '/token').json()['token']
            claims = jwt.decode(token, options={'verify_signature': False})
            assert claims['video']['room'] == 'simulation-' + room['id']
            assert claims['exp'] - claims['nbf'] <= 45
        assert doctor.post(path + '/end').status_code == 404
        assert patient.post(path + '/end').status_code == 200
        assert doctor.post(path + '/token').status_code == 409
    assert closed == ['simulation-' + room['id']]
    with SessionLocal() as db:
        for model in (Appointment, Payment):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_solo_expiration_limits_and_demo_gate(patient, monkeypatch):
    configure_livekit(monkeypatch)
    room = patient.post('/api/simulation/rooms', json={}).json()
    assert room['invitation'] is None
    assert patient.post('/api/simulation/rooms', json={}).status_code == 409
    path = f"/api/simulation/rooms/{room['id']}/token"
    assert patient.post(path).status_code == 200
    with SessionLocal.begin() as db:
        db.get(SimulationRoom, room['id']).expires_at = now() - timedelta(seconds=1)
    assert patient.post(path).status_code == 409
    for _ in range(8):
        assert patient.post('/api/simulation/join', json={'invitation': 'incorrecta'}).status_code == 404
    assert patient.post('/api/simulation/join', json={'invitation': 'incorrecta'}).status_code == 429
    monkeypatch.setattr(simulation, 'DEMO_MODE', False)
    assert patient.post('/api/simulation/rooms', json={}).status_code == 403


def test_staff_can_authorize_fictitious_patient_for_practice_only(client, monkeypatch):
    configure_livekit(monkeypatch)
    login_admin(client)
    with TestClient(app) as patient:
        registered = register_patient(patient, 'Paciente Ficticio', 'practice@example.com', 'PracticePass123')
        assert registered.status_code == 201
        path = f"/api/admin/patients/{registered.json()['id']}/simulation-access"
        payload = {'reason': 'Cuenta ficticia para práctica académica'}
        assert patient.post(path, json=payload).status_code == 403
        assert patient.post('/api/simulation/rooms', json={}).status_code == 403
        assert client.post(path, json=payload).status_code == 200
        assert client.post(path, json=payload).status_code == 200
        assert patient.get('/api/auth/me').json()['demo_patient'] is False
        assert patient.post('/api/simulation/rooms', json={}).status_code == 201


def test_academic_doctor_cohort_is_idempotent_and_keeps_existing_credentials():
    from app.models.entities import Doctor, User
    from app.provision_doctors import add_academic_profiles
    from app.services.doctor_accounts import provision

    with SessionLocal.begin() as db:
        actor = db.scalar(select(User).where(User.role == 'ADMIN'))
        before = {u.id: u.password_hash for u in db.scalars(select(User))}
        add_academic_profiles(db, actor)
        add_academic_profiles(db, actor)
        assert db.scalar(select(func.count()).select_from(Doctor)) == 15
        issued = provision(db, actor)['new_credentials']
        assert len({item['temporary_password'] for item in issued}) == len(issued)
        assert not provision(db, actor)['new_credentials']
        assert {id: db.get(User, id).password_hash for id in before} == before
