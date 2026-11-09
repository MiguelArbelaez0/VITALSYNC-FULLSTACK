from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, UniqueConstraint, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from app.db.session import Base

def now():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String(254), unique=True, nullable=False)
    name = Column(String(120), nullable=False)
    password_hash = Column(Text, nullable=False)
    role = Column(String(16), nullable=False, default='PATIENT')
    __table_args__ = (CheckConstraint("role IN ('PATIENT','ADMIN','DOCTOR')"),)

class Patient(Base):
    __tablename__ = 'patients'
    id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    phone = Column(String(30), default='', nullable=False)

class SessionToken(Base):
    __tablename__ = 'sessions'
    token_hash = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)

class Specialty(Base):
    __tablename__ = 'specialties'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)

class Doctor(Base):
    __tablename__ = 'doctors'
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False, unique=True)
    specialty_id = Column(Integer, ForeignKey('specialties.id'), nullable=False, index=True)
    bio = Column(Text, nullable=False)
    modalities = Column(JSONB, nullable=False, default=lambda: ['PRESENCIAL'])
    enabled = Column(Boolean, default=True, nullable=False)
    __table_args__ = (
        CheckConstraint("jsonb_typeof(modalities) = 'array' AND modalities <> '[]'::jsonb AND modalities <@ '[\"PRESENCIAL\",\"VIRTUAL\"]'::jsonb", name='ck_doctors_modalities'),
        Index('ix_doctors_modalities_gin', 'modalities', postgresql_using='gin'),
    )

class Availability(Base):
    __tablename__ = 'doctor_availability'
    id = Column(Integer, primary_key=True)
    doctor_id = Column(Integer, ForeignKey('doctors.id'), nullable=False, index=True)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    published_by = Column(Integer, ForeignKey('users.id'), nullable=False)
    published = Column(Boolean, default=True, nullable=False)
    modalities = Column(JSONB, nullable=False, default=lambda: ['PRESENCIAL'])
    __table_args__ = (
        UniqueConstraint('doctor_id', 'starts_at'),
        CheckConstraint('ends_at > starts_at'),
        CheckConstraint("jsonb_typeof(modalities) = 'array' AND modalities <> '[]'::jsonb AND modalities <@ '[\"PRESENCIAL\",\"VIRTUAL\"]'::jsonb", name='ck_doctor_availability_modalities'),
        Index('ix_doctor_availability_modalities_gin', 'modalities', postgresql_using='gin'),
    )

class DoctorBlock(Base):
    __tablename__ = 'doctor_blocks'
    id = Column(Integer, primary_key=True)
    doctor_id = Column(Integer, ForeignKey('doctors.id'), nullable=False, index=True)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    reason = Column(Text, nullable=False)
    __table_args__ = (UniqueConstraint('doctor_id', 'starts_at'), CheckConstraint('ends_at > starts_at'))

class Plan(Base):
    __tablename__ = 'plans'
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(Text, nullable=False)
    price = Column(Integer, nullable=False)
    duration_days = Column(Integer, default=30, nullable=False)
    copay = Column(Integer, nullable=False)
    specialty_ids = Column(JSONB, nullable=False)
    modalities = Column(JSONB, nullable=False, default=lambda: ['PRESENCIAL'])
    enabled = Column(Boolean, default=True, nullable=False)
    __table_args__ = (
        CheckConstraint('price >= 0 AND copay >= 0 AND duration_days > 0'),
        CheckConstraint("jsonb_typeof(modalities) = 'array' AND modalities <> '[]'::jsonb AND modalities <@ '[\"PRESENCIAL\",\"VIRTUAL\"]'::jsonb", name='ck_plans_modalities'),
    )

class PatientPlan(Base):
    __tablename__ = 'patient_plans'
    patient_id = Column(Integer, ForeignKey('patients.id'), primary_key=True)
    plan_id = Column(Integer, ForeignKey('plans.id'), nullable=False)
    status = Column(String(16), nullable=False, default='ACTIVE')
    expires_at = Column(DateTime(timezone=True), nullable=False)
    cancelled_at = Column(DateTime(timezone=True))
    cancelled_by = Column(Integer, ForeignKey('users.id'))
    __table_args__ = (CheckConstraint("status IN ('ACTIVE','INACTIVE')"),)

class PatientPlanCancellation(Base):
    __tablename__ = 'patient_plan_cancellations'
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey('patients.id'), nullable=False, index=True)
    plan_id = Column(Integer, ForeignKey('plans.id'), nullable=False, index=True)
    changed_by = Column(Integer, ForeignKey('users.id'), nullable=False)
    previous_status = Column(String(16), nullable=False)
    new_status = Column(String(16), nullable=False)
    policy = Column(String(16), nullable=False, default='IMMEDIATE')
    reason = Column(Text, nullable=False)
    cancelled_at = Column(DateTime(timezone=True), nullable=False, default=now)
    effective_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (
        CheckConstraint("previous_status = 'ACTIVE' AND new_status = 'INACTIVE'"),
        CheckConstraint("policy = 'IMMEDIATE'"),
    )

