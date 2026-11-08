from sqlalchemy import select
from app.models.entities import Doctor, Specialty, Appointment, Plan

def doctors_query():
    return select(Doctor, Specialty).join(Specialty, Specialty.id == Doctor.specialty_id)

def appointments_query(patient_id):
    return select(Appointment, Doctor, Specialty, Plan).join(Doctor, Doctor.id == Appointment.doctor_id).join(Specialty, Specialty.id == Doctor.specialty_id).join(Plan, Plan.id == Appointment.plan_id).where(Appointment.patient_id == patient_id)

def doctor_dict(d, s):
    return dict(id=d.id, name=d.name, specialty_id=s.id, specialty=s.name, bio=d.bio, enabled=d.enabled, modalities=d.modalities)

def appointment_dict(a, d, s, p):
    return dict(id=a.id, code=a.code, patient_id=a.patient_id, doctor=d.name, specialty=s.name, plan=p.name, starts_at=a.starts_at, ends_at=a.ends_at, modality=a.modality, status=a.status, version=a.version, copay=a.copay, cancelled_at=a.cancelled_at, cancellation_reason=a.cancellation_reason, economic_review=a.economic_review)
