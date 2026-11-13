import json
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func,event
from sqlalchemy.exc import OperationalError,IntegrityError
from app.main import app
from app.db.session import SessionLocal
from app.core.security import passwords,digest
from app.models.entities import *
from app.services.doctor_accounts import provision
from app.services import clinical_history
from conftest import activate,register_patient
from test_doctor_portal import medic, reserve, PASSWORD


@pytest.fixture
def accounts():
    with SessionLocal.begin() as db:
        return provision(db,db.get(User,1))['new_credentials']


def login_as(record,rotate=True):
    client=TestClient(app)
    result=client.post('/api/auth/login',json={'email':record['email'],'password':record['temporary_password']})
    assert result.status_code==200
    if rotate:
        new=uuid4().hex+'Aa1!'
        changed=client.post('/api/doctor/password',json={'current_password':record['temporary_password'],'new_password':new,'confirm_password':new})
        assert changed.status_code==200,changed.text
    return client


def test_all_professionals_provisioned_individually_existing_password_preserved(accounts):
    assert len(accounts)==4
    assert len({r['email'] for r in accounts})==4 and len({r['temporary_password'] for r in accounts})==4
    with SessionLocal.begin() as db:
        before={u.id:u.password_hash for u in db.scalars(select(User))}
        result=provision(db,db.get(User,1))
        assert not result['new_credentials'] and len(result['preserved_doctor_ids'])==5
        assert {u.id:u.password_hash for u in db.scalars(select(User))}==before
        assert db.scalar(select(func.count()).select_from(DoctorAccount))==5
        for r in accounts:
            assert passwords.verify(r['temporary_password'],db.get(User,r['user_id']).password_hash)
            assert db.get(DoctorCredentialState,r['user_id']).must_change_password
    for record in accounts:
        with login_as(record) as client:
            assert client.get('/api/doctor/me').status_code==200
            assert client.get('/api/doctor/appointments').json()==[]


def test_new_and_disabled_professionals_can_be_provisioned_without_duplicate_links():
    with SessionLocal.begin() as db:
        doctor=Doctor(name='Profesional futuro ficticio',specialty_id=1,bio='Perfil de prueba académica',modalities=['PRESENCIAL'],enabled=False)
        db.add(doctor);db.flush()
        created=provision(db,db.get(User,1))['new_credentials']
        account=next(r for r in created if r['doctor_id']==doctor.id)
        assert db.get(User,account['user_id']).status=='DISABLED'
    with TestClient(app) as client:
        assert client.post('/api/auth/login',json={'email':account['email'],'password':account['temporary_password']}).status_code==403


def test_provision_avoids_case_insensitive_email_collisions():
    with SessionLocal.begin() as db:
        existing=User(name='Cuenta existente',email='MEDICO-1@VITALSYNC.DEMO',role='PATIENT',password_hash=passwords.hash(uuid4().hex))
        db.add(existing);db.flush()
        before=existing.password_hash
        result=provision(db,db.get(User,1))
        created=next(r for r in result['new_credentials'] if r['doctor_id']==1)
        assert created['email']!='medico-1@vitalsync.demo'
        assert existing.password_hash==before and existing.role=='PATIENT'


def test_temporary_password_requires_rotation_and_is_not_in_api(accounts):
    record=accounts[0]
    with login_as(record,rotate=False) as client:
        me=client.get('/api/auth/me').json()
        assert me['must_change_password'] is True
        assert record['temporary_password'] not in json.dumps(me)
        assert client.get('/api/doctor/dashboard').status_code==403
        wrong={'current_password':uuid4().hex,'new_password':uuid4().hex+'Aa1!'};wrong['confirm_password']=wrong['new_password']
        assert client.post('/api/doctor/password',json=wrong).status_code==400
        new=uuid4().hex+'Aa1!'
        assert client.post('/api/doctor/password',json={'current_password':record['temporary_password'],'new_password':new,'confirm_password':new}).status_code==200
        assert client.get('/api/auth/me').json()['must_change_password'] is False
        assert client.get('/api/doctor/dashboard').status_code==200
        assert client.post('/api/auth/login',json={'email':record['email'],'password':record['temporary_password']}).status_code==401
        assert client.post('/api/auth/login',json={'email':record['email'],'password':new}).status_code==200


