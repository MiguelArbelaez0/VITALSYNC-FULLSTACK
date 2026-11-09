from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError, OperationalError
from app.main import app
from app.db.session import SessionLocal, engine
from app.models.entities import *
from app.core.security import digest, passwords
from app.services import booking
from app.seed import seed
from conftest import activate, free_slot, hold, copay, appointment, registration_data, register_patient

def test_register_duplicate_and_role_injection(client):
    body = registration_data('Paciente Nuevo', 'nuevo@example.com', 'Password2026!', '123456')
    assert client.post('/api/auth/register',json=body|{'role':'ADMIN'}).status_code == 422
    r = client.post('/api/auth/register',json=body)
    assert r.status_code == 201
    assert r.json()['role'] == 'PATIENT'
    assert r.json()['document_type'] == 'CC' and r.json()['document_masked'] == '••3456'
    assert r.json()['has_document'] is True
    assert r.json()['privacy_notice_version'] and r.json()['privacy_accepted_at']
    cookie = r.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'samesite=strict' in cookie
    assert client.get('/api/auth/me').json()['name'] == 'Paciente Nuevo'
    duplicate_email = client.post('/api/auth/register',json=body|{'email':'NUEVO@example.com','document_number':'654321'})
    assert duplicate_email.status_code == 409
    duplicate_document = register_patient(client, 'Otra Paciente', 'otra@example.com', 'Password2026!', '123456')
    assert duplicate_document.status_code == 409
    assert duplicate_document.json() == duplicate_email.json()
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == body['email']))
        assert u.password_hash != body['password'] and passwords.verify(body['password'], u.password_hash)

@pytest.mark.parametrize('document', ['12345', '12345678901', '123 456', '123.456', '12A456', ''])
def test_registration_rejects_invalid_document_without_echoing_it(client, document):
    body = registration_data('Paciente Prueba', 'identity-format@example.com', 'Password2026!', document)
    response = client.post('/api/auth/register', json=body)
    assert response.status_code == 422
    assert b'"input"' not in response.content

def test_registration_requires_phone_and_privacy_consent(client):
    body = registration_data('Paciente Prueba', 'identity-consent@example.com', 'Password2026!')
    assert client.post('/api/auth/register', json=body | {'privacy_accepted': False}).status_code == 422
    assert client.post('/api/auth/register', json={key: value for key, value in body.items() if key != 'phone'}).status_code == 422

@pytest.mark.parametrize('password', ['short7!', 'lowercasepass1', 'UPPERCASEPASS1'])
def test_registration_rejects_insufficient_passwords(client, password):
    body = registration_data('Paciente Seguridad', 'password-policy@example.com', password)
    assert client.post('/api/auth/register', json=body).status_code == 422

def test_database_keeps_identity_nullable_for_historical_patients(patient):
    with SessionLocal() as db:
        columns = {row.column_name: row.is_nullable for row in db.execute(text("""
            SELECT column_name, is_nullable FROM information_schema.columns
            WHERE table_name = 'patients' AND column_name IN ('document_type','document_number')
        """))}
        legacy_id = patient.get('/api/auth/me').json()['id']
        legacy = db.get(Patient, legacy_id)
        assert columns == {'document_type': 'YES', 'document_number': 'YES'}
        assert legacy.document_type is None and legacy.document_number is None

def test_same_document_race_creates_at_most_one_patient():
    document = '34567890'
    def create(index):
        with TestClient(app) as client:
            return register_patient(client, f'Paciente Numero {index}', f'document-race-{index}@example.com', 'Password2026!', document).status_code
    with ThreadPoolExecutor(2) as pool:
        statuses = list(pool.map(create, [1, 2]))
    assert sorted(statuses) == [201, 409]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Patient).where(Patient.document_number == document)) == 1

def test_two_self_registered_patients_have_independent_profiles_plans_and_appointments():
    with TestClient(app) as first, TestClient(app) as second:
        a = register_patient(first, 'Ana Maria', 'Ana.Patient@Example.com', 'Password2026!', '123456')
        b = register_patient(second, 'Bruno Lopez', 'bruno.patient@example.com', 'Password2026!', '0001234567')
        assert a.status_code == b.status_code == 201
        assert a.json()['id'] != b.json()['id']
        assert a.json()['email'] == 'ana.patient@example.com'
        assert a.json()['document_masked'] == '••3456'
        assert b.json()['document_masked'] == '••••••4567'
        assert '123456' not in a.text and '0001234567' not in b.text
        assert first.get('/api/auth/me').json()['name'] == 'Ana Maria'
        assert second.get('/api/auth/me').json()['name'] == 'Bruno Lopez'
        assert first.get('/api/my-plan').json()['status'] == 'INACTIVE'
        assert second.get('/api/my-plan').json()['status'] == 'INACTIVE'

        activate(first, 'Estándar')
        appointment(first, 'Estándar')
        assert first.get('/api/my-plan').json()['status'] == 'ACTIVE'
        assert len(first.get('/api/appointments').json()) == 1
        assert second.get('/api/my-plan').json()['status'] == 'INACTIVE'
        assert second.get('/api/appointments').json() == []
        assert len(first.get('/api/notifications').json()) > len(second.get('/api/notifications').json())

