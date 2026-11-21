from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.main import app
from app.db.session import SessionLocal
from app.models.entities import User, Doctor, DoctorAccount, DoctorApplication, DoctorCredentialDelivery, SessionToken
from app.core.security import passwords
from app.services import medical_registration as service
from conftest import ADMIN_TEST_PASSWORD, PATIENT_TEST_PASSWORD, register_patient
from test_admin_portal import login_admin

def payload(**overrides):
    return dict(given_names='María Elena', surnames='Gómez Torres', document_type='CC',
        document_number='9988776655', specialty_id=1, professional_number='REG-9911',
        contact_email='medica@example.com', phone='3001234567', bio='Profesional ficticia para pruebas de registro académico.', privacy_accepted=True, **overrides)

def submit(client, data=None):
    result=client.post('/api/auth/doctor-applications', json=data or payload())
    assert result.status_code==201, result.text
    return result.json()

def approve(client, row):
    result=client.post(f"/api/admin/doctor-applications/{row['id']}/approve",json={
        'version':1,'reason':'Revisión académica de datos ficticios','professional_review_confirmed':True,'verification_kind':'ACADEMIC_SIMULATED'})
    assert result.status_code==200, result.text
    return result.json()

def delivered(row):
    with SessionLocal.begin() as db:
        actor=db.scalar(select(User).where(User.role=='ADMIN'))
        return service.deliver(db,actor,row['delivery_id'])

def test_pending_normalization_reserved_email_and_rejection(client):
    proposed=client.post('/api/auth/doctor-applications/preview',json={'given_names':'  María Elena ', 'surnames':'Gómez Torres'}).json()
    assert proposed['institutional_email']=='maria.gomez@doctor.vitalsync.demo' and not proposed['reserved']
    row=submit(client)
    assert row['status']=='PENDING' and len(row['receipt'])>=32
    with SessionLocal() as db:
        assert not db.scalar(select(User.id).where(User.email==row['institutional_email']))
        assert db.scalar(select(DoctorApplication)).receipt_hash != row['receipt']
    assert client.get('/api/doctor/dashboard').status_code==401
    assert client.post('/api/auth/doctor-applications',json=payload()).status_code==409
    assert register_patient(client,'Intento Paciente',row['institutional_email'],'PacienteSeguro123!').status_code==409
    login_admin(client)
    rejected=client.post(f"/api/admin/doctor-applications/{row['id']}/reject",json={'version':1,'reason':'Datos profesionales ficticios incompletos'})
    assert rejected.status_code==200 and rejected.json()['status']=='REJECTED'
    status=client.post('/api/auth/doctor-applications/status',json={'receipt':row['receipt']}).json()
    assert status['status']=='REJECTED' and 'document_number' not in status
    assert client.post('/api/auth/doctor-applications/status',json={'receipt':'x'*43}).status_code==404

def test_approval_delivery_once_password_login_reset_and_preservation(client):
    with SessionLocal() as db:
        preserved={u.id:(u.email,u.password_hash) for u in db.scalars(select(User))}
        doctors=db.scalar(select(func.count()).select_from(Doctor))
    pending=submit(client)
    login_admin(client)
    row=approve(client,pending)
    assert approve(client,pending)['idempotent'] is True
    assert 'password' not in str(row).lower() and 'encrypted_secret' not in str(row)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Doctor))==doctors+1
        assert all((db.get(User,id).email,db.get(User,id).password_hash)==data for id,data in preserved.items())
        assert db.get(DoctorCredentialDelivery,row['delivery_id']).encrypted_secret
    secret=delivered(row)
    with pytest.raises(HTTPException): delivered(row)
    with SessionLocal() as db:
        delivery=db.get(DoctorCredentialDelivery,row['delivery_id'])
        assert delivery.encrypted_secret is None and delivery.status=='DELIVERED'
        assert passwords.verify(secret['password'],db.get(User,row['user_id']).password_hash)
    with TestClient(app) as doctor:
        assert doctor.post('/api/auth/login',json={'email':secret['email'],'password':secret['password']}).json()['role']=='DOCTOR'
        assert doctor.get('/api/doctor/dashboard').status_code==200
        assert doctor.get('/api/auth/me').json()['must_change_password'] is False
        assert doctor.get('/api/admin/doctor-applications').status_code==403
        wrong=client.post(f"/api/admin/accounts/{row['user_id']}/doctor-credentials",json={'current_password':'incorrecto123','reason':'Recuperación solicitada por titular'})
        assert wrong.status_code==403
        reset=client.post(f"/api/admin/accounts/{row['user_id']}/doctor-credentials",json={'current_password':ADMIN_TEST_PASSWORD,'reason':'Identidad del profesional comprobada para prueba'})
        assert reset.status_code==200,reset.text
        assert doctor.get('/api/doctor/dashboard').status_code==401
        assert doctor.post('/api/auth/login',json={'email':secret['email'],'password':secret['password']}).status_code==401
        second=delivered(reset.json())
        assert second['password']!=secret['password']
        assert doctor.post('/api/auth/login',json={'email':second['email'],'password':second['password']}).status_code==200
        assert client.post(f"/api/admin/accounts/{row['user_id']}/recovery",json={'reason':'Intento de recuperación médica por enlace'}).status_code==403
        with SessionLocal.begin() as db: db.get(Doctor,row['doctor_id']).enabled=False
        assert doctor.get('/api/doctor/dashboard').status_code==403

