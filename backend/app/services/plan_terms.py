"""Versioned catalogue versus the conditions actually purchased by each patient."""
from types import SimpleNamespace
from sqlalchemy import select,func
from app.models.entities import PlanRule,SubscriptionTerms,PaymentTerms,AppointmentSnapshot,Appointment,Hold,PatientPlan,Doctor,Specialty,Plan,now
from fastapi import HTTPException

def catalog(db,plan):
    r=db.get(PlanRule,plan.id)
    result={k:getattr(plan,k) for k in ['id','name','description','price','duration_days','copay','specialty_ids','modalities','enabled']}
    result.update(copays={'VIRTUAL':r.virtual_copay if r and r.virtual_copay is not None else plan.copay,'PRESENCIAL':r.onsite_copay if r and r.onsite_copay is not None else plan.copay},consultation_limit=r.consultation_limit if r else None,benefits=r.benefits if r else '',restrictions=r.restrictions if r else '',version=r.version if r else 1)
    return result

def subscription(db,pp):
    row=db.get(SubscriptionTerms,pp.patient_id)
    return dict(row.terms) if row and row.plan_id==pp.plan_id else catalog(db,db.get(Plan,pp.plan_id))

def capture_payment(db,payment,plan):
    terms=catalog(db,plan)
    db.add(PaymentTerms(payment_id=payment.id,terms=terms))
    return terms

def purchase(db,payment,plan):
    row=db.get(PaymentTerms,payment.id)
    return dict(row.terms) if row else catalog(db,plan)

def activate(db,pp,terms):
    row=db.get(SubscriptionTerms,pp.patient_id)
    if not row:
        row=SubscriptionTerms(patient_id=pp.patient_id,plan_id=pp.plan_id,terms=terms);db.add(row)
    row.plan_id=pp.plan_id;row.terms=terms;row.contracted_at=now()

def quota(db,patient_id,terms,exclude_hold=None):
    limit=terms.get('consultation_limit')
    if limit is None:return
    pp=db.get(PatientPlan,patient_id)
    conditions=(Appointment.patient_id==patient_id,Appointment.plan_id==pp.plan_id,Appointment.starts_at>=now(),Appointment.starts_at<pp.expires_at,Appointment.status.in_(['CONFIRMED','IN_PROGRESS','ATTENDED','TECHNICAL_ERROR','PATIENT_ABSENT']))
    # Attended consultations count even when their date is already in the past within this contract.
    contract=db.get(SubscriptionTerms,patient_id)
    since=contract.contracted_at if contract else now()
    used=db.scalar(select(func.count()).select_from(Appointment).where(Appointment.patient_id==patient_id,Appointment.plan_id==pp.plan_id,Appointment.starts_at>=since,Appointment.starts_at<pp.expires_at,Appointment.status.in_(['CONFIRMED','IN_PROGRESS','ATTENDED','TECHNICAL_ERROR','PATIENT_ABSENT'])))
    q=select(func.count()).select_from(Hold).where(Hold.patient_id==patient_id,Hold.plan_id==pp.plan_id,Hold.status=='ACTIVE',Hold.expires_at>now())
    if exclude_hold is not None:q=q.where(Hold.id!=exclude_hold)
    if used+db.scalar(q)>=limit:raise HTTPException(409,'Se agotaron las consultas incluidas en tu contratación vigente')

def record_appointment(db,a):
    doctor=db.get(Doctor,a.doctor_id)
    pp=db.get(PatientPlan,a.patient_id)
    db.add(AppointmentSnapshot(appointment_id=a.id,terms={'plan':subscription(db,pp)['name'],'doctor':doctor.name,'specialty':db.get(Specialty,doctor.specialty_id).name,'copay':a.copay,'origin':'BOOKING'}))