def test_legacy_patient_can_add_document_without_changing_login_or_exposing_full_value(patient):
    before = patient.get('/api/auth/me').json()
    assert before['has_document'] is False and before['document_masked'] is None
    response = patient.patch('/api/auth/me', json={
        'name': before['name'],
        'phone': '+57 300 123 4567',
        'document_type': 'CC',
        'document_number': '00123456',
        'privacy_accepted': True,
    })
    assert response.status_code == 200, response.text
    assert response.json()['document_masked'] == '••••3456'
    assert '00123456' not in response.text
    with SessionLocal() as db:
        patient_record = db.get(Patient, before['id'])
        user = db.get(User, before['id'])
        assert patient_record.document_number == '00123456'
        assert user.privacy_notice_version and user.privacy_accepted_at
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.actor_id == before['id'], AuditEvent.action == 'PATIENT_PROFILE_UPDATED'
        )) == 1
    assert patient.get('/api/auth/me').status_code == 200

def test_document_conflict_is_generic_and_existing_document_cannot_be_replaced(patient):
    with TestClient(app) as other:
        register_patient(other, 'Otra Persona', 'document-owner@example.com', 'Password2026!', '12345678')
    duplicate = patient.patch('/api/auth/me', json={
        'name': 'Valentina Torres', 'phone': '', 'document_type': 'CC',
        'document_number': '12345678', 'privacy_accepted': True,
    })
    assert duplicate.status_code == 409
    assert 'No pudimos guardar este documento' in duplicate.json()['detail']
    assert '12345678' not in duplicate.text
    with TestClient(app) as owner:
        register_patient(owner, 'Dueña del Documento', 'document-owner-two@example.com', 'Password2026!', '87654321')
        changed = owner.patch('/api/auth/me', json={
            'name': 'Dueña del Documento', 'phone': '', 'document_type': 'CC',
            'document_number': '11223344', 'privacy_accepted': True,
        })
        assert changed.status_code == 409
        assert '11223344' not in changed.text

def test_profile_rejects_document_without_consent_and_keeps_legacy_login(patient):
    before = patient.get('/api/auth/me').json()
    assert before['has_document'] is False
    rejected = patient.patch('/api/auth/me', json={
        'name': before['name'], 'phone': '', 'document_type': 'CC',
        'document_number': '76543210', 'privacy_accepted': False,
    })
    assert rejected.status_code == 422
    assert '76543210' not in rejected.text
    assert patient.get('/api/auth/me').status_code == 200
    assert patient.get('/api/auth/me').json()['has_document'] is False

def test_registration_rolls_back_all_records_if_commit_fails(monkeypatch):
    from sqlalchemy.orm import Session
    body = registration_data('Rollback Patient', 'rollback-registration@example.com', 'Password2026!', '98765432')
    def broken_commit(self):
        raise OperationalError('injected commit failure', {}, Exception('test'))
    with monkeypatch.context() as patcher:
        patcher.setattr(Session, 'commit', broken_commit)
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post('/api/auth/register', json=body)
            assert response.status_code == 503
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(User).where(User.email == body['email'])) == 0
        assert db.scalar(select(func.count()).select_from(Patient).where(Patient.document_number == '98765432')) == 0
        assert db.scalar(select(func.count()).select_from(Notification).join(Patient, Notification.patient_id == Patient.id).join(User, User.id == Patient.id).where(User.email == body['email'])) == 0

def test_login_logout_and_session_persistence(patient):
    token = patient.cookies.get('vitalsync_session')
    with TestClient(app) as another:
        another.cookies.set('vitalsync_session', token)
        assert another.get('/api/auth/me').status_code == 200
    assert patient.post('/api/auth/logout').status_code == 200
    assert patient.get('/api/auth/me').status_code == 401
    with TestClient(app) as another:
        another.cookies.set('vitalsync_session', token)
        assert another.get('/api/auth/me').status_code == 401

def test_disabled_account_cannot_reuse_an_existing_session(patient):
    uid = patient.get('/api/auth/me').json()['id']
    with SessionLocal.begin() as db:
        db.get(User, uid).status = 'DISABLED'
    assert patient.get('/api/auth/me').status_code == 401
    assert patient.post('/api/auth/login', json={'email':'paciente@vitalsync.demo','password':'Paciente2026!'}).status_code == 403

@pytest.mark.parametrize('email,password', [('paciente@vitalsync.demo','Incorrecta123!'),('missing@example.com','Incorrecta123!')])
def test_invalid_login(client,email,password):
    assert client.post('/api/auth/login',json={'email':email,'password':password}).status_code == 401

def test_authorization_origin_and_expiry(patient):
    with TestClient(app) as anonymous:
        assert anonymous.get('/api/dashboard').status_code == 401
        assert anonymous.post('/api/holds',json={'availability_id':1}).status_code == 401
        assert anonymous.post('/api/auth/login',json={'email':'admin@vitalsync.demo','password':'AdminDemo2026!'}).status_code == 403
    assert patient.post('/api/holds',json={'availability_id':1},headers={'origin':'https://evil.example'}).status_code == 403
    assert patient.post('/api/holds',json={'availability_id':1},headers={'sec-fetch-site':'cross-site'}).status_code == 403
    with SessionLocal.begin() as db:
        token = db.get(SessionToken,digest(patient.cookies.get('vitalsync_session')))
        token.expires_at = now()-timedelta(seconds=1)
    assert patient.get('/api/dashboard').status_code == 401