def test_seed_only_explicit_demo_patients_is_idempotent_and_preserves_existing():
    with SessionLocal.begin() as db:
        result=clinical_history.seed_histories(db,include_extra_patients=True)
        assert result=={'histories_created':2,'patients_created':2}
        assert db.scalar(select(func.count()).select_from(ClinicalHistory))==3
        assert db.scalar(select(func.count()).select_from(ClinicalEncounter))==9
        existing=db.scalar(select(ClinicalBackground).order_by(ClinicalBackground.id));existing.description='Registro ficticio existente conservado'
        before=(db.scalar(select(func.count()).select_from(User)),db.scalar(select(func.count()).select_from(Appointment)))
        assert clinical_history.seed_histories(db,True)=={'histories_created':0,'patients_created':0}
        assert existing.description=='Registro ficticio existente conservado'
        assert before==(db.scalar(select(func.count()).select_from(User)),db.scalar(select(func.count()).select_from(Appointment)))


def test_unknown_patient_never_receives_invented_clinical_data(client):
    r=register_patient(client,'Paciente No Clasificado','not-demo-'+uuid4().hex+'@example.com','PacientePrueba2026!')
    assert r.status_code==201
    with SessionLocal.begin() as db:
        clinical_history.seed_histories(db,True)
        assert db.get(DemoPatient,r.json()['id']) is None
        assert not db.scalar(select(ClinicalHistory.id).where(ClinicalHistory.patient_id==r.json()['id']))


def test_seed_is_disabled_outside_demo(monkeypatch):
    monkeypatch.setattr(clinical_history,'DEMO_MODE',False)
    with SessionLocal.begin() as db:
        before=db.scalar(select(func.count()).select_from(ClinicalHistory))
        assert clinical_history.seed_histories(db,True)=={'histories_created':0,'patients_created':0}
        assert db.scalar(select(func.count()).select_from(ClinicalHistory))==before


@pytest.mark.parametrize('status',['CONFIRMED','IN_PROGRESS','ATTENDED'])
def test_treating_doctor_can_read_and_reads_are_audited(patient,medic,status):
    aid=reserve(patient)
    with SessionLocal.begin() as db:
        db.get(Appointment,aid).status=status
    root='/api/doctor/patients/2/clinical-history'
    response=medic.get(root);assert response.status_code==200,response.text
    data=response.json()
    assert data['demo_marker']==clinical_history.MARKER and data['read_only']
    assert len(data['backgrounds'])==4 and data['allergies'] and data['medications']
    assert data['patient']['age'] is None
    assert not {'document_number','phone','email','password_hash'} & data['patient'].keys()
    assert [v['occurred_at'] for v in data['encounters']]==sorted([v['occurred_at'] for v in data['encounters']],reverse=True)
    encounter=medic.get(root+'/encounters/'+str(data['encounters'][0]['id']))
    assert encounter.status_code==200 and encounter.json()['vitals']['spo2']==98
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action=='CLINICAL_HISTORY_VIEWED'))==1
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action=='CLINICAL_ENCOUNTER_VIEWED'))==1


@pytest.mark.parametrize('status',['CANCELLED','PATIENT_ABSENT','DOCTOR_ABSENT','TECHNICAL_ERROR'])
def test_cancelled_or_incident_alone_never_grants_clinical_access(patient,medic,status):
    aid=reserve(patient)
    with SessionLocal.begin() as db: db.get(Appointment,aid).status=status
    assert medic.get('/api/doctor/patients/2/clinical-history').status_code==404
    assert medic.get('/api/doctor/patients/2').json()['clinical_history_available'] is False