@pytest.mark.parametrize('extra',[{'role':'ADMIN'},{'role':'DOCTOR'},{'institutional_email':'admin@vitalsync.demo'},{'password':'ChosenPassword123!'}])
def test_manipulated_registration_rejected(client,extra):
    assert client.post('/api/auth/doctor-applications',json={**payload(),**extra}).status_code==422

def test_patient_cannot_review_or_request_medical_credentials(patient):
    row=submit(patient)
    assert patient.get('/api/admin/doctor-applications').status_code==403
    assert patient.post(f"/api/admin/doctor-applications/{row['id']}/approve",json={'version':1,'reason':'Intento sin permisos de administrador'}).status_code==403

def test_email_collisions_concurrent_submissions_are_stable(client):
    def send(index):
        data=payload();data.update(surnames=f'Gómez Apellido{index}', document_number=str(9000000000+index),professional_number=f'REG-{index:04}')
        with TestClient(app) as c: return submit(c,data)
    with ThreadPoolExecutor(max_workers=2) as pool: rows=list(pool.map(send,[1,2]))
    assert {r['institutional_email'] for r in rows}=={'maria.gomez@doctor.vitalsync.demo','maria.gomez.1@doctor.vitalsync.demo'}
    for row in rows:
        assert client.post('/api/auth/doctor-applications/status',json={'receipt':row['receipt']}).json()['institutional_email']==row['institutional_email']

def test_missing_delivery_key_rolls_back_approval(client,monkeypatch):
    row=submit(client);login_admin(client)
    monkeypatch.setattr(service,'DOCTOR_CREDENTIAL_KEY','')
    result=client.post(f"/api/admin/doctor-applications/{row['id']}/approve",json={'version':1,'reason':'Revisión académica de prueba','professional_review_confirmed':True,'verification_kind':'ACADEMIC_SIMULATED'})
    assert result.status_code==503
    with SessionLocal() as db:
        assert db.get(DoctorApplication,row['id']).status=='PENDING'
        assert not db.scalar(select(User.id).where(User.email==row['institutional_email']))

def test_concurrent_approval_creates_one_account_and_delivery(client):
    pending=submit(client)
    def run(_):
        with TestClient(app) as admin:
            login_admin(admin)
            return approve(admin,pending)
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(run,[1,2]))
    assert sorted(r['idempotent'] for r in results)==[False,True]
    assert len({r['user_id'] for r in results})==1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(DoctorCredentialDelivery))==1

def test_failed_review_audit_rolls_back_account_and_password(client):
    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError
    from app.models.entities import AdminEvent
    pending=submit(client);login_admin(client)
    def fail(mapper,connection,target):
        if target.action=='DOCTOR_APPLICATION_APPROVED': raise OperationalError('audit',{},Exception('Injected failure'))
    event.listen(AdminEvent,'before_insert',fail)
    try:
        result=client.post(f"/api/admin/doctor-applications/{pending['id']}/approve",json={'version':1,'reason':'Revisión académica de prueba','professional_review_confirmed':True,'verification_kind':'ACADEMIC_SIMULATED'})
        assert result.status_code==503
    finally: event.remove(AdminEvent,'before_insert',fail)
    with SessionLocal() as db:
        assert db.get(DoctorApplication,pending['id']).status=='PENDING'
        assert not db.scalar(select(User.id).where(User.email==pending['institutional_email']))
        assert db.scalar(select(func.count()).select_from(DoctorCredentialDelivery))==0

@pytest.mark.parametrize('domain',['gmail.com','outlook.com','example.org'])
def test_personal_email_registration_and_patient_password_change(client,domain):
    email=f'prueba.{uuid4().hex}@{domain}'
    old='PacienteSeguro123!';new='PacienteNueva456!'
    response=register_patient(client,'Paciente Prueba',email,old)
    assert response.status_code==201 and response.json()['role']=='PATIENT'
    assert client.post('/api/auth/password',json={'current_password':old,'new_password':new,'confirm_password':new}).status_code==200
    assert client.get('/api/auth/me').status_code==200
    client.post('/api/auth/logout')
    assert client.post('/api/auth/login',json={'email':email,'password':old}).status_code==401
    assert client.post('/api/auth/login',json={'email':email,'password':new}).status_code==200
