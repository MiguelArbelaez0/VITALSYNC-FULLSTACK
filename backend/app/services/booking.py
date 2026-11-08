from datetime import timedelta
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select, or_, and_
from app.models.entities import *
from app.core.config import HOLD_MINUTES, CANCELLATION_HOURS

def fail(message, code=409):
    raise HTTPException(code, message)

def lock_patient(db, patient_id):
    db.execute(select(Patient).where(Patient.id == patient_id).with_for_update()).scalar_one()

def lock_doctor(db, doctor_id):
    d = db.execute(select(Doctor).where(Doctor.id == doctor_id).with_for_update()).scalar_one_or_none()
    if not d or not d.enabled:
        fail('El médico no está disponible. Selecciona otro médico')
    return d

def active_plan(db, patient_id, specialty_id, modality='PRESENCIAL'):
    pp = db.get(PatientPlan, patient_id)
    if not pp or pp.status != 'ACTIVE':
        fail('Debes activar tu plan para solicitar una cita médica')
    if pp.expires_at <= now():
        fail('Tu plan ha vencido. Debes renovarlo para continuar')
    plan = db.get(Plan, pp.plan_id)
    if not plan.enabled or specialty_id not in plan.specialty_ids:
        fail('Tu plan no cubre esta especialidad. Consulta otro plan o especialidad')
    if modality not in plan.modalities:
        fail(f'Tu plan no cubre la modalidad {modality.lower()}. Consulta otro plan o modalidad')
    return plan

def overlaps(model, start, end):
    return and_(model.starts_at < end, model.ends_at > start)

def available(db, slot, patient_id=None, exclude_hold=None):
    if not slot.published or slot.starts_at <= now():
        return False
    if db.scalar(select(DoctorBlock.id).where(DoctorBlock.doctor_id == slot.doctor_id, overlaps(DoctorBlock, slot.starts_at, slot.ends_at)).limit(1)):
        return False
    appointment_filter = Appointment.doctor_id == slot.doctor_id
    hold_filter = Hold.doctor_id == slot.doctor_id
    if patient_id:
        appointment_filter = or_(appointment_filter, Appointment.patient_id == patient_id)
        hold_filter = or_(hold_filter, Hold.patient_id == patient_id)
    if db.scalar(select(Appointment.id).where(appointment_filter, Appointment.status == 'CONFIRMED', overlaps(Appointment, slot.starts_at, slot.ends_at)).limit(1)):
        return False
    q = select(Hold.id).where(hold_filter, Hold.status == 'ACTIVE', Hold.expires_at > now(), overlaps(Hold, slot.starts_at, slot.ends_at))
    if exclude_hold:
        q = q.where(Hold.id != exclude_hold)
    return db.scalar(q.limit(1)) is None

def create_hold(db, user, slot_id, modality='PRESENCIAL'):
    lock_patient(db, user.id)
    slot = db.get(Availability, slot_id)
    if not slot:
        fail('Horario no encontrado', 404)
    doctor = lock_doctor(db, slot.doctor_id)
    if modality not in doctor.modalities:
        fail(f'El médico no ofrece citas {modality.lower()}. Selecciona otro médico')
    if modality not in slot.modalities:
        fail(f'Este horario no está publicado para citas {modality.lower()}. Selecciona otro turno')
    if not available(db, slot, user.id):
        fail('El horario está ocupado, bloqueado o retenido. Selecciona otra fecha u horario')
    plan = active_plan(db, user.id, doctor.specialty_id, modality)
    h = Hold(patient_id=user.id, doctor_id=doctor.id, availability_id=slot.id, plan_id=plan.id, starts_at=slot.starts_at, ends_at=slot.ends_at, expires_at=now() + timedelta(minutes=HOLD_MINUTES), copay=plan.copay, modality=modality)
    db.add(h)
    db.flush()
    db.add(AuditEvent(actor_id=user.id, action='HOLD_CREATED', entity_id=h.id))
    return h

def owned_hold(db, user, hold_id):
    h = db.get(Hold, hold_id)
    if not h or h.patient_id != user.id:
        fail('Retención no encontrada', 404)
    return h