def test_profile_and_real_dashboard(patient):
    assert patient.patch('/api/auth/me',json={'name':'Valentina Actualizada','phone':'+57 300 1234567'}).status_code == 200
    assert patient.get('/api/auth/me').json()['name'] == 'Valentina Actualizada'
    d=patient.get('/api/dashboard').json()
    assert d['upcoming_count']==0 and d['plan']['status']=='INACTIVE'

def test_no_plan_and_expired_plan(patient):
    slot=free_slot(patient)
    assert 'Debes activar' in patient.post('/api/holds',json={'availability_id':slot['id']}).json()['detail']
    activate(patient)
    uid=patient.get('/api/auth/me').json()['id']
    with SessionLocal.begin() as db:
        db.get(PatientPlan,uid).expires_at=now()-timedelta(days=1)
    assert patient.get('/api/my-plan').json()['status']=='EXPIRED'
    assert 'vencido' in patient.post('/api/holds',json={'availability_id':slot['id']}).json()['detail']

@pytest.mark.parametrize('status', ['REJECTED','PENDING','IN_RECONCILIATION'])
def test_plan_not_activated_without_approval(patient,status):
    p=activate(patient,status=status)
    assert p['status']==status
    assert patient.get('/api/my-plan').json()['status']=='INACTIVE'

def test_plan_payment_idempotency_and_renewal(patient):
    p=activate(patient)
    before=patient.get('/api/my-plan').json()
    with SessionLocal() as db:
        key=db.get(Payment,p['id']).idempotency_key
    r=patient.post('/api/payments',json={'kind':'PLAN','target_id':p['plan_id'],'status':'APPROVED','idempotency_key':key})
    assert r.json()['id']==p['id']
    assert patient.get('/api/my-plan').json()['expires_at']==before['expires_at']
    activate(patient)
    after=patient.get('/api/my-plan').json()
    assert datetime.fromisoformat(after['expires_at'])-datetime.fromisoformat(before['expires_at'])==timedelta(days=30)

def test_pending_plan_reconciliation(patient):
    p=activate(patient,status='PENDING')
    assert patient.post('/api/payments',json={'kind':'PLAN','target_id':p['plan_id'],'status':'APPROVED','idempotency_key':uuid4().hex}).status_code==409
    assert patient.post(f"/api/payments/{p['id']}/reconcile",json={'status':'APPROVED'}).status_code==200
    expiry=patient.get('/api/my-plan').json()['expires_at']
    assert patient.post(f"/api/payments/{p['id']}/reconcile",json={'status':'APPROVED'}).status_code==200
    assert patient.get('/api/my-plan').json()['expires_at']==expiry
    assert patient.post(f"/api/payments/{p['id']}/reconcile",json={'status':'REJECTED'}).status_code==409

@pytest.mark.parametrize('plan_name',['Básico','Estándar','Premium','Plan Académico Nuevo'])
def test_any_active_plan_can_be_cancelled_immediately_and_audited(patient,plan_name):
    if plan_name == 'Plan Académico Nuevo':
        with SessionLocal.begin() as db:
            specialty_id=db.scalar(select(Specialty.id).order_by(Specialty.id))
            db.add(Plan(name=plan_name,description='Plan de prueba extensible',price=75000,duration_days=45,copay=5000,specialty_ids=[specialty_id],modalities=['PRESENCIAL'],enabled=True))
    saved_appointment=appointment(patient,plan_name)
    uid=patient.get('/api/auth/me').json()['id']
    membership=patient.get('/api/my-plan').json()
    plan_id=membership['plan']['id']
    response=patient.post('/api/my-plan/cancel',json={'plan_id':plan_id,'confirmed':True})
    assert response.status_code==200,response.text
    result=response.json()
    assert result['plan_id']==plan_id and result['plan_name']==plan_name
    assert result['previous_status']=='ACTIVE' and result['status']=='INACTIVE'
    assert result['policy']=='IMMEDIATE' and result['cancelled_at']==result['effective_at']
    after=patient.get('/api/my-plan').json()
    assert after['status']=='INACTIVE' and after['cancelled_at']==result['cancelled_at']
    assert after['cancellation_history'][0]['plan_name']==plan_name
    assert after['cancellation_history'][0]['previous_status']=='ACTIVE'
    assert after['cancellation_history'][0]['new_status']=='INACTIVE'
    dashboard=patient.get('/api/dashboard').json()
    assert dashboard['plan']['status']=='INACTIVE'
    assert any(a['id']==saved_appointment['id'] and a['status']=='CONFIRMED' for a in patient.get('/api/appointments').json())
    duplicate=patient.post('/api/my-plan/cancel',json={'plan_id':plan_id,'confirmed':True})
    assert duplicate.status_code==409
    with SessionLocal() as db:
        history=db.scalars(select(PatientPlanCancellation).where(PatientPlanCancellation.patient_id==uid)).all()
        assert len(history)==1 and history[0].plan_id==plan_id and history[0].changed_by==uid
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.actor_id==uid,AuditEvent.action=='PATIENT_PLAN_CANCELLED',AuditEvent.entity_id==plan_id))==1
        assert db.scalar(select(func.count()).select_from(Appointment).where(Appointment.id==saved_appointment['id'],Appointment.status=='CONFIRMED'))==1
    next_slot=free_slot(patient)
    rejected=patient.post('/api/holds',json={'availability_id':next_slot['id'],'modality':'PRESENCIAL'})
    assert rejected.status_code==409 and 'activar tu plan' in rejected.json()['detail']

