from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.security import passwords
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import Appointment, DoctorAccount, DoctorCredentialState, LiveKitRoomEvent, StatusHistory, User, VirtualConsultation, now
from app.seed import seed
from app.services import livekit_consultations as livekit
from conftest import activate, register_patient

DOCTOR_PASSWORD = 'DoctorVideo2026!'


def configure_livekit(monkeypatch):
    monkeypatch.setattr(livekit, 'LIVEKIT_ENABLED', True)
    monkeypatch.setattr(livekit, 'LIVEKIT_API_KEY', 'vitalsync-test-key')
    monkeypatch.setattr(livekit, 'LIVEKIT_API_SECRET', 'test-secret-not-for-use-in-production-000000000')
    monkeypatch.setattr(livekit, 'LIVEKIT_PUBLIC_URL', 'ws://localhost:7880')
    monkeypatch.setattr(livekit, 'LIVEKIT_TOKEN_TTL_SECONDS', 600)


def reserve_virtual(client, doctor_id=2, move_to_current=False):
    activate(client, 'Premium')
    slot = next(s for s in client.get(f'/api/doctors/{doctor_id}/availability?modality=VIRTUAL').json() if s['available'])
    hold = client.post('/api/holds', json={'availability_id': slot['id'], 'modality': 'VIRTUAL'})
    assert hold.status_code == 201, hold.text
    confirmed = client.post(f"/api/holds/{hold.json()['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    appointment_id = confirmed.json()['id']
    if move_to_current:
        with SessionLocal.begin() as db:
            appointment = db.get(Appointment, appointment_id)
            appointment.starts_at = now() - timedelta(seconds=10)
            appointment.ends_at = now() + timedelta(minutes=29)
    return appointment_id


def doctor_client():
    with SessionLocal.begin() as db:
        user = db.scalar(select(User).where(User.email == 'medico@vitalsync.demo'))
        user.password_hash = passwords.hash(DOCTOR_PASSWORD)
        state = db.get(DoctorCredentialState, user.id)
        if state:
            state.must_change_password = False
        doctor_id = db.scalar(select(DoctorAccount.doctor_id).where(DoctorAccount.user_id == user.id))
    client = TestClient(app)
    response = client.post('/api/auth/login', json={'email': 'medico@vitalsync.demo', 'password': DOCTOR_PASSWORD})
    assert response.status_code == 200, response.text
    return client, user.id, doctor_id


def test_patient_token_is_short_lived_and_confined_to_owned_appointment(patient, monkeypatch):
    configure_livekit(monkeypatch)
    monkeypatch.setattr(livekit, 'TELECONSULT_ROOM_OPEN_MINUTES', 10080)
    appointment_id = reserve_virtual(patient, doctor_id=2)

    response = patient.post(f'/api/appointments/{appointment_id}/livekit-token', json={})
    assert response.status_code == 200, response.text
    claims = jwt.decode(response.json()['token'], options={'verify_signature': False})
    with SessionLocal() as db:
        room = db.get(VirtualConsultation, appointment_id).livekit_room_name
    assert claims['sub'].startswith('user:')
    assert claims['video']['room'] == room
    assert claims['video']['roomJoin'] is True
    assert claims['video']['roomCreate'] is False
    assert claims['video']['roomAdmin'] is False
    assert claims['video']['roomRecord'] is False
    assert claims['video']['canPublishData'] is False
    assert claims['exp'] - claims['nbf'] <= 600
    assert 'test-secret' not in response.text

    with TestClient(app) as outsider:
        register_patient(outsider, 'Paciente Externo', 'lk-outsider@example.com', 'PacienteSeguro2026!')
        denied = outsider.post(f'/api/appointments/{appointment_id}/livekit-token', json={})
    assert denied.status_code == 404


def test_livekit_token_respects_appointment_entry_window(patient, monkeypatch):
    configure_livekit(monkeypatch)
    appointment_id = reserve_virtual(patient, doctor_id=2)
    monkeypatch.setattr(livekit, 'TELECONSULT_ROOM_OPEN_MINUTES', 5)
    response = patient.post(f'/api/appointments/{appointment_id}/livekit-token', json={})
    assert response.status_code == 409
    assert 'cinco minutos' in response.json()['detail']


def test_livekit_webhooks_track_participants_and_doctor_finalization_is_idempotent(patient, monkeypatch):
    configure_livekit(monkeypatch)
    appointment_id = reserve_virtual(patient, doctor_id=2, move_to_current=True)
    with SessionLocal() as db:
        appointment = db.get(Appointment, appointment_id)
        room_name = db.get(VirtualConsultation, appointment_id).livekit_room_name
        patient_id = appointment.patient_id
        doctor_user_id = db.scalar(select(DoctorAccount.user_id).where(DoctorAccount.doctor_id == appointment.doctor_id))

    event = SimpleNamespace()
    class Receiver:
        def __init__(self, *_args): pass
        def receive(self, _body, _authorization): return event
    monkeypatch.setattr(livekit.api, 'WebhookReceiver', Receiver)

    def deliver(event_id, identity, event_type='participant_joined'):
        event.id = event_id
        event.event = event_type
        event.room = SimpleNamespace(name=room_name)
        event.participant = SimpleNamespace(identity=identity)
        with SessionLocal.begin() as db:
            return livekit.process_webhook(db, b'{}', 'Bearer signed-by-livekit')

    assert deliver('event-patient-joined', f'user:{patient_id}')['connection_state'] == 'WAITING'
    assert deliver('event-doctor-joined', f'user:{doctor_user_id}')['connection_state'] == 'CONNECTED'
    assert deliver('event-doctor-joined', f'user:{doctor_user_id}')['duplicate'] is True
    assert deliver('event-patient-left-temp', f'user:{patient_id}', 'participant_left')['connection_state'] == 'RECONNECTING'
    assert deliver('event-patient-rejoined', f'user:{patient_id}')['connection_state'] == 'CONNECTED'
    with SessionLocal() as db:
        assert db.get(Appointment, appointment_id).status == 'IN_PROGRESS'
        assert db.get(VirtualConsultation, appointment_id).status == 'EN_ATENCION'
        assert db.scalar(select(func.count()).select_from(LiveKitRoomEvent).where(LiveKitRoomEvent.appointment_id == appointment_id)) == 4

    doctor, _user_id, doctor_id = doctor_client()
    monkeypatch.setattr(livekit, 'close_room', lambda _room: True)
    try:
        done = doctor.post(f'/api/doctor/appointments/{appointment_id}/livekit-finalize', json={})
        assert done.status_code == 200, done.text
        assert done.json()['appointment_status'] == 'ATTENDED'
        assert done.json()['idempotent'] is False
        repeated = doctor.post(f'/api/doctor/appointments/{appointment_id}/livekit-finalize', json={})
        assert repeated.status_code == 200
        assert repeated.json()['idempotent'] is True
        assert done.json()['started_at'] and done.json()['finalized_at']
    finally:
        doctor.close()

    # Delayed provider events are auditable but cannot reopen a terminal call.
    with SessionLocal() as db:
        disconnect_history_count = db.scalar(select(func.count()).select_from(StatusHistory).where(
            StatusHistory.appointment_id == appointment_id,
            StatusHistory.status == 'LIVEKIT_PATIENT_DISCONNECTED',
        ))
    stale = deliver('event-patient-left-after-finalization', f'user:{patient_id}', 'participant_left')
    assert stale['terminal'] is True
    with SessionLocal() as db:
        assert db.get(Appointment, appointment_id).status == 'ATTENDED'
        assert db.get(VirtualConsultation, appointment_id).status == 'FINALIZADA'
        assert db.get(VirtualConsultation, appointment_id).livekit_connection_state == 'DISCONNECTED'
        assert db.scalar(select(func.count()).select_from(StatusHistory).where(
            StatusHistory.appointment_id == appointment_id,
            StatusHistory.status == 'LIVEKIT_PATIENT_DISCONNECTED',
        )) == disconnect_history_count

    assert patient.post(f'/api/appointments/{appointment_id}/livekit-token', json={}).status_code == 409
    assert patient.get('/api/appointments?view=completed').json()[0]['status'] == 'ATTENDED'


def test_patient_cannot_finalize_livekit_consultation(patient, monkeypatch):
    configure_livekit(monkeypatch)
    appointment_id = reserve_virtual(patient, doctor_id=2, move_to_current=True)
    with SessionLocal.begin() as db:
        appointment = db.get(Appointment, appointment_id)
        appointment.status = 'IN_PROGRESS'
        db.get(VirtualConsultation, appointment_id).status = 'EN_ATENCION'
    denied = patient.post(f'/api/doctor/appointments/{appointment_id}/livekit-finalize', json={})
    assert denied.status_code in (401, 403)


def test_room_close_retries_transient_livekit_errors(monkeypatch):
    calls = {'count': 0}

    class RoomClient:
        async def delete_room(self, _request):
            calls['count'] += 1
            if calls['count'] < 3:
                raise RuntimeError('temporary LiveKit API failure')

    class FakeClient:
        room = RoomClient()
        async def aclose(self): pass

    monkeypatch.setattr(livekit.api, 'LiveKitAPI', lambda *_args, **_kwargs: FakeClient())
    assert livekit.close_room('room-retry-test') is True
    assert calls['count'] == 3
