from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func, event
from sqlalchemy.exc import OperationalError, IntegrityError
from app.main import app
from app.core.security import passwords
from app.db.session import SessionLocal
from app.models.entities import User, Doctor, DoctorAccount, Appointment, VirtualConsultation, Notification, AuditEvent, StatusHistory, now
from app.routers import doctor as routes
from app.services import doctor_portal
from app.seed import seed
from conftest import activate

PASSWORD = 'DoctorPrueba2026!'


@pytest.fixture
def medic():
    with SessionLocal.begin() as db:
        user = db.scalar(select(User).where(User.email == 'medico@vitalsync.demo'))
        user.password_hash = passwords.hash(PASSWORD)
    with TestClient(app) as client:
        result = client.post('/api/auth/login', json={'email':'medico@vitalsync.demo','password':PASSWORD})
        assert result.status_code == 200, result.text
        assert result.json()['role'] == 'DOCTOR' and result.json()['doctor_id'] == 2
        assert 'HttpOnly' in result.headers['set-cookie']
        yield client


def reserve(patient, doctor=2, modality='VIRTUAL'):
    activate(patient, 'Premium')
    slot = next(s for s in patient.get(f'/api/doctors/{doctor}/availability?modality={modality}').json() if s['available'])
    hold = patient.post('/api/holds', json={'availability_id':slot['id'],'modality':modality})
    assert hold.status_code == 201, hold.text
    result = patient.post(f"/api/holds/{hold.json()['id']}/confirm")
    assert result.status_code == 200, result.text
    return result.json()['id']


def operation(medic, aid, event_name):
    return medic.post(f'/api/doctor/appointments/{aid}/teleconsult/events', json={'event':event_name})


@pytest.mark.parametrize('path', ['/dashboard','/appointments','/my-plan','/payments','/notifications'])
def test_medical_sessions_cannot_read_patient_endpoints(medic, path):
    assert medic.get('/api' + path).status_code == 403


@pytest.mark.parametrize('path', ['/me','/dashboard','/appointments','/patients','/availability'])
def test_patient_cannot_read_medical_endpoints(patient, path):
    assert patient.get('/api/doctor' + path).status_code == 403


def test_unlinked_disabled_and_admin_accounts_are_refused(client):
    with SessionLocal.begin() as db:
        db.add(User(name='Sin perfil', email='unlinked@example.com', role='DOCTOR', password_hash=passwords.hash(PASSWORD)))
    assert client.post('/api/auth/login', json={'email':'unlinked@example.com','password':PASSWORD}).status_code == 403
    assert client.post('/api/auth/login', json={'email':'admin@vitalsync.demo','password':'AdminDemo2026!'}).status_code == 403
    assert client.post('/api/auth/register', json={'role':'DOCTOR'}).status_code == 422
    assert client.get('/api/doctor/dashboard').status_code == 401


def test_removed_profile_revokes_existing_session(medic):
    with SessionLocal.begin() as db:
        db.delete(db.scalar(select(DoctorAccount).where(DoctorAccount.doctor_id == 2)))
    assert medic.get('/api/auth/me').status_code == 403
    assert medic.get('/api/doctor/dashboard').status_code == 403


def test_own_appointments_and_patient_projection_only(patient, medic):
    mine, other = reserve(patient), reserve(patient, doctor=1)
    listed = medic.get('/api/doctor/appointments?doctor_id=1').json()
    assert [a['id'] for a in listed] == [mine]
    assert medic.get(f'/api/doctor/appointments/{other}').status_code == 404
    assert operation(medic, other, 'ADVANCE_DEMO_CLOCK').status_code == 404
    assert medic.post(f'/api/doctor/appointments/{other}/cancel', json={'version':1,'reason':'Prueba ajena','confirmed':True}).status_code == 404
    detail = medic.get(f'/api/doctor/appointments/{mine}').json()
    assert detail['patient'] and detail['duration_minutes'] == 30 and detail['history']
    assert not {'copay','payment_id','plan','phone','document_number','email','password_hash'} & detail.keys()
    patients = medic.get('/api/doctor/patients?search=Valentina').json()
    assert patients == [{'id':2,'name':'Valentina Torres'}]
    related = medic.get('/api/doctor/patients/2').json()
    assert [a['id'] for a in related['appointments']] == [mine]
    assert medic.get('/api/doctor/patients/99999').status_code == 404
    assert medic.get('/api/doctor/patients?search=NoExiste').json() == []