def test_plan_cancellation_requires_ownership_and_explicit_confirmation(patient):
    activate(patient,'Estándar')
    plan_id=patient.get('/api/my-plan').json()['plan']['id']
    with TestClient(app) as other:
        register_patient(other,'Otro Paciente','cancel-plan-owner@example.com','Paciente2026!')
        assert other.post('/api/my-plan/cancel',json={'plan_id':plan_id,'confirmed':True}).status_code==404
    assert patient.post('/api/my-plan/cancel',json={'plan_id':plan_id,'confirmed':False}).status_code==422
    assert patient.post('/api/my-plan/cancel',json={'plan_id':plan_id}).status_code==422
    with TestClient(app) as anonymous:
        assert anonymous.post('/api/my-plan/cancel',json={'plan_id':plan_id,'confirmed':True}).status_code==401
    assert patient.get('/api/my-plan').json()['status']=='ACTIVE'

def test_plan_cancellation_blocks_pending_payments_and_active_holds(patient):
    activate(patient,'Premium')
    plan_id=patient.get('/api/my-plan').json()['plan']['id']
    pending=patient.post('/api/payments',json={'kind':'PLAN','target_id':plan_id,'status':'PENDING','idempotency_key':uuid4().hex})
    assert pending.status_code==200
    blocked=patient.post('/api/my-plan/cancel',json={'plan_id':plan_id,'confirmed':True})
    assert blocked.status_code==409 and 'pago pendiente' in blocked.json()['detail']
    assert patient.post(f"/api/payments/{pending.json()['id']}/reconcile",json={'status':'REJECTED'}).status_code==200
    active_hold=hold(patient)
    blocked=patient.post('/api/my-plan/cancel',json={'plan_id':plan_id,'confirmed':True})
    assert blocked.status_code==409 and 'retención activa' in blocked.json()['detail']
    assert patient.post(f"/api/holds/{active_hold['id']}/release").status_code==200
    assert patient.post('/api/my-plan/cancel',json={'plan_id':plan_id,'confirmed':True}).status_code==200

def test_directory_availability_coverage_and_block(patient):
    assert len(patient.get('/api/specialties').json())==5
    assert len(patient.get('/api/doctors?specialty_id=1').json())==1
    assert len(patient.get('/api/doctors?search=Isabella').json())==1
    assert patient.get('/api/doctors/9999').status_code==404
    slots=patient.get('/api/doctors/1/availability').json()
    blocked=next(s for s in slots if not s['available'])
    activate(patient)
    assert patient.post('/api/holds',json={'availability_id':blocked['id']}).status_code==409
    assert 'no cubre' in patient.post('/api/holds',json={'availability_id':free_slot(patient,2)['id']}).json()['detail']
    assert patient.get('/api/appointments').json()==[]

def test_hold_expiry_and_late_payment(patient):
    activate(patient)
    h=hold(patient)
    p=copay(patient,h,'PENDING').json()
    with SessionLocal.begin() as db:
        db.get(Hold,h['id']).expires_at=now()-timedelta(seconds=1)
    assert patient.post(f"/api/holds/{h['id']}/confirm").status_code==409
    assert copay(patient,h).status_code==409
    assert patient.post(f"/api/payments/{p['id']}/reconcile",json={'status':'APPROVED'}).status_code==409
    assert next(x for x in patient.get('/api/payments').json() if x['id']==p['id'])['status']=='PENDING'
    assert patient.post(f"/api/payments/{p['id']}/reconcile",json={'status':'REJECTED'}).status_code==200

def test_hold_release_and_no_patient_schedule_publication(patient):
    activate(patient)
    h=hold(patient)
    assert patient.post('/api/doctors/1/availability',json={}).status_code==405
    assert patient.post(f"/api/holds/{h['id']}/release").status_code==200
    assert patient.post(f"/api/holds/{h['id']}/confirm").status_code==409
    assert patient.get(f"/api/holds/{h['id']}").json()['status']=='RELEASED'

@pytest.mark.parametrize('status',['REJECTED','PENDING','IN_RECONCILIATION'])
def test_copay_not_confirmed_unless_approved(patient,status):
    activate(patient)
    h=hold(patient)
    assert h['copay']==15000
    p=copay(patient,h,status)
    assert p.status_code==200
    assert patient.post(f"/api/holds/{h['id']}/confirm").status_code==409
    if status!='REJECTED':
        assert copay(patient,h).status_code==409
        assert patient.post(f"/api/payments/{p.json()['id']}/reconcile",json={'status':'APPROVED'}).status_code==200
    else:
        assert copay(patient,h).status_code==200
    assert patient.post(f"/api/holds/{h['id']}/confirm").status_code==200