class Hold(Base):
    __tablename__ = 'appointment_holds'
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey('patients.id'), nullable=False, index=True)
    doctor_id = Column(Integer, ForeignKey('doctors.id'), nullable=False, index=True)
    availability_id = Column(Integer, ForeignKey('doctor_availability.id'), nullable=False)
    plan_id = Column(Integer, ForeignKey('plans.id'), nullable=False)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    copay = Column(Integer, nullable=False)
    modality = Column(String(12), nullable=False, default='PRESENCIAL')
    status = Column(String(16), default='ACTIVE', nullable=False)
    __table_args__ = (CheckConstraint("status IN ('ACTIVE','CONFIRMED','RELEASED')"), CheckConstraint("modality IN ('PRESENCIAL','VIRTUAL')"), CheckConstraint('ends_at > starts_at AND copay >= 0'))

class Payment(Base):
    __tablename__ = 'payments'
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey('patients.id'), nullable=False, index=True)
    idempotency_key = Column(String(80), unique=True, nullable=False)
    kind = Column(String(10), nullable=False)
    plan_id = Column(Integer, ForeignKey('plans.id'))
    hold_id = Column(Integer, ForeignKey('appointment_holds.id'), index=True)
    amount = Column(Integer, nullable=False)
    status = Column(String(24), nullable=False)
    created_at = Column(DateTime(timezone=True), default=now, nullable=False)
    __table_args__ = (CheckConstraint("status IN ('APPROVED','REJECTED','PENDING','IN_RECONCILIATION')"), CheckConstraint("(kind = 'PLAN' AND plan_id IS NOT NULL AND hold_id IS NULL) OR (kind = 'COPAY' AND hold_id IS NOT NULL AND plan_id IS NULL)"), CheckConstraint('amount >= 0'))

class Appointment(Base):
    __tablename__ = 'appointments'
    id = Column(Integer, primary_key=True)
    code = Column(String(30), nullable=False, unique=True)
    patient_id = Column(Integer, ForeignKey('patients.id'), nullable=False, index=True)
    doctor_id = Column(Integer, ForeignKey('doctors.id'), nullable=False, index=True)
    hold_id = Column(Integer, ForeignKey('appointment_holds.id'), unique=True, nullable=False)
    plan_id = Column(Integer, ForeignKey('plans.id'), nullable=False)
    payment_id = Column(Integer, ForeignKey('payments.id'), unique=True)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    copay = Column(Integer, nullable=False)
    modality = Column(String(12), nullable=False, default='PRESENCIAL')
    status = Column(String(16), nullable=False, default='CONFIRMED')
    version = Column(Integer, default=1, nullable=False)
    cancelled_at = Column(DateTime(timezone=True))
    cancelled_by = Column(Integer, ForeignKey('users.id'))
    cancellation_reason = Column(Text)
    economic_review = Column(Boolean, default=False, nullable=False)
    __table_args__ = (CheckConstraint("status IN ('CONFIRMED','CANCELLED','ATTENDED')"), CheckConstraint("modality IN ('PRESENCIAL','VIRTUAL')"), CheckConstraint('ends_at > starts_at'), Index('uq_confirmed_slot', 'doctor_id', 'starts_at', unique=True, postgresql_where=(status == 'CONFIRMED')))

class VirtualConsultation(Base):
    __tablename__ = 'virtual_consultations'
    appointment_id = Column(Integer, ForeignKey('appointments.id'), primary_key=True)
    patient_id = Column(Integer, ForeignKey('patients.id'), nullable=False, index=True)
    doctor_id = Column(Integer, ForeignKey('doctors.id'), nullable=False, index=True)
    status = Column(String(24), nullable=False, default='PROGRAMADA')
    updated_at = Column(DateTime(timezone=True), default=now, nullable=False)
    __table_args__ = (CheckConstraint("status IN ('PROGRAMADA','SALA_DISPONIBLE','PACIENTE_EN_ESPERA','MEDICO_EN_ESPERA','EN_ATENCION','FINALIZADA','PACIENTE_AUSENTE','MEDICO_AUSENTE','CANCELADA')"),)

class StatusHistory(Base):
    __tablename__ = 'appointment_status_history'
    id = Column(Integer, primary_key=True)
    appointment_id = Column(Integer, ForeignKey('appointments.id'), nullable=False, index=True)
    status = Column(String(32), nullable=False)
    author_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now, nullable=False)

class Notification(Base):
    __tablename__ = 'notifications'
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey('patients.id'), nullable=False, index=True)
    message = Column(Text, nullable=False)
    read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now, nullable=False)

class AuditEvent(Base):
    __tablename__ = 'audit_events'
    id = Column(Integer, primary_key=True)
    actor_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    action = Column(String(60), nullable=False)
    entity_id = Column(Integer)
    created_at = Column(DateTime(timezone=True), default=now, nullable=False)
