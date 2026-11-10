"""Demo transitions share the request transaction with booking, history and notices."""
from fastapi import HTTPException
from sqlalchemy import select
from app.models.entities import Appointment, VirtualConsultation, StatusHistory, AuditEvent, now
from app.services import booking

TRANSITIONS = {
    'PROGRAMADA': {'SALA_DISPONIBLE'},
    'SALA_DISPONIBLE': {'PACIENTE_EN_ESPERA', 'MEDICO_EN_ESPERA', 'PACIENTE_AUSENTE', 'MEDICO_AUSENTE'},
    'PACIENTE_EN_ESPERA': {'MEDICO_EN_ESPERA', 'MEDICO_AUSENTE', 'EN_ATENCION'},
    'MEDICO_EN_ESPERA': {'PACIENTE_EN_ESPERA', 'EN_ATENCION', 'PACIENTE_AUSENTE'},
    'EN_ATENCION': {'FINALIZADA'},
}
for targets in TRANSITIONS.values():
    targets.add('ERROR_TECNICO')

EVENTS = {
    'ERROR_TECNICO': 'Incidencia técnica simulada',
    'SALA_DISPONIBLE': 'Sala simulada habilitada',
    'PACIENTE_EN_ESPERA': 'Paciente marcado presente',
    'MEDICO_EN_ESPERA': 'Médico marcado presente',
    'EN_ATENCION': 'Atención simulada iniciada',
    'FINALIZADA': 'Atención simulada finalizada',
    'PACIENTE_AUSENTE': 'Paciente ausente',
    'MEDICO_AUSENTE': 'Médico ausente',
}

def transition(db, user, appointment_id, target, demo_mode):
    booking.lock_patient(db, user.id)
    a = db.scalar(select(Appointment).where(
        Appointment.id == appointment_id, Appointment.patient_id == user.id,
        Appointment.modality == 'VIRTUAL').with_for_update())
    if not a:
        raise HTTPException(404, 'Teleconsulta no encontrada o no pertenece a tu cuenta')
    if not demo_mode:
        raise HTTPException(403, 'La simulación está deshabilitada fuera de DEMO_MODE; requiere atención clínica autorizada')
    vc = db.scalar(select(VirtualConsultation).where(
        VirtualConsultation.appointment_id == a.id).with_for_update())
    if a.status not in ('CONFIRMED', 'IN_PROGRESS') or not vc or target not in TRANSITIONS.get(vc.status, set()):
        raise HTTPException(409, 'Este estado no corresponde al siguiente paso de la simulación')
    if target == 'EN_ATENCION' and not (vc.patient_present_at and vc.doctor_present_at):
        raise HTTPException(409, 'Ambos participantes deben estar presentes')
    previous = vc.status
    timestamp = now()
    if target == 'PACIENTE_EN_ESPERA':
        if vc.patient_present_at:
            raise HTTPException(409, 'La presencia del paciente ya está registrada')
        vc.patient_present_at = timestamp
    if target == 'MEDICO_EN_ESPERA':
        if vc.doctor_present_at:
            raise HTTPException(409, 'La presencia del médico ya está registrada')
        vc.doctor_present_at = timestamp
    vc.status, vc.updated_at = target, timestamp
    new_status = {'EN_ATENCION': 'IN_PROGRESS', 'FINALIZADA': 'ATTENDED',
                  'PACIENTE_AUSENTE': 'PATIENT_ABSENT', 'MEDICO_AUSENTE': 'DOCTOR_ABSENT', 'ERROR_TECNICO': 'TECHNICAL_ERROR'}.get(target)
    if new_status:
        old_status = a.status
        a.status = new_status
        a.version += 1
        if target == 'FINALIZADA':
            a.completion_source = 'DEMO'
            a.simulated_completed_at = timestamp
            a.clinically_attended = False
        db.add(StatusHistory(appointment_id=a.id, status=new_status, author_id=user.id,
            reason=f'DEMOSTRACIÓN · Cita {a.code} · {old_status} → {new_status} · Simulador: {user.name} · No hubo atención médica real'))
        booking.notify(db, user.id, f'Cita {a.code}: {EVENTS[target]}. DEMOSTRACIÓN; no hubo atención médica real.')
    db.add(StatusHistory(appointment_id=a.id, status='VIRTUAL_' + target, author_id=user.id,
        reason=f'DEMOSTRACIÓN · Cita {a.code} · {previous} → {target} · Simulador: {user.name} · {EVENTS[target]}'))
    db.add(AuditEvent(actor_id=user.id, action='SIMULATED_TELECONSULT_' + target, entity_id=a.id))
    db.flush()
    return {'appointment_id': a.id, 'status': vc.status, 'appointment_status': a.status,
            'completion_source': a.completion_source, 'simulated_completed_at': a.simulated_completed_at,
            'clinically_attended': a.clinically_attended,
            'message': 'Estado demostrativo guardado. No hubo atención médica real.'}