def test_copay_duplicate_and_confirmation_idempotent(patient):
    activate(patient)
    h=hold(patient)
    key=uuid4().hex
    p=copay(patient,h,key=key).json()
    assert copay(patient,h,key=key).json()['id']==p['id']
    assert copay(patient,h).status_code==409
    first=patient.post(f"/api/holds/{h['id']}/confirm").json()
    second=patient.post(f"/api/holds/{h['id']}/confirm").json()
    assert first['id']==second['id']
    assert len(patient.get('/api/appointments').json())==1
    assert patient.get('/api/dashboard').json()['upcoming_count']==1

def test_no_copay_premium(patient):
    activate(patient,'Premium')
    h=hold(patient)
    assert h['copay']==0
    assert copay(patient,h).status_code==409
    assert patient.post(f"/api/holds/{h['id']}/confirm").status_code==200

@pytest.mark.parametrize('change',['doctor_disabled','block','plan_expired','plan_changed','schedule_unpublished'])
def test_confirmation_revalidates(patient,change):
    activate(patient,'Premium')
    h=hold(patient)
    uid=patient.get('/api/auth/me').json()['id']
    with SessionLocal.begin() as db:
        if change=='doctor_disabled': db.get(Doctor,h['doctor_id']).enabled=False
        if change=='block': db.add(DoctorBlock(doctor_id=h['doctor_id'],starts_at=datetime.fromisoformat(h['starts_at']),ends_at=datetime.fromisoformat(h['ends_at']),reason='Bloqueo tardío'))
        if change=='plan_expired': db.get(PatientPlan,uid).expires_at=now()-timedelta(days=1)
        if change=='plan_changed': db.get(PatientPlan,uid).plan_id=1
        if change=='schedule_unpublished': db.get(Availability,db.get(Hold,h['id']).availability_id).published=False
    assert patient.post(f"/api/holds/{h['id']}/confirm").status_code==409
    assert patient.get('/api/appointments').json()==[]

def test_concurrent_holds_and_confirmations(patient):
    activate(patient,'Premium')
    with TestClient(app) as second:
        assert register_patient(second,'Otro Paciente','otro@example.com','Password2026!').status_code==201
        activate(second,'Premium')
        slot=free_slot(patient)
        def reserve(c): return c.post('/api/holds',json={'availability_id':slot['id']})
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(reserve,[patient,second]))
        assert sorted(r.status_code for r in results)==[201,409]
        winner=patient if results[0].status_code==201 else second
        h=next(r.json() for r in results if r.status_code==201)
        def confirm(_):
            with TestClient(app) as c:
                c.cookies.update(winner.cookies)
                return c.post(f"/api/holds/{h['id']}/confirm")
        with ThreadPoolExecutor(2) as pool:
            confirmations=list(pool.map(confirm,range(2)))
        assert all(r.status_code==200 for r in confirmations)
        assert len({r.json()['id'] for r in confirmations})==1
        assert second.get('/api/appointments').status_code==200

def test_cancel_own_history_notification_release_once(patient):
    a=appointment(patient)
    data={'version':a['version'],'reason':'Cambio de agenda','confirmed':True}
    assert patient.post(f"/api/appointments/{a['id']}/cancel",json=data).status_code==200
    after=patient.get(f"/api/appointments/{a['id']}").json()
    assert after['status']=='CANCELLED' and after['version']==2 and after['economic_review']
    assert len(after['history'])==2
    assert patient.post(f"/api/appointments/{a['id']}/cancel",json=data).status_code==409
    assert patient.post(f"/api/appointments/{a['id']}/cancel",json=data|{'version':2}).status_code==409
    assert len(patient.get('/api/appointments').json())==1
    messages=patient.get('/api/notifications').json()
    assert any('cancelada' in n['message'] for n in messages)
    assert patient.post(f"/api/notifications/{messages[0]['id']}/read").status_code==200
    assert patient.get('/api/notifications').json()[0]['read']
    assert patient.get('/api/dashboard').json()['upcoming_count']==0
    with SessionLocal() as db:
        original=db.get(Hold,db.get(Appointment,a['id']).hold_id)
        slot_id=original.availability_id
    assert patient.post('/api/holds',json={'availability_id':slot_id}).status_code==201

def test_other_patient_denied(patient):
    a=appointment(patient)
    with TestClient(app) as other:
        register_patient(other,'Otro Paciente','otro@example.com','Password2026!')
        assert other.get(f"/api/appointments/{a['id']}").status_code==404
        assert other.post(f"/api/appointments/{a['id']}/cancel",json={'version':1,'reason':'Ajena','confirmed':True}).status_code==404
        with SessionLocal() as db:
            h=db.get(Appointment,a['id']).hold_id
        assert other.get(f'/api/holds/{h}').status_code==404

