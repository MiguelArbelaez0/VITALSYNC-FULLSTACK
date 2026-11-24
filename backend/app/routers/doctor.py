"""Medical portal. Every professional id comes from the authenticated session."""
from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks
from pydantic import Field
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from app.core.security import authenticated_user, current_doctor, doctor_for_user, passwords, digest
from app.core.config import DEMO_MODE
from app.db.session import get_db
from app.models.entities import Appointment, User, Availability, DoctorBlock, VirtualConsultation, AuditEvent, DoctorCredentialState, SessionToken, now
from app.schemas.requests import Input, Cancel, TeleconsultationStatus, DoctorPasswordChange
from app.services import doctor_portal as service, teleconsultation, clinical_history, livekit_consultations

router = APIRouter(prefix='/api/doctor', tags=['doctor'])


class DoctorProfileUpdate(Input):
    bio: str = Field(min_length=20, max_length=2000)


@router.get('/me')
def me(doctor=Depends(current_doctor, scope='function'), db: Session = Depends(get_db, scope='function')):
    return service.profile(db, doctor)


@router.patch('/me')
def update_me(data: DoctorProfileUpdate, doctor=Depends(current_doctor, scope='function'), user=Depends(authenticated_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    doctor.bio = data.bio
    db.add(AuditEvent(actor_id=user.id, action='DOCTOR_BIO_UPDATED', entity_id=doctor.id))
    return service.profile(db, doctor)


@router.get('/dashboard')
def dashboard(doctor=Depends(current_doctor, scope='function'), db: Session = Depends(get_db, scope='function')):
    today = now().astimezone(service.BOGOTA).date()
    start, end = service.day_bounds(today)
    rows = db.execute(service.appointments_query(doctor).where(Appointment.starts_at >= start, Appointment.starts_at < end).order_by(Appointment.starts_at)).all()
    agenda = [service.appointment_dict(db, doctor, a, name) for a, name in rows]
    next_row = db.execute(service.appointments_query(doctor).where(Appointment.status.in_(service.ACTIVE), Appointment.ends_at > now()).order_by(Appointment.starts_at).limit(1)).first()
    return dict(doctor=service.profile(db, doctor), date=today, timezone='America/Bogota',
                metrics=dict(total=len(rows), presencial=sum(a.modality=='PRESENCIAL' for a, _ in rows),
                             virtual=sum(a.modality=='VIRTUAL' for a, _ in rows),
                             pending=sum(a.status in service.ACTIVE for a, _ in rows),
                             completed=sum(a.status=='ATTENDED' for a, _ in rows)),
                next_appointment=service.appointment_dict(db, doctor, *next_row) if next_row else None, agenda=agenda)


@router.get('/appointments')
def appointments(day: date | None = None, modality: Literal['PRESENCIAL','VIRTUAL'] | None = None,
                 status: Literal['CONFIRMED','IN_PROGRESS','ATTENDED','CANCELLED','PATIENT_ABSENT','DOCTOR_ABSENT','TECHNICAL_ERROR'] | None = None,
                 view: Literal['all','upcoming','history','cancelled'] = 'all',
                 doctor=Depends(current_doctor, scope='function'), db: Session = Depends(get_db, scope='function')):
    q = service.appointments_query(doctor)
    if day:
        start, end = service.day_bounds(day)
        q = q.where(Appointment.starts_at >= start, Appointment.starts_at < end)
    if modality:
        q = q.where(Appointment.modality == modality)
    if status:
        q = q.where(Appointment.status == status)
    if view == 'upcoming':
        q = q.where(Appointment.status.in_(service.ACTIVE), Appointment.ends_at > now())
    elif view == 'history':
        q = q.where(Appointment.status.notin_(service.ACTIVE))
    elif view == 'cancelled':
        q = q.where(Appointment.status == 'CANCELLED')
    return [service.appointment_dict(db, doctor, a, name) for a, name in db.execute(q.order_by(Appointment.starts_at).limit(500))]


@router.get('/appointments/{appointment_id}')
def detail(appointment_id: int, doctor=Depends(current_doctor, scope='function'), db: Session = Depends(get_db, scope='function')):
    a = service.owned(db, doctor, appointment_id)
    return {**service.appointment_dict(db, doctor, a), 'history': service.history(db, a)}


@router.post('/appointments/{appointment_id}/cancel')
def cancel(appointment_id: int, data: Cancel, doctor=Depends(current_doctor, scope='function'), user=Depends(authenticated_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    return service.cancel(db, doctor, user, appointment_id, data)


@router.get('/patients')
def patients(search: str = Query('', max_length=120), doctor=Depends(current_doctor, scope='function'), db: Session = Depends(get_db, scope='function')):
    assigned = select(Appointment.patient_id).where(Appointment.doctor_id == doctor.id)
    users = db.scalars(select(User).where(User.id.in_(assigned), User.name.icontains(search, autoescape=True)).order_by(User.name).limit(200)).all()
    return [dict(id=u.id, name=u.name) for u in users]


@router.get('/patients/{patient_id}')
def patient_detail(patient_id: int, doctor=Depends(current_doctor, scope='function'), db: Session = Depends(get_db, scope='function')):
    rows = db.execute(service.appointments_query(doctor).where(Appointment.patient_id == patient_id).order_by(Appointment.starts_at.desc()).limit(500)).all()
    if not rows:
        raise HTTPException(404, 'Paciente no asignado a tu agenda')
    return dict(id=patient_id, name=rows[0][1], clinical_history_available=clinical_history.available(db,doctor.id,patient_id), appointments=[service.appointment_dict(db, doctor, a, name) for a, name in rows])


@router.get('/availability')
def availability(day: date | None = None, doctor=Depends(current_doctor, scope='function'), db: Session = Depends(get_db, scope='function')):
    selected = day or now().astimezone(service.BOGOTA).date()
    start, end = service.day_bounds(selected)
    slots = db.scalars(select(Availability).where(Availability.doctor_id == doctor.id, Availability.starts_at >= start, Availability.starts_at < end).order_by(Availability.starts_at)).all()
    from app.models.entities import BlockRelease
    from sqlalchemy import select as sql_select
    blocks = db.scalars(select(DoctorBlock).where(DoctorBlock.doctor_id == doctor.id, DoctorBlock.starts_at < end, DoctorBlock.ends_at > start, ~DoctorBlock.id.in_(sql_select(BlockRelease.block_id))).order_by(DoctorBlock.starts_at)).all()
    return dict(date=selected, read_only=True,
                slots=[dict(id=s.id, starts_at=s.starts_at, ends_at=s.ends_at, modalities=s.modalities, published=s.published) for s in slots],
                blocks=[dict(starts_at=b.starts_at, ends_at=b.ends_at, reason=b.reason) for b in blocks])


@router.get('/appointments/{appointment_id}/teleconsult')
def room(appointment_id: int, doctor=Depends(current_doctor, scope='function'), db: Session = Depends(get_db, scope='function')):
    a = service.owned(db, doctor, appointment_id)
    vc = db.get(VirtualConsultation, a.id)
    if a.modality != 'VIRTUAL' or not vc or vc.doctor_id != doctor.id or vc.patient_id != a.patient_id:
        raise HTTPException(404, 'Sala virtual no encontrada')
    demo = DEMO_MODE and teleconsultation.DEMO_MODE and not livekit_consultations.enabled()
    state = teleconsultation.state_dict(a, vc, demo)
    if not demo:
        state['available_actions'] = []
    return {**service.appointment_dict(db, doctor, a), 'virtual_status': teleconsultation.display_status(vc),
            'virtual_state': state, 'demo_mode': demo, 'livekit_enabled': livekit_consultations.enabled(),
            'livekit_connection_state': vc.livekit_connection_state, 'history': service.history(db, a)}


@router.post('/appointments/{appointment_id}/livekit-token')
def doctor_livekit_token(appointment_id: int, doctor=Depends(current_doctor, scope='function'), user=Depends(authenticated_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    return livekit_consultations.issue_token(db, appointment_id, user, doctor.id)


@router.post('/appointments/{appointment_id}/livekit-finalize')
def finalize_livekit(appointment_id: int, background_tasks: BackgroundTasks, doctor=Depends(current_doctor, scope='function'), user=Depends(authenticated_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    result = livekit_consultations.finalize(db, appointment_id, user, doctor.id)
    # Repeated idempotent requests also retry room closure if a previous
    # LiveKit API call failed after PostgreSQL had already committed.
    background_tasks.add_task(livekit_consultations.close_room, result['room_name'])
    return {key: value for key, value in result.items() if key != 'room_name'}


@router.post('/appointments/{appointment_id}/teleconsult/events')
def transition(appointment_id: int, data: TeleconsultationStatus, doctor=Depends(current_doctor, scope='function'), user=Depends(authenticated_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    if livekit_consultations.enabled():
        raise HTTPException(409, 'Los cambios simulados están deshabilitados mientras la sala LiveKit está activa')
    if not data.event:
        raise HTTPException(422, 'Indica un evento de sala virtual')
    return teleconsultation.apply_event(db, user, appointment_id, data.event, data.reason,
                                        demo_mode=DEMO_MODE and teleconsultation.DEMO_MODE, doctor_id=doctor.id)


@router.get('/patients/{patient_id}/clinical-history')
def clinical_record(patient_id: int, doctor=Depends(current_doctor,scope='function'), user=Depends(authenticated_user,scope='function'), db: Session=Depends(get_db,scope='function')):
    return clinical_history.read_history(db,doctor,user,patient_id)


@router.get('/patients/{patient_id}/clinical-history/encounters/{encounter_id}')
def clinical_visit(patient_id: int, encounter_id: int, doctor=Depends(current_doctor,scope='function'), user=Depends(authenticated_user,scope='function'), db: Session=Depends(get_db,scope='function')):
    return clinical_history.read_encounter(db,doctor,user,patient_id,encounter_id)


@router.post('/password')
def change_password(data: DoctorPasswordChange, request: Request, user=Depends(authenticated_user,scope='function'), db: Session=Depends(get_db,scope='function')):
    raise HTTPException(403, 'El restablecimiento de credenciales médicas se solicita a administración; no está disponible desde el portal.')
