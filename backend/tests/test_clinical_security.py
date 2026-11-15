from concurrent.futures import ThreadPoolExecutor
from datetime import date
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func,event
from sqlalchemy.exc import OperationalError
from app.main import app
from app.db.session import SessionLocal
from app.models.entities import User,DoctorAccount,ClinicalHistory,AuditEvent
from app.core.security import passwords
from app.services.doctor_accounts import provision
from app.services.clinical_history import seed_histories
from test_clinical_history import accounts,login_as
from test_doctor_portal import medic,reserve

def test_concurrent_provision_creates_each_account_once():
 def run(_):
  with SessionLocal.begin() as db:return len(provision(db,db.get(User,1))['new_credentials'])
 with ThreadPoolExecutor(max_workers=2) as executor:counts=list(executor.map(run,range(2)))
 assert sorted(counts)==[0,4]
 with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(DoctorAccount))==5

def test_password_rotation_revokes_other_sessions(accounts):
 record=accounts[0]
 with login_as(record,False) as first,login_as(record,False) as second:
  fresh=uuid4().hex+'Aa1!'
  assert first.post('/api/doctor/password',json={'current_password':record['temporary_password'],'new_password':fresh,'confirm_password':fresh}).status_code==200
  assert first.get('/api/doctor/me').status_code==200
  assert second.get('/api/auth/me').status_code==401

def test_failed_password_audit_rolls_back_password(accounts):
 record=accounts[0]
 def fail(mapper,connection,target):
  if target.action=='DOCTOR_PASSWORD_CHANGED':raise OperationalError('audit',{},Exception('Injected'))
 with login_as(record,False) as client:
  event.listen(AuditEvent,'before_insert',fail)
  try:
   fresh=uuid4().hex+'Aa1!'
   assert client.post('/api/doctor/password',json={'current_password':record['temporary_password'],'new_password':fresh,'confirm_password':fresh}).status_code==503
  finally:event.remove(AuditEvent,'before_insert',fail)
 with SessionLocal() as db:assert passwords.verify(record['temporary_password'],db.get(User,record['user_id']).password_hash)

def test_age_is_calculated_only_when_birth_date_exists(patient,medic):
 reserve(patient)
 with SessionLocal.begin() as db:db.scalar(select(ClinicalHistory)).birth_date=date(2000,1,1)
 result=medic.get('/api/doctor/patients/2/clinical-history');assert result.status_code==200
 assert result.json()['patient']['age']>=26

def test_collision_never_relabels_unknown_user_or_partially_seeds():
 with SessionLocal.begin() as db:
  db.add(User(name='Registro no clasificado',email='demo.santiago@vitalsync.demo',role='PATIENT',password_hash=passwords.hash(uuid4().hex)))
 with pytest.raises(ValueError):
  with SessionLocal.begin() as db:seed_histories(db,True)
 with SessionLocal() as db:
  assert db.scalar(select(func.count()).select_from(ClinicalHistory))==1
  assert db.scalar(select(User).where(User.email=='demo.lucia@vitalsync.demo')) is None