@pytest.mark.parametrize('change',['attended','policy','version'])
def test_cancel_policy_state_and_version(patient,change):
    a=appointment(patient,'Premium')
    with SessionLocal.begin() as db:
        entity=db.get(Appointment,a['id'])
        if change=='attended': entity.status='ATTENDED'
        if change=='policy':
            entity.starts_at=now()+timedelta(minutes=30)
            entity.ends_at=entity.starts_at+timedelta(minutes=30)
        if change=='version': entity.version+=1
    assert patient.post(f"/api/appointments/{a['id']}/cancel",json={'version':1,'reason':'Prueba','confirmed':True}).status_code==409

def test_cancellation_requires_explicit_confirmation(patient):
    a=appointment(patient,'Premium')
    assert patient.post(f"/api/appointments/{a['id']}/cancel",json={'version':1,'reason':'Prueba','confirmed':False}).status_code==422
    assert patient.get(f"/api/appointments/{a['id']}").json()['status']=='CONFIRMED'

def test_transaction_rollback_confirmation(patient,monkeypatch):
    activate(patient,'Premium')
    h=hold(patient)
    def broken(*args): raise OperationalError('injected transaction failure',{},Exception('test'))
    monkeypatch.setattr(booking,'notify',broken)
    with TestClient(app,raise_server_exceptions=False) as c:
        c.cookies.update(patient.cookies)
        assert c.post(f"/api/holds/{h['id']}/confirm").status_code==503
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Appointment))==0
        assert db.get(Hold,h['id']).status=='ACTIVE'
        assert db.scalar(select(func.count()).select_from(StatusHistory))==0

def test_transaction_rollback_cancellation(patient,monkeypatch):
    a=appointment(patient,'Premium')
    def broken(*args): raise OperationalError('injected failure',{},Exception('test'))
    monkeypatch.setattr(booking,'notify',broken)
    with TestClient(app,raise_server_exceptions=False) as c:
        c.cookies.update(patient.cookies)
        assert c.post(f"/api/appointments/{a['id']}/cancel",json={'version':1,'reason':'Prueba rollback','confirmed':True}).status_code==503
    saved=patient.get(f"/api/appointments/{a['id']}").json()
    assert saved['status']=='CONFIRMED' and saved['version']==1 and len(saved['history'])==1

def test_database_constraints_and_seed_idempotent(patient):
    a=appointment(patient,'Premium')
    with SessionLocal() as db:
        before={m.__tablename__:db.scalar(select(func.count()).select_from(m)) for m in [User,Doctor,Availability,Plan]}
    seed()
    with SessionLocal() as db:
        after={m.__tablename__:db.scalar(select(func.count()).select_from(m)) for m in [User,Doctor,Availability,Plan]}
        assert before==after
        assert db.get(Appointment,a['id']).code==a['code']
        assert db.scalar(text("SELECT count(*) FROM pg_constraint WHERE conname IN ('no_doctor_overlap','no_patient_overlap')"))==2

def test_demo_payments_disabled(patient,monkeypatch):
    import app.main as main
    monkeypatch.setattr(main,'DEMO_MODE',False)
    r=patient.post('/api/payments',json={'kind':'PLAN','target_id':1,'status':'APPROVED','idempotency_key':uuid4().hex})
    assert r.status_code==403

def test_commit_failure_is_not_reported_as_success(patient,monkeypatch):
    activate(patient,'Premium')
    h=hold(patient)
    from sqlalchemy.orm import Session
    def broken_commit(self):
        raise OperationalError('injected commit failure',{},Exception('test'))
    with monkeypatch.context() as m:
        m.setattr(Session,'commit',broken_commit)
        with TestClient(app,raise_server_exceptions=False) as c:
            c.cookies.update(patient.cookies)
            assert c.post(f"/api/holds/{h['id']}/confirm").status_code==503
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Appointment))==0
        assert db.get(Hold,h['id']).status=='ACTIVE'

def test_partial_overlap_is_rejected_by_service_and_database(patient):
    a=appointment(patient,'Premium')
    start=datetime.fromisoformat(a['starts_at'])+timedelta(minutes=5)
    end=start+timedelta(minutes=30)
    with SessionLocal.begin() as db:
        original=db.get(Appointment,a['id'])
        admin=db.scalar(select(User).where(User.role=='ADMIN'))
        slot=Availability(doctor_id=original.doctor_id,starts_at=start,ends_at=end,published_by=admin.id)
        db.add(slot)
        db.flush()
        slot_id=slot.id
        uid=original.patient_id
        doctor_id=original.doctor_id
        plan_id=original.plan_id
    assert patient.post('/api/holds',json={'availability_id':slot_id}).status_code==409
    with SessionLocal() as db:
        h=Hold(patient_id=uid,doctor_id=doctor_id,availability_id=slot_id,plan_id=plan_id,starts_at=start,ends_at=end,expires_at=now()+timedelta(minutes=10),copay=0,status='CONFIRMED')
        db.add(h)
        db.flush()
        db.add(Appointment(code='VS-DIRECT-CONFLICT',patient_id=uid,doctor_id=doctor_id,hold_id=h.id,plan_id=plan_id,starts_at=start,ends_at=end,copay=0,status='CONFIRMED'))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
    assert len(patient.get('/api/appointments').json())==1

