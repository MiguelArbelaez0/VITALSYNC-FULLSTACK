"""Transactional lifecycle for simulated virtual appointments.

The provider boundary intentionally carries no media connection. A real provider can
be added later without changing appointment lifecycle transitions.
"""
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select
from app.core.config import DEMO_MODE, TELECONSULT_ROOM_OPEN_MINUTES, TELECONSULT_WAIT_GRACE_MINUTES
from app.models.entities import Appointment, AuditEvent, StatusHistory, VirtualConsultation, now
from app.services import booking, appointment_lifecycle, attendance, notification_service
from app.services.consultation_provider import DemoTeleconsultationProvider

PROVIDER = DemoTeleconsultationProvider()

LEGACY_EVENTS = {
    'SALA_DISPONIBLE': 'OPEN_ROOM',
    'PACIENTE_EN_ESPERA': 'PATIENT_JOIN',
    'MEDICO_EN_ESPERA': 'DOCTOR_JOIN',
    'EN_ATENCION': 'START',
    'FINALIZADA': 'FINALIZE',
    'PACIENTE_AUSENTE': 'PATIENT_ABSENT',
    'MEDICO_AUSENTE': 'DOCTOR_ABSENT',
    'ERROR_TECNICO': 'TECHNICAL_ERROR',
}
DEMO_EVENTS = {'ADVANCE_DEMO_CLOCK','DOCTOR_JOIN','START','FINALIZE','PATIENT_ABSENT','DOCTOR_ABSENT','TECHNICAL_ERROR','RETRY'}


def display_status(vc):
    return attendance.display_status(vc)


def available_actions(appointment, vc, demo_mode=None):
    demo_mode = DEMO_MODE if demo_mode is None else demo_mode
    current = now()
    window_open = current >= appointment.starts_at - timedelta(minutes=TELECONSULT_ROOM_OPEN_MINUTES)
    if demo_mode and vc.demo_clock_advanced_at:
        window_open = True
    if appointment.status in ('ATTENDED','CANCELLED','PATIENT_ABSENT','DOCTOR_ABSENT'):
        return []
    if appointment.status == 'TECHNICAL_ERROR' or vc.status == 'ERROR_TECNICO':
        return ['RETRY'] if demo_mode else []
    if vc.status == 'PROGRAMADA':
        actions = ['ADVANCE_DEMO_CLOCK'] if demo_mode and not window_open else []
        if window_open:
            actions.append('OPEN_ROOM')
        if demo_mode:
            actions.append('TECHNICAL_ERROR')
        return actions
    if vc.status == 'SALA_DISPONIBLE' or vc.status == 'EN_ESPERA':
        actions = []
        if not vc.patient_present:
            actions.append('PATIENT_JOIN')
        if demo_mode and not vc.doctor_present:
            actions.append('DOCTOR_JOIN')
        grace_elapsed = current >= appointment.starts_at + timedelta(minutes=TELECONSULT_WAIT_GRACE_MINUTES)
        if demo_mode and (grace_elapsed or vc.demo_clock_advanced_at):
            if not vc.patient_present:
                actions.append('PATIENT_ABSENT')
            if not vc.doctor_present:
                actions.append('DOCTOR_ABSENT')
        if demo_mode and vc.patient_present and vc.doctor_present:
            actions.append('START')
        if demo_mode:
            actions.append('TECHNICAL_ERROR')
        return actions
    if vc.status == 'EN_ATENCION':
        return ['FINALIZE','TECHNICAL_ERROR'] if demo_mode else []
    return []


def state_dict(appointment, vc, demo_mode=None):
    demo_mode = DEMO_MODE if demo_mode is None else demo_mode
    return {
        'status': display_status(vc), 'lifecycle_status': vc.status,
        'patient_present': vc.patient_present, 'doctor_present': vc.doctor_present,
        'patient_joined_at': vc.patient_joined_at, 'doctor_joined_at': vc.doctor_joined_at,
        'room_opened_at': vc.room_opened_at, 'started_at': vc.started_at,
        'finalized_at': vc.finalized_at, 'demo_clock_advanced': bool(vc.demo_clock_advanced_at),
        'incident_reason': vc.incident_reason, 'incident_at': vc.incident_at,
        'incident_resolved_at': vc.incident_resolved_at,
        'available_actions': available_actions(appointment, vc, demo_mode),
        'room_open_minutes': TELECONSULT_ROOM_OPEN_MINUTES,
        'wait_grace_minutes': TELECONSULT_WAIT_GRACE_MINUTES,
        'demo_mode': demo_mode, 'provider': PROVIDER.name,
    }


