from sqlalchemy import select
from app.models.entities import (
    Appointment, AppointmentSnapshot, AuditEvent, DemoPatient, Doctor,
    DoctorAccount, StatusHistory, User, VirtualConsultation,
)
from app.core.security import passwords
from app.services import livekit_consultations
from conftest import SessionLocal, register_patient


def link_all_demo_doctors():
    with SessionLocal.begin() as db:
        doctors = db.scalars(select(Doctor).order_by(Doctor.id).limit(5)).all()
        assert len(doctors) == 5
        for doctor in doctors:
            doctor.is_demo_doctor = True
            if not db.scalar(select(DoctorAccount.user_id).where(DoctorAccount.doctor_id == doctor.id)):
                user = User(email=f'demo-doctor-{doctor.id}@vitalsync.demo', name=doctor.name,
                            password_hash=passwords.hash('DemoTest123Aa'), role='DOCTOR')
                db.add(user)
                db.flush()
                db.add(DoctorAccount(user_id=user.id, doctor_id=doctor.id))


def test_demo_patient_can_start_idempotent_immediate_test_with_all_five_doctors(patient, monkeypatch):
    link_all_demo_doctors()
    monkeypatch.setattr(livekit_consultations, 'enabled', lambda: True)

    listed = patient.get('/api/demo/livekit/doctors')
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) == 5

    for doctor in listed.json():
        response = patient.post('/api/demo/livekit-sessions', json={'doctor_id': doctor['id']})
        assert response.status_code == 201, f"doctor {doctor['id']}: {response.text}"
        item = response.json()
        assert item['is_demo_test'] is True
        repeated = patient.post('/api/demo/livekit-sessions', json={'doctor_id': doctor['id']})
        assert repeated.status_code == 201, repeated.text
        assert repeated.json()['id'] == item['id']

        detail = patient.get(f"/api/appointments/{item['id']}")
        assert detail.status_code == 200, detail.text
        assert detail.json()['appointment_label'] == 'Consulta académica de prueba'
        assert detail.json()['plan'] == 'Consulta académica de prueba'
        assert detail.json()['copay'] == 0

        with SessionLocal.begin() as db:
            appointment = db.get(Appointment, item['id'])
            assert appointment and appointment.hold_id is None and appointment.plan_id is None
            assert appointment.payment_id is None and appointment.is_demo_test
            assert db.get(VirtualConsultation, item['id']).is_demo_test
            assert db.get(AppointmentSnapshot, item['id']).terms['origin'] == 'ACADEMIC_DEMO'
            assert db.scalar(select(AuditEvent.id).where(AuditEvent.action == 'DEMO_LIVEKIT_TEST_CREATED', AuditEvent.entity_id == item['id']))
            assert db.scalar(select(StatusHistory.id).where(StatusHistory.appointment_id == item['id']))
            # Keep patient and doctor slot exclusion intact while checking each test doctor.
            appointment.status = 'ATTENDED'
            db.get(VirtualConsultation, item['id']).status = 'FINALIZADA'


def test_regular_patient_cannot_use_demo_test_endpoint(patient, monkeypatch):
    monkeypatch.setattr(livekit_consultations, 'enabled', lambda: True)
    response = register_patient(patient, 'Paciente Normal', 'regular@vitalsync-demo.example.com', 'Patient123Aa')
    assert response.status_code == 201, response.text
    assert patient.post('/api/demo/livekit-sessions', json={'doctor_id': 1}).status_code == 403


def test_demo_doctor_is_blocked_when_another_patient_has_active_test(patient, monkeypatch):
    link_all_demo_doctors()
    monkeypatch.setattr(livekit_consultations, 'enabled', lambda: True)
    first = patient.post('/api/demo/livekit-sessions', json={'doctor_id': 1})
    assert first.status_code == 201, first.text

    other = register_patient(patient, 'Otra Paciente Demo', 'other-demo@vitalsync-demo.example.com', 'Patient123Bb')
    assert other.status_code == 201, other.text
    with SessionLocal.begin() as db:
        admin = db.scalar(select(User).where(User.role == 'ADMIN'))
        patient_id = other.json()['id']
        db.add(DemoPatient(patient_id=patient_id, source='OPERATOR_CONFIRMED', confirmed_by=admin.id))
    blocked = patient.post('/api/demo/livekit-sessions', json={'doctor_id': 1})
    assert blocked.status_code == 409
    assert 'otra sesión' in blocked.json()['detail']


def test_demo_livekit_tokens_allow_immediate_entry_and_doctor_finalization(patient, monkeypatch):
    link_all_demo_doctors()
    monkeypatch.setattr(livekit_consultations, 'enabled', lambda: True)
    monkeypatch.setattr(livekit_consultations, 'LIVEKIT_API_KEY', 'demo-key')
    monkeypatch.setattr(livekit_consultations, 'LIVEKIT_API_SECRET', 'demo-secret-for-tests-at-least-32-bytes')
    monkeypatch.setattr(livekit_consultations, 'LIVEKIT_PUBLIC_URL', 'ws://localhost:7880')
    created = patient.post('/api/demo/livekit-sessions', json={'doctor_id': 2})
    assert created.status_code == 201, created.text
    appointment_id = created.json()['id']

    with SessionLocal.begin() as db:
        appointment = db.get(Appointment, appointment_id)
        patient_user = db.get(User, appointment.patient_id)
        doctor_user = db.scalar(select(User).join(DoctorAccount, DoctorAccount.user_id == User.id).where(DoctorAccount.doctor_id == appointment.doctor_id))
        patient_token = livekit_consultations.issue_token(db, appointment_id, patient_user)
        doctor_token = livekit_consultations.issue_token(db, appointment_id, doctor_user, appointment.doctor_id)
        assert patient_token['token'] and doctor_token['token']
        # Simulate both authenticated participants connected; the shared finalizer owns lifecycle.
        appointment.status = 'IN_PROGRESS'
        vc = db.get(VirtualConsultation, appointment_id)
        vc.status = 'EN_ATENCION'
        result = livekit_consultations.finalize(db, appointment_id, doctor_user, appointment.doctor_id)
        assert result['appointment_status'] == 'ATTENDED'
        assert result['idempotent'] is False

    with SessionLocal() as db:
        assert db.get(Appointment, appointment_id).status == 'ATTENDED'
        assert db.get(VirtualConsultation, appointment_id).status == 'FINALIZADA'
        assert db.get(VirtualConsultation, appointment_id).finalized_at is not None
        assert db.scalar(select(AuditEvent.id).where(AuditEvent.action == 'LIVEKIT_CONSULTATION_FINALIZED', AuditEvent.entity_id == appointment_id))
