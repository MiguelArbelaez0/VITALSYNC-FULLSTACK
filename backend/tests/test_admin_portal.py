from uuid import uuid4
import json
import subprocess
import sys
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, func
from fastapi.testclient import TestClient

from conftest import ADMIN_TEST_PASSWORD, PATIENT_TEST_PASSWORD, appointment, activate
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import User, DoctorAccount, DoctorCredentialState, RecoveryRequest, Plan, PatientPlan, SubscriptionTerms, Payment, PaymentTerms, RefundRequest, RefundTransition, Appointment, Doctor, Availability


def login_admin(client):
    response = client.post('/api/auth/login', json={'email': 'admin@vitalsync.demo', 'password': ADMIN_TEST_PASSWORD})
    assert response.status_code == 200, response.text
    return client


def test_admin_dashboard_and_patient_projection_exclude_clinical_content(client):
    admin = login_admin(client)
    dashboard = admin.get('/api/admin/dashboard')
    assert dashboard.status_code == 200
    assert dashboard.json()['metrics']['patients_total'] == 1
    patient_id = admin.get('/api/admin/patients').json()['items'][0]['id']
    detail = admin.get(f'/api/admin/patients/{patient_id}')
    assert detail.status_code == 200
    assert not {'diagnoses', 'medications', 'allergies', 'encounters', 'clinical_history'} & detail.json().keys()
    assert admin.get(f'/api/doctor/patients/{patient_id}/clinical-history').status_code == 403


def test_admin_module_scope_is_enforced_server_side(client):
    with SessionLocal.begin() as db:
        admin_user = db.scalar(select(User).where(User.email == 'admin@vitalsync.demo'))
        from app.models.entities import AdminPermission
        db.add(AdminPermission(user_id=admin_user.id, scopes=['dashboard', 'accounts']))
    admin = login_admin(client)
    assert admin.get('/api/admin/dashboard').status_code == 200
    assert admin.get('/api/admin/patients').status_code == 403
    settings = admin.get('/api/admin/settings')
    assert settings.status_code == 200 and settings.json()['institution'] is None
    assert admin.get('/api/admin/administrators').status_code == 200
    with TestClient(app) as patient:
        assert patient.post('/api/auth/login', json={'email': 'paciente@vitalsync.demo', 'password': PATIENT_TEST_PASSWORD}).status_code == 200
        assert patient.get('/api/admin/dashboard').status_code == 403
    with SessionLocal() as db:
        from app.models.entities import AdminEvent
        denied = db.scalar(select(AdminEvent).where(AdminEvent.action == 'SECURITY_DENIED', AdminEvent.details['route'].astext == '/api/admin/patients'))
        assert denied and denied.details == {'status': 403, 'method': 'GET', 'route': '/api/admin/patients'}


def test_admin_doctor_creation_creates_private_recovery_without_exposing_password(client):
    admin = login_admin(client)
    response = admin.post('/api/admin/doctors', json={
        'name': 'Dra. Prueba Administrativa', 'email': 'admin.doctor+' + uuid4().hex[:10] + '@vitalsync.demo',
        'specialty_id': 1, 'bio': 'Profesional ficticia para verificar el acceso del portal administrativo.',
        'modalities': ['VIRTUAL', 'PRESENCIAL'], 'enabled': True, 'reason': 'Registro profesional de prueba',
    })
    assert response.status_code == 201, response.text
    assert 'password' not in response.text.lower()
    row = response.json()
    with SessionLocal() as db:
        link = db.scalar(select(DoctorAccount).where(DoctorAccount.doctor_id == row['id']))
        user = db.get(User, link.user_id)
        assert user.status == 'ACTIVE'
        assert db.scalar(select(DoctorCredentialState).where(DoctorCredentialState.user_id == user.id))
        assert db.scalar(select(RecoveryRequest).where(RecoveryRequest.user_id == user.id, RecoveryRequest.status == 'PENDING'))
        assert user.password_hash != 'MedicoDemo2026!'