def test_past_schedule_rejected_before_payment(patient):
    activate(patient)
    with SessionLocal.begin() as db:
        admin=db.scalar(select(User).where(User.role=='ADMIN'))
        slot=Availability(doctor_id=1,starts_at=now()-timedelta(days=1),ends_at=now()-timedelta(hours=23),published_by=admin.id)
        db.add(slot)
        db.flush()
        slot_id=slot.id
    assert patient.post('/api/holds',json={'availability_id':slot_id}).status_code==409
    assert all(p['kind']=='PLAN' for p in patient.get('/api/payments').json())

def test_concurrent_cancellation_changes_once(patient):
    a=appointment(patient,'Premium')
    data={'version':1,'reason':'Cancelación concurrente','confirmed':True}
    def do_cancel(_):
        with TestClient(app) as c:
            c.cookies.update(patient.cookies)
            return c.post(f"/api/appointments/{a['id']}/cancel",json=data)
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(do_cancel,range(2)))
    assert sorted(r.status_code for r in results)==[200,409]
    saved=patient.get(f"/api/appointments/{a['id']}").json()
    assert saved['version']==2 and len(saved['history'])==2
    notices=patient.get('/api/notifications').json()
    assert sum('ha sido cancelada' in n['message'] for n in notices)==1

def virtual_slot(c, doctor_id=1):
    return next(s for s in c.get(f'/api/doctors/{doctor_id}/availability?modality=VIRTUAL').json() if s['available'])

def test_existing_appointments_default_to_in_person_and_virtual_doctors_are_filtered(patient):
    old=appointment(patient,'Premium')
    assert old['modality']=='PRESENCIAL'
    assert patient.get('/api/doctors?modality=VIRTUAL').status_code==200
    assert patient.get('/api/doctors?modality=VIRTUAL').json()[0]['modalities']==['PRESENCIAL','VIRTUAL']
    assert patient.get('/api/doctors?modality=NOPE').status_code==422
    assert patient.get('/api/doctors/1/availability?modality=VIRTUAL').json()

def test_plan_without_virtual_coverage_rejected_before_hold_or_copay(patient):
    activate(patient,'Básico')
    slot=virtual_slot(patient,1)
    error=patient.post('/api/holds',json={'availability_id':slot['id'],'modality':'VIRTUAL'})
    assert error.status_code==409 and 'no incluye consultas virtuales' in error.json()['detail']
    assert patient.get('/api/appointments').json()==[]
    assert all(p['kind']=='PLAN' for p in patient.get('/api/payments').json())

@pytest.mark.parametrize('plan_name,doctor_id,modality,copay',[
    ('Básico',1,'PRESENCIAL',15000),
    ('Estándar',2,'VIRTUAL',10000),
    ('Estándar',3,'PRESENCIAL',10000),
    ('Premium',5,'VIRTUAL',0),
    ('Premium',4,'PRESENCIAL',0),
])
def test_plan_coverage_is_configured_by_specialty_modality_and_copay(patient,plan_name,doctor_id,modality,copay):
    activate(patient,plan_name)
    slots=patient.get(f'/api/doctors/{doctor_id}/availability?modality={modality}').json()
    slot=next(s for s in slots if s['available'])
    response=patient.post('/api/holds',json={'availability_id':slot['id'],'modality':modality})
    assert response.status_code==201,response.text
    assert response.json()['modality']==modality and response.json()['copay']==copay

def test_standard_plan_rejects_uncovered_specialty(patient):
    activate(patient,'Estándar')
    slot=next(s for s in patient.get('/api/doctors/4/availability?modality=VIRTUAL').json() if s['available'])
    response=patient.post('/api/holds',json={'availability_id':slot['id'],'modality':'VIRTUAL'})
    assert response.status_code==409 and 'no cubre esta especialidad' in response.json()['detail']
    assert patient.get('/api/appointments').json()==[]

@pytest.mark.parametrize('doctor_modalities,requested',[
    (['PRESENCIAL'],'VIRTUAL'),
    (['VIRTUAL'],'PRESENCIAL'),
])
def test_doctor_rejects_unsupported_requested_modality(patient,doctor_modalities,requested):
    activate(patient,'Premium')
    with SessionLocal.begin() as db:
        doctor=db.get(Doctor,1)
        doctor.modalities=doctor_modalities
        slot_id=db.scalar(select(Availability.id).where(Availability.doctor_id==1,Availability.starts_at>now()).order_by(Availability.starts_at))
    response=patient.post('/api/holds',json={'availability_id':slot_id,'modality':requested})
    assert response.status_code==409 and 'no ofrece citas' in response.json()['detail']
    assert patient.get('/api/appointments').json()==[]

def test_standard_plan_virtual_copay_confirmation_and_receipt(patient):
    activate(patient,'Estándar')
    slot=virtual_slot(patient,1)
    h=patient.post('/api/holds',json={'availability_id':slot['id'],'modality':'VIRTUAL'}).json()
    assert h['modality']=='VIRTUAL' and h['copay']==10000
    p=copay(patient,h)
    assert p.status_code==200
    confirmed=patient.post(f"/api/holds/{h['id']}/confirm")
    assert confirmed.status_code==200
    receipt=patient.get(f"/api/appointments/{confirmed.json()['id']}").json()
    assert receipt['modality']=='VIRTUAL' and receipt['location'] is None and receipt['virtual_status']=='PROGRAMADA'
    assert patient.get('/api/appointments').json()[0]['modality']=='VIRTUAL'