def test_dashboard_date_filters_and_availability_use_persisted_data(patient, medic):
    virtual, onsite = reserve(patient), reserve(patient, modality='PRESENCIAL')
    start, _ = doctor_portal.day_bounds(now().astimezone(doctor_portal.BOGOTA).date())
    with SessionLocal.begin() as db:
        for aid, hour in [(virtual,10),(onsite,11)]:
            a = db.get(Appointment, aid); a.starts_at=start+timedelta(hours=hour); a.ends_at=a.starts_at+timedelta(minutes=30)
    dashboard = medic.get('/api/doctor/dashboard').json()
    assert dashboard['timezone'] == 'America/Bogota'
    assert dashboard['metrics'] == dict(total=2,virtual=1,presencial=1,pending=2,completed=0)
    assert len(dashboard['agenda']) == 2
    assert [a['id'] for a in medic.get(f"/api/doctor/appointments?day={dashboard['date']}&modality=PRESENCIAL&status=CONFIRMED").json()] == [onsite]
    schedule = medic.get('/api/doctor/availability?day=' + (start.date()+timedelta(days=1)).isoformat()).json()
    assert schedule['read_only'] and schedule['slots'] and schedule['blocks']
    assert medic.post('/api/doctor/availability', json={}).status_code == 405


def test_medical_cancel_within_patient_deadline_notifies_and_keeps_history(patient, medic):
    aid = reserve(patient)
    with SessionLocal.begin() as db:
        a = db.get(Appointment, aid); a.starts_at=now()+timedelta(minutes=30); a.ends_at=a.starts_at+timedelta(minutes=30)
    body = {'version':1,'reason':'Indisponibilidad del profesional','confirmed':True}
    assert patient.post(f'/api/appointments/{aid}/cancel',json=body).status_code == 409
    assert medic.post(f'/api/doctor/appointments/{aid}/cancel',json=body | {'reason':' '}).status_code == 422
    assert medic.post(f'/api/doctor/appointments/{aid}/cancel',json=body | {'confirmed':False}).status_code == 422
    assert medic.post(f'/api/doctor/appointments/{aid}/cancel',json=body | {'version':2}).status_code == 409
    assert medic.post(f'/api/doctor/appointments/{aid}/cancel',json=body).status_code == 200
    assert medic.post(f'/api/doctor/appointments/{aid}/cancel',json=body).status_code == 409
    detail = patient.get(f'/api/appointments/{aid}').json()
    assert detail['status'] == 'CANCELLED' and detail['history'][-1]['reason'].startswith('Cancelación médica')
    assert any('Indisponibilidad del profesional' in n['message'] for n in patient.get('/api/notifications').json())
    with SessionLocal() as db:
        assert db.get(VirtualConsultation, aid).status == 'CANCELADA'
        a=db.get(Appointment,aid)
        assert a.cancelled_by == db.scalar(select(DoctorAccount.user_id).where(DoctorAccount.doctor_id == 2))
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id==aid,AuditEvent.action=='DOCTOR_APPOINTMENT_CANCELLED')) == 1


def test_shared_simulation_requires_presences_and_finishes_both_portals(patient, medic):
    aid = reserve(patient)
    assert operation(medic, aid, 'START').status_code == 409
    for event_name in ['ADVANCE_DEMO_CLOCK','OPEN_ROOM','DOCTOR_JOIN']:
        assert operation(medic, aid, event_name).status_code == 200
    assert operation(medic, aid, 'START').status_code == 409
    assert patient.post(f'/api/appointments/{aid}/teleconsult/status',json={'event':'PATIENT_JOIN'}).status_code == 200
    assert operation(medic, aid, 'START').status_code == 200
    assert operation(medic, aid, 'FINALIZE').status_code == 200
    p = patient.get(f'/api/appointments/{aid}').json()
    d = medic.get(f'/api/doctor/appointments/{aid}').json()
    assert p['status'] == d['status'] == 'ATTENDED'
    assert p['completion_source'] == d['completion_source'] == 'DEMO'
    assert p['simulated_completed_at'] == d['simulated_completed_at'] and d['clinically_attended'] is False
    assert not medic.get('/api/doctor/appointments?view=upcoming').json()
    assert medic.get('/api/doctor/appointments?view=history').json()[0]['id'] == aid
    assert not patient.get('/api/appointments?view=upcoming').json()
    assert patient.get('/api/appointments?view=completed').json()[0]['id'] == aid
    assert operation(medic, aid, 'FINALIZE').status_code == 409
    assert medic.post(f'/api/doctor/appointments/{aid}/cancel',json={'version':d['version'],'reason':'Ya finalizada','confirmed':True}).status_code == 409


