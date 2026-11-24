"""Real RSA-signed ID tokens with a controlled Google certificate transport."""
import json
from datetime import timedelta
from types import SimpleNamespace
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.main import app
from app.db.session import SessionLocal
from app.models.entities import GoogleIdentity, User, Patient, now
from app.routers import google_auth as google
from conftest import PATIENT_TEST_PASSWORD, ADMIN_TEST_PASSWORD, register_patient
from test_livekit_consultations import doctor_client

ORIGIN = {'Origin': 'http://localhost:5188'}
CLIENT_ID = 'controlled-client.apps.googleusercontent.com'

@pytest.fixture
def provider(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    def request(*args, **kwargs):
        return SimpleNamespace(status=200, data=json.dumps({'test-key': public}).encode())
    monkeypatch.setattr(google, 'GOOGLE_CLIENT_ID', CLIENT_ID)
    monkeypatch.setattr(google, 'GoogleRequest', lambda: request)
    def token(challenge_nonce, **overrides):
        claims = dict(iss='https://accounts.google.com', aud=CLIENT_ID,
            exp=int((now() + timedelta(minutes=5)).timestamp()), iat=int(now().timestamp()),
            sub='google-sub-patient', email='new-google@example.com', email_verified=True,
            name='Paciente Google', nonce=challenge_nonce)
        claims.update(overrides)
        return jwt.encode(claims, key, algorithm='RS256', headers={'kid': 'test-key'})
    return token

def challenge(client, purpose='LOGIN', password=None):
    response = client.post('/api/auth/google/challenge', headers=ORIGIN,
        json={'purpose': purpose, **({'current_password': password} if password else {})})
    assert response.status_code == 200, response.text
    return response.json()['challenge']

def exchange(client, nonce, token):
    return client.post('/api/auth/google/exchange', headers=ORIGIN, json={'challenge': nonce, 'credential': token})

def test_new_google_patient_registration_and_login(client, provider):
    nonce = challenge(client)
    verified = exchange(client, nonce, provider(nonce))
    assert verified.status_code == 200 and verified.json()['registration_required']
    assert client.post('/api/auth/google/register', headers=ORIGIN, json={'challenge': nonce, 'document_number': 'bad', 'phone': '3001234567', 'privacy_accepted': True}).status_code == 422
    created = client.post('/api/auth/google/register', headers=ORIGIN, json={'challenge': nonce, 'document_number': '1122334455', 'phone': '3001234567', 'privacy_accepted': True})
    assert created.status_code == 201, created.text
    assert created.json()['role'] == 'PATIENT' and created.json()['redirect_to'] == '/portal'
    assert exchange(client, nonce, provider(nonce)).status_code == 409
    assert client.get('/api/doctor/dashboard').status_code == 403
    assert client.get('/api/admin/dashboard').status_code == 403
    assert client.post('/api/auth/logout').status_code == 200
    login_nonce = challenge(client)
    logged_in = exchange(client, login_nonce, provider(login_nonce))
    assert logged_in.json()['redirect_to'] == '/portal'
    assert client.get('/api/auth/me').json()['has_document'] is True
    with SessionLocal() as db:
        identity = db.get(GoogleIdentity, 'google-sub-patient')
        assert db.get(Patient, identity.user_id).document_number == '1122334455'

@pytest.mark.parametrize('overrides', [
    {'aud': 'another-client'}, {'iss': 'https://evil.example'}, {'exp': 1},
    {'email_verified': False}, {'sub': ''}, {'nonce': 'attacker-nonce'},
])
def test_invalid_google_claims_rejected(client, provider, overrides):
    nonce = challenge(client)
    assert exchange(client, nonce, provider(nonce, **overrides)).status_code == 401

def test_bad_signature_cookie_and_origin_rejected(client, provider):
    nonce = challenge(client)
    bad = jwt.encode({'sub': 'attacker'}, 'not-the-key-' * 4, algorithm='HS256')
    assert exchange(client, nonce, bad).status_code == 401
    assert client.post('/api/auth/google/challenge', json={'purpose': 'LOGIN'}).status_code == 403
    client.cookies.delete(google.COOKIE)
    assert exchange(client, nonce, provider(nonce)).status_code == 403

def test_existing_email_requires_password_link_and_duplicate_sub_rejected(patient, provider):
    nonce = challenge(patient)
    assert exchange(patient, nonce, provider(nonce, email='paciente@vitalsync.demo')).status_code == 409
    assert patient.post('/api/auth/google/challenge', headers=ORIGIN, json={'purpose': 'LINK', 'current_password': 'incorrect-password'}).status_code == 403
    nonce = challenge(patient, 'LINK', PATIENT_TEST_PASSWORD)
    linked = exchange(patient, nonce, provider(nonce, email='personal@example.com'))
    assert linked.json()['linked'] is True
    assert patient.get('/api/auth/me').json()['email'] == 'paciente@vitalsync.demo'
    doctor, _, _ = doctor_client()
    try:
        from test_livekit_consultations import DOCTOR_PASSWORD
        assert doctor.post('/api/auth/google/challenge', headers=ORIGIN, json={'purpose': 'LINK', 'current_password': DOCTOR_PASSWORD}).status_code == 403
    finally: doctor.close()

    with TestClient(app) as other:
        password='OtroPacienteSeguro123!'
        assert register_patient(other,'Otro Paciente','other-google@example.com',password).status_code==201
        nonce=challenge(other,'LINK',password)
        assert exchange(other,nonce,provider(nonce)).status_code==409

def test_doctor_google_denied_existing_identity_preserved(client, provider):
    from test_livekit_consultations import DOCTOR_PASSWORD
    doctor, user_id, _ = doctor_client()
    try:
        assert doctor.post('/api/auth/google/challenge', headers=ORIGIN, json={'purpose':'LINK','current_password':DOCTOR_PASSWORD}).status_code == 403
        with SessionLocal.begin() as db:
            db.add(GoogleIdentity(sub='doctor-sub', user_id=user_id, email='personal-doctor@gmail.com'))
        nonce = challenge(doctor)
        assert exchange(doctor, nonce, provider(nonce, sub='doctor-sub')).status_code == 403
        assert doctor.get('/api/doctor/dashboard').status_code == 200
        assert doctor.get('/api/appointments').status_code == 403
        with SessionLocal() as db: assert db.get(GoogleIdentity, 'doctor-sub') is not None
        assert client.post('/api/auth/login', json={'email':'admin@vitalsync.demo','password':ADMIN_TEST_PASSWORD}).status_code == 200
        assert client.post('/api/auth/google/challenge', headers=ORIGIN, json={'purpose':'LINK','current_password':ADMIN_TEST_PASSWORD}).status_code == 403
        nonce = challenge(client)
        assert exchange(client, nonce, provider(nonce, email='admin@vitalsync.demo')).status_code == 403
    finally: doctor.close()


def test_link_challenge_is_bound_to_authenticated_session(patient, provider):
    nonce = challenge(patient, 'LINK', PATIENT_TEST_PASSWORD)
    patient.post('/api/auth/logout')
    assert exchange(patient, nonce, provider(nonce)).status_code == 401


def test_patient_unlink_requires_password_and_preserves_traditional_login(patient, provider):
    nonce = challenge(patient, 'LINK', PATIENT_TEST_PASSWORD)
    assert exchange(patient, nonce, provider(nonce)).status_code == 200
    wrong = patient.post('/api/auth/google/unlink', headers=ORIGIN,
        json={'current_password': 'wrong-password', 'reason': 'Desvinculación de prueba del titular'})
    assert wrong.status_code == 403
    assert patient.get('/api/auth/google/identity').json()['linked'] is True
    response = patient.post('/api/auth/google/unlink', headers=ORIGIN,
        json={'current_password': PATIENT_TEST_PASSWORD, 'reason': 'Desvinculación de prueba del titular'})
    assert response.status_code == 200
    assert patient.get('/api/auth/google/identity').json()['linked'] is False
    patient.post('/api/auth/logout')
    assert patient.post('/api/auth/login', json={'email': 'paciente@vitalsync.demo', 'password': PATIENT_TEST_PASSWORD}).status_code == 200