def test_virtual_same_slot_conflicts_with_in_person_booking(patient):
    current=appointment(patient,'Premium')
    with TestClient(app) as other:
        register_patient(other,'Paciente Virtual','virtual-conflict@example.com','Paciente2026!')
        activate(other,'Premium')
        with SessionLocal.begin() as db:
            original=db.get(Appointment,current['id'])
            slot_id=db.get(Hold,original.hold_id).availability_id
        r=other.post('/api/holds',json={'availability_id':slot_id,'modality':'VIRTUAL'})
        assert r.status_code==409 and 'ocupado' in r.json()['detail']
        assert other.get('/api/appointments').json()==[]

def test_virtual_room_state_transitions_and_access_control(patient):
    activate(patient,'Premium')
    h=patient.post('/api/holds',json={'availability_id':virtual_slot(patient)['id'],'modality':'VIRTUAL'}).json()
    aid=patient.post(f"/api/holds/{h['id']}/confirm").json()['id']
    room=patient.get(f'/api/appointments/{aid}/teleconsult')
    assert room.status_code==200 and 'sin conexión de audio o video' in room.json()['message'].lower()
    for step in ['SALA_DISPONIBLE','PACIENTE_EN_ESPERA','MEDICO_EN_ESPERA','EN_ATENCION','FINALIZADA']:
        r=patient.post(f'/api/appointments/{aid}/teleconsult/status',json={'status':step})
        assert r.status_code==200 and r.json()['status']==step
    assert patient.post(f'/api/appointments/{aid}/teleconsult/status',json={'status':'EN_ATENCION'}).status_code==409
    with TestClient(app) as other:
        register_patient(other,'Otro Paciente','teleconsult-denied@example.com','Paciente2026!')
        assert other.get(f'/api/appointments/{aid}/teleconsult').status_code==404
        assert other.post(f'/api/appointments/{aid}/teleconsult/status',json={'status':'SALA_DISPONIBLE'}).status_code==404
    data={'version':1,'reason':'El paciente cancela su cita virtual','confirmed':True}
    assert patient.post(f'/api/appointments/{aid}/cancel',json=data).status_code==200
    assert patient.get(f'/api/appointments/{aid}/teleconsult').status_code==404
    with SessionLocal() as db:
        assert db.get(VirtualConsultation,aid).status=='CANCELADA'

def test_virtual_absence_outcomes_are_available_only_at_allowed_steps(patient):
    activate(patient,'Premium')
    first=patient.post('/api/holds',json={'availability_id':virtual_slot(patient)['id'],'modality':'VIRTUAL'}).json()
    first_id=patient.post(f"/api/holds/{first['id']}/confirm").json()['id']
    assert patient.post(f'/api/appointments/{first_id}/teleconsult/status',json={'status':'SALA_DISPONIBLE'}).status_code==200
    absent=patient.post(f'/api/appointments/{first_id}/teleconsult/status',json={'status':'PACIENTE_AUSENTE'})
    assert absent.status_code==200 and absent.json()['status']=='PACIENTE_AUSENTE'
    assert patient.post(f'/api/appointments/{first_id}/teleconsult/status',json={'status':'EN_ATENCION'}).status_code==409

    second=patient.post('/api/holds',json={'availability_id':virtual_slot(patient)['id'],'modality':'VIRTUAL'}).json()
    second_id=patient.post(f"/api/holds/{second['id']}/confirm").json()['id']
    for step in ['SALA_DISPONIBLE','PACIENTE_EN_ESPERA']:
        assert patient.post(f'/api/appointments/{second_id}/teleconsult/status',json={'status':step}).status_code==200
    absent=patient.post(f'/api/appointments/{second_id}/teleconsult/status',json={'status':'MEDICO_AUSENTE'})
    assert absent.status_code==200 and absent.json()['status']=='MEDICO_AUSENTE'

def test_virtual_appointment_migration_preserves_preexisting_data(patient):
    with SessionLocal() as db:
        old_count=db.scalar(select(func.count()).select_from(Appointment))
    seed()
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Appointment))==old_count
        assert db.scalar(text("SELECT count(*) FROM appointments WHERE modality NOT IN ('PRESENCIAL','VIRTUAL')"))==0
        assert db.scalar(text("SELECT count(*) FROM doctor_availability WHERE modalities @> '[\"PRESENCIAL\"]'::jsonb"))>0

@pytest.mark.parametrize('table,where',[('doctors','id = 1'),('doctor_availability','id = 1'),('plans',"name = 'Básico'")])
def test_modality_database_constraints_reject_unknown_values(patient,table,where):
    with pytest.raises(IntegrityError):
        with SessionLocal.begin() as db:
            db.execute(text(f"UPDATE {table} SET modalities = '[\"WEBRTC\"]'::jsonb WHERE {where}"))
