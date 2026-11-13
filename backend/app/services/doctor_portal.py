"""Read projections and transactional medical cancellation, scoped to a professional."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select
from app.models.entities import Appointment, Specialty, User, StatusHistory, AuditEvent, VirtualConsultation, now
from app.services import booking

BOGOTA = ZoneInfo('America/Bogota')
ACTIVE = ('CONFIRMED', 'IN_PROGRESS', 'TECHNICAL_ERROR')


def day_bounds(day):
    start = datetime.combine(day, time.min, tzinfo=BOGOTA)
    return start, start + timedelta(days=1)


def profile(db, doctor):
    return dict(id=doctor.id, name=doctor.name, specialty=db.get(Specialty, doctor.specialty_id).name,
                bio=doctor.bio, modalities=doctor.modalities, editable_fields=['bio'],
                institutional_fields=['name', 'specialty', 'modalities'])


def owned(db, doctor, appointment_id, lock=False):
    q = select(Appointment).where(Appointment.id == appointment_id, Appointment.doctor_id == doctor.id)
    a = db.scalar(q.with_for_update().execution_options(populate_existing=True) if lock else q)
    if not a:
        raise HTTPException(404, 'Cita no encontrada o no asignada a tu perfil profesional')
    return a


def appointments_query(doctor):
    return select(Appointment, User.name).join(User, User.id == Appointment.patient_id).where(Appointment.doctor_id == doctor.id)


def appointment_dict(db, doctor, a, patient_name=None):
    # Deliberate allowlist: no payments, phone, identity document or data from other professionals.
    return dict(id=a.id, code=a.code, patient_id=a.patient_id,
                patient=patient_name if patient_name is not None else db.get(User, a.patient_id).name,
                doctor=doctor.name, specialty=db.get(Specialty, doctor.specialty_id).name,
                starts_at=a.starts_at, ends_at=a.ends_at,
                duration_minutes=int((a.ends_at-a.starts_at).total_seconds()/60),
                modality=a.modality, status=a.status, version=a.version,
                completion_source=a.completion_source, simulated_completed_at=a.simulated_completed_at,
                clinically_attended=a.clinically_attended, cancelled_at=a.cancelled_at,
                cancellation_reason=a.cancellation_reason)


def history(db, a):
    return [dict(status=h.status, reason=h.reason, created_at=h.created_at) for h in db.scalars(
        select(StatusHistory).where(StatusHistory.appointment_id == a.id).order_by(StatusHistory.id))]


def cancel(db, doctor, user, appointment_id, data, administrative=False):
    candidate = owned(db, doctor, appointment_id)
    # Same lock order as patient bookings/lifecycle: patient, appointment, professional.
    booking.lock_patient(db, candidate.patient_id)
    a = owned(db, doctor, appointment_id, lock=True)
    if a.version != data.version:
        raise HTTPException(409, 'La cita cambió. Actualiza antes de cancelar')
    if a.status != 'CONFIRMED' or a.starts_at <= now():
        raise HTTPException(409, 'Solo se pueden cancelar citas confirmadas que todavía no hayan comenzado')
    booking.lock_doctor(db, doctor.id)
    previous = a.status
    a.status = 'CANCELLED'
    a.version += 1
    a.cancelled_at = now()
    a.cancelled_by = user.id
    a.cancellation_reason = data.reason
    a.economic_review = a.payment_id is not None
    vc = db.scalar(select(VirtualConsultation).where(VirtualConsultation.appointment_id == a.id).with_for_update())
    if vc:
        vc.status = 'CANCELADA'
        vc.updated_at = a.cancelled_at
    db.add(StatusHistory(appointment_id=a.id, status=a.status, author_id=user.id,
                         reason=f'Cancelación {"administrativa" if administrative else "médica"} · {previous} → {a.status} · {data.reason}'))
    db.add(AuditEvent(actor_id=user.id, action='ADMIN_APPOINTMENT_CANCELLED' if administrative else 'DOCTOR_APPOINTMENT_CANCELLED', entity_id=a.id))
    booking.notify(db, a.patient_id, f'El médico {doctor.name} canceló tu cita {a.code}. Motivo: {data.reason}. Contacta a VITALSYNC para gestionar una nueva reserva.' +
                   (' El copago queda pendiente de gestión económica; no se realizó una devolución.' if a.economic_review else ''))
    db.flush()
    return dict(id=a.id, status=a.status, version=a.version, cancelled_at=a.cancelled_at,
                previous_status=previous, cancellation_reason=a.cancellation_reason,
                rescheduling_status='CONTACT_SUPPORT')