def valid_hold(db, user, h):
    if h.status != 'ACTIVE' or h.expires_at <= now():
        fail('La retención ha vencido o ya no está activa. Selecciona un nuevo horario')
    doctor = lock_doctor(db, h.doctor_id)
    if h.modality not in doctor.modalities:
        fail('El médico ya no ofrece esta modalidad')
    plan = active_plan(db, user.id, doctor.specialty_id, h.modality)
    if plan.id != h.plan_id or plan.copay != h.copay:
        fail('Tu plan ha cambiado. Libera la retención y selecciona nuevamente el horario')
    slot = db.get(Availability, h.availability_id)
    if not slot or h.modality not in slot.modalities or slot.starts_at != h.starts_at or slot.ends_at != h.ends_at or not available(db, slot, user.id, h.id):
        fail('El médico o el horario ya no están disponibles. Selecciona otro horario')

def notify(db, user_id, message):
    db.add(Notification(patient_id=user_id, message=message))

def confirm(db, user, hold_id):
    lock_patient(db, user.id)
    h = owned_hold(db, user, hold_id)
    existing = db.scalar(select(Appointment).where(Appointment.hold_id == h.id))
    if existing:
        return existing
    valid_hold(db, user, h)
    payment = db.scalar(select(Payment).where(Payment.hold_id == h.id, Payment.status == 'APPROVED'))
    if h.copay and not payment:
        fail('Debes completar y conciliar el copago antes de confirmar')
    a = Appointment(code='VS-' + uuid4().hex[:10].upper(), patient_id=user.id, doctor_id=h.doctor_id, hold_id=h.id, plan_id=h.plan_id, payment_id=payment.id if payment else None, starts_at=h.starts_at, ends_at=h.ends_at, copay=h.copay, modality=h.modality)
    h.status = 'CONFIRMED'
    db.add(a)
    db.flush()
    db.add(StatusHistory(appointment_id=a.id, status='CONFIRMED', author_id=user.id, reason='Confirmación del paciente'))
    if a.modality == 'VIRTUAL':
        db.add(VirtualConsultation(appointment_id=a.id, patient_id=a.patient_id, doctor_id=a.doctor_id))
    db.add(AuditEvent(actor_id=user.id, action='APPOINTMENT_CONFIRMED', entity_id=a.id))
    notify(db, user.id, f'Tu cita {a.code} ha sido confirmada. Consulta el comprobante en Mis citas.')
    return a

def cancel(db, user, appointment_id, data):
    lock_patient(db, user.id)
    a = db.scalar(select(Appointment).where(Appointment.id == appointment_id).with_for_update())
    if not a or a.patient_id != user.id:
        fail('Cita no encontrada o no pertenece al paciente', 404)
    if a.version != data.version:
        fail('La cita cambió. Actualiza la página antes de continuar')
    if a.status != 'CONFIRMED':
        fail('Solo puedes cancelar citas confirmadas; no canceladas o atendidas')
    if a.starts_at <= now() + timedelta(hours=CANCELLATION_HOURS):
        fail(f'La política requiere cancelar con más de {CANCELLATION_HOURS} horas de anticipación')
    lock_doctor(db, a.doctor_id)
    a.status = 'CANCELLED'
    a.version += 1
    a.cancelled_at = now()
    a.cancelled_by = user.id
    a.cancellation_reason = data.reason
    a.economic_review = a.payment_id is not None
    virtual = db.get(VirtualConsultation, a.id)
    if virtual:
        virtual.status = 'CANCELADA'
        virtual.updated_at = now()
    db.add(StatusHistory(appointment_id=a.id, status='CANCELLED', author_id=user.id, reason=data.reason))
    db.add(AuditEvent(actor_id=user.id, action='APPOINTMENT_CANCELLED', entity_id=a.id))
    notify(db, user.id, f'Tu cita {a.code} ha sido cancelada. El registro permanece en tu historial.' + (' El copago queda sujeto a gestión económica futura; no se realizó una devolución.' if a.economic_review else ''))
    return a