@pytest.mark.parametrize('state', ['CANCELLED','ATTENDED','IN_PROGRESS','PATIENT_ABSENT','DOCTOR_ABSENT','TECHNICAL_ERROR'])
def test_terminal_or_unconfirmed_appointments_cannot_be_cancelled(patient, medic, state):
    aid=reserve(patient,modality='PRESENCIAL')
    with SessionLocal.begin() as db:
        db.get(Appointment,aid).status=state
    assert medic.post(f'/api/doctor/appointments/{aid}/cancel',json={'version':1,'reason':'No permitido','confirmed':True}).status_code==409


def test_demo_off_medical_room_has_no_actions(patient, medic, monkeypatch):
    aid=reserve(patient)
    monkeypatch.setattr(routes,'DEMO_MODE',False)
    assert medic.get(f'/api/doctor/appointments/{aid}/teleconsult').json()['virtual_state']['available_actions']==[]
    assert operation(medic,aid,'ADVANCE_DEMO_CLOCK').status_code==403
    assert patient.get(f'/api/appointments/{aid}').json()['status']=='CONFIRMED'


def test_simulated_technical_incident_recovers_and_absence_is_terminal(patient, medic):
    aid=reserve(patient)
    for name in ['ADVANCE_DEMO_CLOCK','OPEN_ROOM','TECHNICAL_ERROR','RETRY','PATIENT_ABSENT']:
        assert operation(medic,aid,name).status_code==200
    assert operation(medic,aid,'FINALIZE').status_code==409
    assert medic.get(f'/api/doctor/appointments/{aid}').json()['status']=='PATIENT_ABSENT'


def test_atomic_completion_rollback_and_concurrent_single_finalization(patient, medic):
    aid=reserve(patient)
    for name in ['ADVANCE_DEMO_CLOCK','OPEN_ROOM','PATIENT_JOIN','DOCTOR_JOIN','START']:
        assert operation(medic,aid,name).status_code==200
    def fail(mapper,connection,target):
        raise OperationalError('notification',{},Exception('Injected failure'))
    event.listen(Notification,'before_insert',fail)
    try:
        assert operation(medic,aid,'FINALIZE').status_code==503
    finally:
        event.remove(Notification,'before_insert',fail)
    assert patient.get(f'/api/appointments/{aid}').json()['status']=='IN_PROGRESS'
    cookies=dict(medic.cookies)
    def finish(_):
        with TestClient(app,cookies=cookies) as client:
            return operation(client,aid,'FINALIZE').status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(finish, range(2)))==[200,409]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id==aid,AuditEvent.action=='DOCTOR_SIMULATED_TELECONSULT_FINALIZE'))==1


def test_profile_fields_and_seed_are_safe_and_idempotent(medic):
    original=medic.get('/api/doctor/me').json()
    assert medic.patch('/api/doctor/me',json={'bio':'Una biografía médica actualizada y suficiente.','name':'Otro médico'}).status_code==422
    assert medic.patch('/api/doctor/me',json={'bio':'Una biografía médica actualizada y suficiente.'}).status_code==200
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email=='medico@vitalsync.demo')); before=user.password_hash
        count=db.scalar(select(func.count()).select_from(Doctor))
    seed(); seed()
    with SessionLocal() as db:
        assert db.get(User,user.id).password_hash==before
        assert db.scalar(select(func.count()).select_from(Doctor))==count
        with pytest.raises(IntegrityError):
            db.add(DoctorAccount(user_id=user.id,doctor_id=1)); db.flush()
    assert medic.get('/api/doctor/me').json()['name']==original['name']


@pytest.mark.parametrize('disabled', ['account','professional'])
def test_disabled_medical_accounts_or_professionals_lose_access(medic, disabled):
    with SessionLocal.begin() as db:
        if disabled == 'account':
            user=db.scalar(select(User).where(User.email=='medico@vitalsync.demo')); user.status='DISABLED'
        else:
            db.get(Doctor,2).enabled=False
    assert medic.post('/api/auth/login',json={'email':'medico@vitalsync.demo','password':PASSWORD}).status_code==403
    assert medic.get('/api/doctor/dashboard').status_code==(401 if disabled=='account' else 403)


def test_concurrent_medical_cancellation_is_recorded_once(patient, medic):
    aid=reserve(patient,modality='PRESENCIAL'); cookies=dict(medic.cookies)
    def cancel_one(_):
        with TestClient(app,cookies=cookies) as client:
            return client.post(f'/api/doctor/appointments/{aid}/cancel',json={'version':1,'reason':'Indisponibilidad médica concurrente','confirmed':True}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(cancel_one,range(2)))==[200,409]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id==aid,AuditEvent.action=='DOCTOR_APPOINTMENT_CANCELLED'))==1
        assert db.scalar(select(func.count()).select_from(Notification).where(Notification.message.contains('Indisponibilidad médica concurrente')))==1