def test_other_doctor_patient_admin_and_anonymous_cannot_read_clinical_content(patient,medic,accounts):
    reserve(patient)
    root='/api/doctor/patients/2/clinical-history'
    unrelated=next(r for r in accounts if r['doctor_id']==3)
    with login_as(unrelated) as other:
        assert other.get(root).status_code==404
        assert other.get(root+'/encounters/1').status_code==404
    assert patient.get(root).status_code==403
    with TestClient(app) as anonymous: assert anonymous.get(root).status_code==401
    token=uuid4().hex
    with SessionLocal.begin() as db:
        db.add(SessionToken(token_hash=digest(token),user_id=1,expires_at=now()+__import__('datetime').timedelta(hours=1)))
    with TestClient(app,cookies={'vitalsync_session':token}) as admin:
        assert admin.get(root).status_code==403
        assert admin.get(root+'/encounters/1').status_code==403


def test_encounter_idor_between_histories_is_rejected(patient,medic):
    reserve(patient)
    with SessionLocal.begin() as db:
        clinical_history.seed_histories(db,True)
        another=db.scalar(select(ClinicalHistory).where(ClinicalHistory.patient_id!=2))
        encounter=db.scalar(select(ClinicalEncounter).where(ClinicalEncounter.history_id==another.id))
    assert medic.get(f'/api/doctor/patients/2/clinical-history/encounters/{encounter.id}').status_code==404
    assert medic.get(f'/api/doctor/patients/{another.patient_id}/clinical-history/encounters/{encounter.id}').status_code==404


def test_cancelling_only_valid_relationship_revokes_access_and_retains_record(patient,medic):
    aid=reserve(patient)
    assert medic.get('/api/doctor/patients/2/clinical-history').status_code==200
    assert medic.post(f'/api/doctor/appointments/{aid}/cancel',json={'version':1,'reason':'Cancelación de prueba','confirmed':True}).status_code==200
    assert medic.get('/api/doctor/patients/2/clinical-history').status_code==404
    with SessionLocal() as db: assert db.scalar(select(func.count()).select_from(ClinicalHistory))==1


@pytest.mark.parametrize('disabled',['account','professional'])
def test_disabled_doctor_cannot_read_clinical_history(patient,medic,disabled):
    reserve(patient)
    with SessionLocal.begin() as db:
        if disabled=='professional': db.get(Doctor,2).enabled=False
        else: db.scalar(select(User).where(User.email=='medico@vitalsync.demo')).status='DISABLED'
    assert medic.get('/api/doctor/patients/2/clinical-history').status_code in [401,403]


def test_clinical_response_is_not_delivered_if_audit_fails(patient,medic):
    reserve(patient)
    def fail(mapper,connection,target):
        if target.action=='CLINICAL_HISTORY_VIEWED': raise OperationalError('audit',{},Exception('Injected failure'))
    event.listen(AuditEvent,'before_insert',fail)
    try:
        result=medic.get('/api/doctor/patients/2/clinical-history')
        assert result.status_code==503 and 'backgrounds' not in result.json()
    finally: event.remove(AuditEvent,'before_insert',fail)


def test_clinical_data_is_not_exposed_by_general_endpoints_and_is_read_only(patient,medic):
    aid=reserve(patient)
    for path in ['/api/auth/me','/api/appointments','/api/dashboard','/api/doctor/patients','/api/doctor/appointments']:
        response=(medic if '/doctor/' in path else patient).get(path)
        assert response.status_code==200
        assert clinical_history.MARKER not in response.text
    assert medic.post('/api/doctor/patients/2/clinical-history',json={}).status_code==405
    assert medic.patch('/api/doctor/patients/2/clinical-history',json={}).status_code==405
    assert medic.get('/api/doctor/patients/999999/clinical-history').status_code==404