def apply_event(db, user, appointment_id, event, reason=None, demo_mode=None, legacy_status=None):
    demo_mode = DEMO_MODE if demo_mode is None else demo_mode
    booking.lock_patient(db, user.id)
    appointment = db.scalar(select(Appointment).where(
        Appointment.id == appointment_id, Appointment.patient_id == user.id,
        Appointment.modality == 'VIRTUAL',
    ).with_for_update())
    if not appointment:
        raise HTTPException(404, 'Teleconsulta no encontrada o no pertenece a tu cuenta')
    vc = db.scalar(select(VirtualConsultation).where(VirtualConsultation.appointment_id == appointment_id).with_for_update())
    if not vc or vc.patient_id != user.id or vc.doctor_id != appointment.doctor_id:
        raise HTTPException(404, 'Teleconsulta no encontrada o no pertenece a tu cuenta')
    if legacy_status and not demo_mode:
        raise HTTPException(403, 'La simulación está deshabilitada fuera de DEMO_MODE; requiere atención clínica autorizada')
    if event in DEMO_EVENTS and not demo_mode:
        raise HTTPException(403, 'Esta acción simulada solo está disponible en el modo de demostración')
    if legacy_status == 'SALA_DISPONIBLE' and event == 'OPEN_ROOM' and demo_mode and not vc.demo_clock_advanced_at:
        # Backward-compatible demo transition: the legacy endpoint's explicit room-open request
        # advances only the virtual clock, never the reserved appointment timestamp.
        vc.demo_clock_advanced_at = now()
        db.add(AuditEvent(actor_id=user.id, action='SIMULATED_TELECONSULT_ADVANCE_DEMO_CLOCK', entity_id=appointment_id))
    if event not in available_actions(appointment, vc, demo_mode):
        raise HTTPException(409, 'La acción no está disponible para el estado o la hora actual de la cita')

    timestamp = now()
    if event == 'ADVANCE_DEMO_CLOCK':
        vc.demo_clock_advanced_at = timestamp
        message = 'Reloj demostrativo habilitado; la fecha reservada de la cita se conserva.'
    elif event == 'OPEN_ROOM':
        vc.status = 'SALA_DISPONIBLE'
        vc.room_opened_at = timestamp
        message = 'Sala simulada disponible.'
    elif event == 'PATIENT_JOIN':
        attendance.register_patient(vc, timestamp)
        message = 'Presencia del paciente registrada.'
    elif event == 'DOCTOR_JOIN':
        attendance.register_doctor(vc, timestamp)
        message = 'Ingreso médico ficticio registrado en modo demostración.'
    elif event == 'START':
        vc.status = 'EN_ATENCION'
        vc.started_at = timestamp
        appointment_lifecycle.start(appointment)
        message = 'Atención simulada iniciada. No acredita una consulta médica real.'
    elif event == 'FINALIZE':
        vc.status = 'FINALIZADA'
        vc.finalized_at = timestamp
        appointment_lifecycle.finalize(appointment, timestamp)
        message = 'Atención simulada finalizada correctamente. No hubo atención médica real.'
    elif event in ('PATIENT_ABSENT','DOCTOR_ABSENT'):
        absent = 'PACIENTE_AUSENTE' if event == 'PATIENT_ABSENT' else 'MEDICO_AUSENTE'
        absence_reason = reason or ('El paciente no ingresó dentro del plazo de espera.' if event == 'PATIENT_ABSENT' else 'El médico no ingresó dentro del plazo de espera; ausencia simulada.')
        appointment_lifecycle.mark_absent(appointment, 'PATIENT_ABSENT' if event == 'PATIENT_ABSENT' else 'DOCTOR_ABSENT', timestamp, absence_reason)
        vc.status = absent
        vc.incident_at = timestamp
        vc.incident_reason = absence_reason
        message = 'Se registró una ausencia simulada. La cita permanece en el historial.'
    elif event == 'TECHNICAL_ERROR':
        vc.resume_status = vc.status
        vc.resume_appointment_status = appointment.status
        vc.status = 'ERROR_TECNICO'
        vc.incident_at = timestamp
        vc.incident_reason = reason or 'Incidencia técnica simulada y recuperable.'
        appointment_lifecycle.mark_technical_issue(appointment, timestamp, vc.incident_reason)
        message = 'Incidencia técnica registrada; puedes reintentar la sala simulada.'
    else:  # RETRY
        vc.status = vc.resume_status or 'SALA_DISPONIBLE'
        appointment.status = vc.resume_appointment_status or 'CONFIRMED'
        vc.incident_resolved_at = timestamp
        vc.resume_status = None
        vc.resume_appointment_status = None
        appointment.version += 1
        message = 'La incidencia se resolvió y la sesión simulada quedó lista para continuar.'

    vc.updated_at = timestamp
    history_reason = f'DEMOSTRACIÓN · Cita {appointment.code} · {message}'
    db.add(AuditEvent(actor_id=user.id, action='SIMULATED_TELECONSULT_' + (legacy_status or event), entity_id=appointment_id))
    db.add(StatusHistory(appointment_id=appointment_id, status='VIRTUAL_' + vc.status, author_id=user.id, reason=history_reason))
    if event in {'START','FINALIZE','PATIENT_ABSENT','DOCTOR_ABSENT','TECHNICAL_ERROR','RETRY'}:
        db.add(StatusHistory(appointment_id=appointment_id, status=appointment.status, author_id=user.id, reason=history_reason))
    if event in {'FINALIZE','PATIENT_ABSENT','DOCTOR_ABSENT','TECHNICAL_ERROR','RETRY'}:
        notification_service.lifecycle_update(db, user.id, appointment.code, message)
    db.flush()
    state = state_dict(appointment, vc, demo_mode)
    return {'appointment_id': appointment_id, 'appointment_status': appointment.status, 'completion_source': appointment.completion_source, 'simulated_completed_at': appointment.simulated_completed_at, 'clinically_attended': appointment.clinically_attended, 'state': state, 'status': state['status'], 'message': message}