def test_plan_catalog_edit_does_not_change_existing_subscription_terms(client):
    patient = client
    assert patient.post('/api/auth/login', json={'email': 'paciente@vitalsync.demo', 'password': PATIENT_TEST_PASSWORD}).status_code == 200
    activate(patient, 'Estándar')
    with SessionLocal() as db:
        pp = db.scalar(select(PatientPlan))
        old = dict(db.get(SubscriptionTerms, pp.patient_id).terms)
        plan = db.get(Plan, pp.plan_id)
        old_payment = db.scalar(select(Payment).where(Payment.patient_id == pp.patient_id, Payment.kind == 'PLAN'))
        old_price = old_payment.amount
        payload = {
            'name': plan.name, 'description': plan.description + ' Catálogo actualizado.',
            'price': plan.price + 1000, 'duration_days': plan.duration_days, 'copay': plan.copay,
            'virtual_copay': 6500, 'onsite_copay': 7000, 'consultation_limit': 4,
            'specialty_ids': plan.specialty_ids, 'modalities': plan.modalities, 'enabled': True,
            'benefits': 'Condiciones de catálogo nuevas', 'restrictions': '',
            'version': 1, 'reason': 'Cambio de términos para nuevas compras',
        }
        plan_id = plan.id
    admin = login_admin(client)
    response = admin.patch(f'/api/admin/plans/{plan_id}', json=payload)
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        pp = db.scalar(select(PatientPlan))
        assert db.get(SubscriptionTerms, pp.patient_id).terms == old
        assert db.scalar(select(Payment).where(Payment.patient_id == pp.patient_id, Payment.kind == 'PLAN')).amount == old_price
        assert db.scalar(select(PaymentTerms).where(PaymentTerms.payment_id == old_payment.id)).terms == old


def test_admin_refund_requires_cancellation_and_follows_versioned_review(client):
    patient = client
    assert patient.post('/api/auth/login', json={'email': 'paciente@vitalsync.demo', 'password': PATIENT_TEST_PASSWORD}).status_code == 200
    appointment(patient, 'Básico')
    with SessionLocal() as db:
        copay = db.scalar(select(Payment).where(Payment.kind == 'COPAY'))
        appointment_row = db.scalar(select(Appointment).where(Appointment.payment_id == copay.id))
        payment_id, appointment_id, version = copay.id, appointment_row.id, appointment_row.version
    admin = login_admin(client)
    payload = {'payment_id': payment_id, 'operation_key': uuid4().hex, 'reason': 'Revisión administrativa del copago'}
    assert admin.post('/api/admin/refunds', json=payload).status_code == 409
    cancelled = admin.post(f'/api/admin/appointments/{appointment_id}/cancel', json={'reason': 'Cancelación para revisar el copago', 'version': version, 'confirmed': True})
    assert cancelled.status_code == 200, cancelled.text
    created = admin.post('/api/admin/refunds', json=payload)
    assert created.status_code == 201, created.text
    refund_id = created.json()['id']
    for version, status in enumerate(['REVIEWING', 'APPROVED', 'AUTHORIZED', 'PROCESSED'], start=1):
        step = admin.post(f'/api/admin/refunds/{refund_id}/transition', json={
            'status': status, 'version': version, 'operation_key': uuid4().hex,
            'reason': 'Transición revisada por operador autorizado',
        })
        assert step.status_code == 200, step.text
        assert step.json()['status'] == status
    assert admin.post(f'/api/admin/refunds/{refund_id}/transition', json={
        'status': 'FAILED', 'version': 5, 'operation_key': uuid4().hex, 'reason': 'No debe repetirse'
    }).status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(RefundRequest)) == 1
        assert db.scalar(select(func.count()).select_from(RefundTransition)) == 5
        assert db.get(Payment, payment_id).status == 'APPROVED'


