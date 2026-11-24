"""Server-authorized academic LiveKit test appointments, isolated from coverage and billing."""
from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, text

from app.core.config import DEMO_MODE
from app.models.entities import (
    Appointment, AppointmentSnapshot, AuditEvent, DemoPatient, Doctor,
    DoctorAccount, Notification, StatusHistory, User, VirtualConsultation, now,
)
from app.services import livekit_consultations

ACTIVE = ('CONFIRMED', 'IN_PROGRESS', 'TECHNICAL_ERROR')
TEST_LABEL = 'Consulta académica de prueba'


def _require_demo_patient(db, user):
    if not DEMO_MODE or user.role != 'PATIENT' or not db.get(DemoPatient, user.id):
        raise HTTPException(403, 'Esta función solo está disponible para pacientes de demostración autorizados')
    if not livekit_consultations.enabled():
        raise HTTPException(503, 'La sala de video no está configurada en este entorno')


def doctors(db, user):
    _require_demo_patient(db, user)
    rows = db.execute(
        select(Doctor, User.name, User.id)
        .join(DoctorAccount, DoctorAccount.doctor_id == Doctor.id)
        .join(User, User.id == DoctorAccount.user_id)
        .where(Doctor.enabled, Doctor.is_demo_doctor, Doctor.modalities.contains(['VIRTUAL']), User.role == 'DOCTOR', User.status == 'ACTIVE')
        .order_by(Doctor.id)
    ).all()
    return [dict(id=d.id, name=d.name, account_name=name, specialty_id=d.specialty_id) for d, name, _ in rows]


def create(db, user, doctor_id: int):
    _require_demo_patient(db, user)
    # Serialize all test starts per doctor. This also makes rapid repeated requests idempotent.
    db.execute(text('SELECT pg_advisory_xact_lock(879221, :doctor_id)'), {'doctor_id': doctor_id})
    doctor = db.scalar(
        select(Doctor).join(DoctorAccount, DoctorAccount.doctor_id == Doctor.id)
        .join(User, User.id == DoctorAccount.user_id)
        .where(Doctor.id == doctor_id, Doctor.enabled, Doctor.is_demo_doctor,
               Doctor.modalities.contains(['VIRTUAL']), User.role == 'DOCTOR', User.status == 'ACTIVE')
    )
    if not doctor:
        raise HTTPException(404, 'Médico de demostración virtual no disponible')

    active = db.scalar(select(Appointment).where(Appointment.doctor_id == doctor.id, Appointment.status.in_(ACTIVE), Appointment.is_demo_test).with_for_update())
    if active:
        if active.patient_id == user.id:
            return active
        raise HTTPException(409, 'Este médico ya participa en otra sesión de prueba. Inténtalo cuando finalice.')

    start = now()
    end = start + timedelta(minutes=30)
    occupied = db.scalar(select(Appointment.id).where(
        Appointment.doctor_id == doctor.id,
        Appointment.status.in_(ACTIVE),
        Appointment.is_demo_test.is_(False),
        Appointment.starts_at < end,
        Appointment.ends_at > start,
    ).limit(1))
    if occupied:
        raise HTTPException(409, 'Este médico tiene una consulta ordinaria durante este intervalo. Prueba con otro médico.')
    patient_occupied = db.scalar(select(Appointment.id).where(
        Appointment.patient_id == user.id,
        Appointment.status.in_(ACTIVE),
        Appointment.starts_at < end,
        Appointment.ends_at > start,
    ).limit(1))
    if patient_occupied:
        raise HTTPException(409, 'Ya tienes una consulta activa que coincide con este intervalo. Finalízala antes de iniciar otra prueba.')

    appointment = Appointment(
        code='VS-DEMO-' + uuid4().hex[:10].upper(), patient_id=user.id,
        doctor_id=doctor.id, hold_id=None, plan_id=None, payment_id=None,
        starts_at=start, ends_at=end, copay=0, modality='VIRTUAL',
        status='CONFIRMED', is_demo_test=True,
    )
    db.add(appointment)
    db.flush()
    db.add(AppointmentSnapshot(appointment_id=appointment.id, terms={
        'plan': TEST_LABEL, 'doctor': doctor.name,
        'specialty': 'Sesión académica', 'copay': 0, 'origin': 'ACADEMIC_DEMO',
    }))
    db.add(VirtualConsultation(
        appointment_id=appointment.id, patient_id=user.id, doctor_id=doctor.id,
        status='PROGRAMADA', is_demo_test=True,
        livekit_room_name='vs-' + uuid4().hex,
    ))
    db.add(StatusHistory(appointment_id=appointment.id, status='CONFIRMED', author_id=user.id,
                         reason='Creación de consulta académica de prueba inmediata. Sin plan, cobertura ni cobro.'))
    db.add(AuditEvent(actor_id=user.id, action='DEMO_LIVEKIT_TEST_CREATED', entity_id=appointment.id))
    db.add(Notification(patient_id=user.id, message=f'Se creó la {TEST_LABEL.lower()} con {doctor.name}. No genera cobros ni modifica tu cobertura.'))
    return appointment