def test_recovery_is_private_single_use_and_does_not_change_password_until_redeemed(client, tmp_path):
    admin = login_admin(client)
    with SessionLocal() as db:
        target = db.scalar(select(User).where(User.email == 'paciente@vitalsync.demo'))
        target_id = target.id
        old_hash = target.password_hash
    requested = admin.post(f'/api/admin/accounts/{target_id}/recovery', json={'reason': 'Recuperación solicitada por titular'})
    assert requested.status_code == 200 and 'token' not in requested.text.lower()
    output = tmp_path / 'recovery.json'
    run = subprocess.run([sys.executable, '-m', 'app.access_recovery', '--output', str(output), '--email', 'paciente@vitalsync.demo'], capture_output=True, text=True, check=True)
    assert 'passwords_changed": 0' in run.stdout
    assert output.stat().st_mode & 0o777 == 0o600
    credential = json.loads(output.read_text())['recovery_links'][0]
    assert credential['email'] == 'paciente@vitalsync.demo'
    with SessionLocal() as db:
        assert db.get(User, target_id).password_hash == old_hash
    new_password = 'NuevaClaveSegura2026!'
    redeemed = client.post('/api/auth/recover', json={'token': credential['token'], 'new_password': new_password, 'confirm_password': new_password})
    assert redeemed.status_code == 200, redeemed.text
    assert client.post('/api/auth/recover', json={'token': credential['token'], 'new_password': new_password, 'confirm_password': new_password}).status_code == 400
    with SessionLocal() as db:
        assert db.get(User, target_id).password_hash != old_hash


def test_admin_cannot_disable_a_doctor_with_future_bookings(client):
    assert client.post('/api/auth/login', json={'email': 'paciente@vitalsync.demo', 'password': PATIENT_TEST_PASSWORD}).status_code == 200
    appointment(client, 'Básico')
    admin = login_admin(client)
    with SessionLocal() as db:
        doctor_id = db.scalar(select(Appointment.doctor_id))
    doctor_row = next(row for row in admin.get('/api/admin/doctors').json()['items'] if row['id'] == doctor_id)
    payload = {key: doctor_row[key] for key in ['name', 'specialty_id', 'bio', 'modalities']}
    payload.update(enabled=False, reason='Intento de desactivar con una cita futura')
    result = admin.patch(f"/api/admin/doctors/{doctor_row['id']}", json=payload)
    assert result.status_code == 409
    with SessionLocal() as db:
        assert db.get(Doctor, doctor_row['id']).enabled is True


def test_admin_schedule_batch_rolls_back_when_a_later_slot_conflicts(client):
    admin = login_admin(client)
    first = date.today() + timedelta(days=2)
    second = first + timedelta(days=1)
    with SessionLocal.begin() as db:
        doctor = db.scalar(select(Doctor).order_by(Doctor.id))
        db.add(Availability(doctor_id=doctor.id, starts_at=datetime.combine(second, time(12, 30), tzinfo=ZoneInfo('America/Bogota')),
                            ends_at=datetime.combine(second, time(13, 0), tzinfo=ZoneInfo('America/Bogota')),
                            modalities=['PRESENCIAL'], published=True, published_by=1))
    with SessionLocal() as db:
        doctor_id = db.scalar(select(Doctor.id).order_by(Doctor.id))
        before = db.scalar(select(func.count()).select_from(Availability).where(Availability.doctor_id == doctor_id))
    payload = {'doctor_id': doctor_id, 'first_day': first.isoformat(), 'last_day': second.isoformat(),
               'start_time': '12:00', 'end_time': '13:00', 'minutes': 30,
               'weekdays': [first.weekday(), second.weekday()], 'modalities': ['PRESENCIAL'],
               'published': True, 'reason': 'Prueba de atomicidad de jornada'}
    response = admin.post('/api/admin/schedules', json=payload)
    assert response.status_code == 409
    with SessionLocal() as db:
        after = db.scalar(select(func.count()).select_from(Availability).where(Availability.doctor_id == doctor_id))
        assert after == before
