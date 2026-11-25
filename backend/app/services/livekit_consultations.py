"""Authorization and metadata lifecycle for appointment-bound LiveKit calls."""
import asyncio
import re
from datetime import timedelta

from fastapi import HTTPException
from livekit import api
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import (
    DEMO_MODE, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_API_URL, LIVEKIT_ENABLED,
    LIVEKIT_PUBLIC_URL, LIVEKIT_TOKEN_TTL_SECONDS, LIVEKIT_MANAGED_ROOMS,
    TELECONSULT_WAIT_GRACE_MINUTES,
)
from app.models.entities import (
    Appointment, AuditEvent, DemoPatient, Doctor, DoctorAccount, LiveKitRoomEvent, Notification,
    StatusHistory, VirtualConsultation, now,
)
from app.services import appointment_lifecycle

TERMINAL_APPOINTMENTS = {'ATTENDED', 'CANCELLED', 'PATIENT_ABSENT', 'DOCTOR_ABSENT'}


def enabled():
    return LIVEKIT_ENABLED and bool(LIVEKIT_API_KEY and LIVEKIT_API_SECRET)


def ensure_room(name, max_participants=2):
    if not LIVEKIT_MANAGED_ROOMS:
        return

    async def create_if_missing():
        async with api.LiveKitAPI(LIVEKIT_API_URL, api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET) as client:
            existing = await client.room.list_rooms(api.ListRoomsRequest(names=[name]))
            if not existing.rooms:
                await client.room.create_room(api.CreateRoomRequest(
                    name=name, max_participants=max_participants, empty_timeout=120, departure_timeout=20))

    try:
        asyncio.run(asyncio.wait_for(create_if_missing(), timeout=8))
    except Exception:
        raise HTTPException(503, 'No se pudo abrir la sala. Vuelve a intentar en un momento.') from None


def _room_membership(db: Session, appointment_id: int, user, doctor_id: int | None = None, allow_terminal: bool = False):
    if not enabled():
        raise HTTPException(503, 'La sala de video no está configurada en este entorno')
    appointment = db.scalar(select(Appointment).where(Appointment.id == appointment_id).with_for_update())
    if not appointment or appointment.modality != 'VIRTUAL':
        raise HTTPException(404, 'Cita virtual no encontrada')
    vc = db.scalar(select(VirtualConsultation).where(
        VirtualConsultation.appointment_id == appointment_id,
    ).with_for_update())
    if not vc or vc.patient_id != appointment.patient_id or vc.doctor_id != appointment.doctor_id:
        raise HTTPException(404, 'Sala virtual no encontrada')
    if vc.is_demo_test or appointment.is_demo_test:
        if not (DEMO_MODE and vc.is_demo_test and appointment.is_demo_test):
            raise HTTPException(403, 'La consulta académica está deshabilitada fuera del modo demostración')
        demo_doctor = db.get(Doctor, appointment.doctor_id)
        if not demo_doctor or not demo_doctor.is_demo_doctor or not db.get(DemoPatient, appointment.patient_id):
            raise HTTPException(403, 'Esta consulta ya no está vinculada a cuentas de demostración autorizadas')
    if doctor_id is None:
        if user.role != 'PATIENT' or user.id != appointment.patient_id:
            raise HTTPException(404, 'Cita virtual no encontrada')
        role = 'PATIENT'
    else:
        linked_doctor = db.scalar(select(DoctorAccount.doctor_id).where(DoctorAccount.user_id == user.id))
        if user.role != 'DOCTOR' or linked_doctor != appointment.doctor_id or doctor_id != appointment.doctor_id:
            raise HTTPException(404, 'Cita virtual no encontrada')
        role = 'DOCTOR'
    terminal = appointment.status in TERMINAL_APPOINTMENTS or vc.status in {'FINALIZADA', 'CANCELADA', 'PACIENTE_AUSENTE', 'MEDICO_AUSENTE'}
    if terminal and not allow_terminal:
        raise HTTPException(409, 'La consulta terminó y ya no admite nuevos ingresos')
    if not terminal and appointment.status not in {'CONFIRMED', 'IN_PROGRESS', 'TECHNICAL_ERROR'}:
        raise HTTPException(409, 'El estado actual de la cita no permite ingresar a video')
    current = now()
    immediate_demo = bool(vc.is_demo_test and appointment.is_demo_test and DEMO_MODE)
    if not terminal and not immediate_demo and current > appointment.ends_at + timedelta(minutes=TELECONSULT_WAIT_GRACE_MINUTES):
        raise HTTPException(409, 'La ventana de ingreso a la cita ya terminó')
    return appointment, vc, role


def issue_token(db: Session, appointment_id: int, user, doctor_id: int | None = None):
    appointment, vc, role = _room_membership(db, appointment_id, user, doctor_id)
    ensure_room(vc.livekit_room_name)
    identity = f'user:{user.id}'
    grants = api.VideoGrants(
        room_join=True,
        room=vc.livekit_room_name,
        room_create=False,
        room_list=False,
        room_admin=False,
        room_record=False,
        ingress_admin=False,
        can_publish=True,
        can_subscribe=True,
        can_publish_data=False,
        can_update_own_metadata=False,
        can_publish_sources=['camera', 'microphone', 'screen_share', 'screen_share_audio'],
    )
    token = (
        api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name('Paciente' if role == 'PATIENT' else 'Médico')
        .with_ttl(timedelta(seconds=max(60, min(LIVEKIT_TOKEN_TTL_SECONDS, 900))))
        .with_grants(grants)
        .to_jwt()
    )
    return {
        'token': token,
        'server_url': LIVEKIT_PUBLIC_URL,
        'expires_in_seconds': max(60, min(LIVEKIT_TOKEN_TTL_SECONDS, 900)),
        'connection_state': vc.livekit_connection_state,
        'appointment_status': appointment.status,
    }


def process_webhook(db: Session, raw_body: bytes, auth_header: str | None, background=None):
    if not enabled() or not auth_header:
        raise HTTPException(401, 'Webhook no autorizado')
    try:
        verifier = api.TokenVerifier(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        event = api.WebhookReceiver(verifier).receive(raw_body.decode('utf-8'), auth_header)
    except Exception as exc:
        raise HTTPException(401, 'Firma de webhook inválida') from exc

    event_id = str(getattr(event, 'id', '') or '')
    event_type = str(getattr(event, 'event', '') or '')
    room = getattr(event, 'room', None)
    participant = getattr(event, 'participant', None)
    room_name = str(getattr(room, 'name', '') or '')
    identity = str(getattr(participant, 'identity', '') or '')
    if not event_id or not room_name or event_type not in {'participant_joined', 'participant_left'}:
        return {'accepted': True, 'processed': False}
    match = re.fullmatch(r'user:(\d+)', identity)
    if not match:
        return {'accepted': True, 'processed': False}
    user_id = int(match.group(1))
    if room_name.startswith('simulation-'):
        from app.models.entities import SimulationRoom

        practice = db.get(SimulationRoom, room_name.removeprefix('simulation-'))
        admitted = practice and practice.ended_at is None and practice.expires_at > now() and user_id in (practice.owner_id, practice.guest_id)
        if not admitted and event_type == 'participant_joined' and background is not None:
            background.add_task(close_room, room_name)
        return {'accepted': True, 'processed': False}
    vc = db.scalar(select(VirtualConsultation).where(
        VirtualConsultation.livekit_room_name == room_name,
    ).with_for_update())
    if not vc:
        return {'accepted': True, 'processed': False}
    appointment = db.scalar(select(Appointment).where(Appointment.id == vc.appointment_id).with_for_update())
    if not appointment or appointment.modality != 'VIRTUAL':
        return {'accepted': True, 'processed': False}
    doctor_user_id = db.scalar(select(DoctorAccount.user_id).where(DoctorAccount.doctor_id == vc.doctor_id))
    role = 'PATIENT' if user_id == vc.patient_id else 'DOCTOR' if user_id == doctor_user_id else None
    if not role:
        return {'accepted': True, 'processed': False}
    if db.scalar(select(LiveKitRoomEvent.id).where(LiveKitRoomEvent.event_id == event_id)):
        return {'accepted': True, 'processed': False, 'duplicate': True}

    inserted = db.execute(insert(LiveKitRoomEvent).values(
        event_id=event_id,
        appointment_id=appointment.id,
        participant_user_id=user_id,
        participant_role=role,
        event_type=event_type,
        created_at=now(),
    ).on_conflict_do_nothing(index_elements=['event_id']))
    if inserted.rowcount == 0:
        return {'accepted': True, 'processed': False, 'duplicate': True}

    # Webhooks can arrive late after the doctor has finalized the encounter.
    # Keep the event for idempotency/audit, but never let it reopen or regress
    # the consultation state or append a post-finalization lifecycle transition.
    if appointment.status in TERMINAL_APPOINTMENTS or vc.status in {'FINALIZADA', 'CANCELADA', 'PACIENTE_AUSENTE', 'MEDICO_AUSENTE'}:
        if LIVEKIT_MANAGED_ROOMS and event_type == 'participant_joined' and background is not None:
            background.add_task(close_room, room_name)
        db.flush()
        return {'accepted': True, 'processed': True, 'terminal': True, 'connection_state': 'DISCONNECTED'}

    timestamp = now()
    connected = event_type == 'participant_joined'
    if role == 'PATIENT':
        vc.livekit_patient_connected = connected
        if connected:
            vc.patient_present = True
            vc.patient_present_at = vc.patient_present_at or timestamp
            vc.patient_joined_at = vc.patient_joined_at or timestamp
    else:
        vc.livekit_doctor_connected = connected
        if connected:
            vc.doctor_present = True
            vc.doctor_present_at = vc.doctor_present_at or timestamp
            vc.doctor_joined_at = vc.doctor_joined_at or timestamp

    if connected and vc.status == 'PROGRAMADA':
        vc.status = 'SALA_DISPONIBLE'
        vc.room_opened_at = vc.room_opened_at or timestamp
    if connected and not (vc.livekit_patient_connected and vc.livekit_doctor_connected):
        if appointment.status == 'CONFIRMED':
            vc.status = 'EN_ESPERA'
    if appointment.status not in TERMINAL_APPOINTMENTS and vc.livekit_patient_connected and vc.livekit_doctor_connected:
        vc.livekit_connection_state = 'CONNECTED'
        if appointment.status == 'CONFIRMED':
            appointment_lifecycle.start(appointment)
            vc.status = 'EN_ATENCION'
            vc.started_at = vc.started_at or timestamp
            db.add(StatusHistory(appointment_id=appointment.id, status='IN_PROGRESS', author_id=user_id,
                                 reason='LiveKit: paciente y médico conectados a la consulta virtual.'))
        elif appointment.status == 'IN_PROGRESS':
            # Restoring both media connections resumes the same encounter;
            # it must not regress the persisted consultation phase.
            vc.status = 'EN_ATENCION'
    elif connected:
        vc.livekit_connection_state = 'WAITING'
    else:
        vc.livekit_connection_state = 'RECONNECTING' if appointment.status == 'IN_PROGRESS' else 'DISCONNECTED'

    vc.updated_at = timestamp
    vc.livekit_last_event_at = timestamp
    verb = 'conectado' if connected else 'desconectado'
    db.add(AuditEvent(actor_id=user_id, action=f'LIVEKIT_{role}_{"JOINED" if connected else "LEFT"}', entity_id=appointment.id))
    db.add(StatusHistory(appointment_id=appointment.id, status=f'LIVEKIT_{role}_{"CONNECTED" if connected else "DISCONNECTED"}',
                         author_id=user_id, reason=f'LiveKit: {"Paciente" if role == "PATIENT" else "Médico"} {verb}.'))
    db.flush()
    return {'accepted': True, 'processed': True, 'connection_state': vc.livekit_connection_state}


def finalize(db: Session, appointment_id: int, user, doctor_id: int):
    appointment, vc, role = _room_membership(db, appointment_id, user, doctor_id, allow_terminal=True)
    if role != 'DOCTOR':
        raise HTTPException(403, 'Solo el médico asignado puede finalizar la consulta')
    if appointment.status == 'ATTENDED' and vc.status == 'FINALIZADA':
        return {'appointment_id': appointment.id, 'status': 'FINALIZADA', 'appointment_status': 'ATTENDED',
                'idempotent': True, 'room_name': vc.livekit_room_name, 'started_at': vc.started_at,
                'finalized_at': vc.finalized_at}
    if appointment.status != 'IN_PROGRESS' or vc.status != 'EN_ATENCION':
        raise HTTPException(409, 'La consulta solo se puede finalizar después de que ambos participantes se conecten')

    timestamp = now()
    previous = appointment.status
    appointment.status = 'ATTENDED'
    appointment.attended_at = timestamp
    appointment.completion_source = None
    appointment.simulated_completed_at = None
    appointment.clinically_attended = False
    appointment.version += 1
    vc.status = 'FINALIZADA'
    vc.finalized_at = timestamp
    vc.livekit_patient_connected = False
    vc.livekit_doctor_connected = False
    vc.livekit_connection_state = 'DISCONNECTED'
    vc.livekit_last_event_at = timestamp
    vc.updated_at = timestamp
    db.add(StatusHistory(appointment_id=appointment.id, status='ATTENDED', author_id=user.id,
                         reason=f'Consulta virtual LiveKit finalizada formalmente por el médico ({previous} → ATTENDED).'))
    db.add(AuditEvent(actor_id=user.id, action='LIVEKIT_CONSULTATION_FINALIZED', entity_id=appointment.id))
    db.add(Notification(patient_id=appointment.patient_id,
                        message=f'La consulta virtual de la cita {appointment.code} fue finalizada por el médico y quedó en tu historial.'))
    db.flush()
    return {'appointment_id': appointment.id, 'status': 'FINALIZADA', 'appointment_status': 'ATTENDED',
            'idempotent': False, 'room_name': vc.livekit_room_name, 'started_at': vc.started_at,
            'finalized_at': vc.finalized_at}


def close_room(room_name: str):
    """Close the finalized room after commit, retrying transient LiveKit errors."""
    async def _close():
        for attempt in range(3):
            client = api.LiveKitAPI(LIVEKIT_API_URL, api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET)
            try:
                await client.room.delete_room(api.DeleteRoomRequest(room=room_name))
                return True
            except Exception:
                if attempt == 2:
                    return False
                await asyncio.sleep(0.2 * (attempt + 1))
            finally:
                await client.aclose()
        return False
    try:
        return asyncio.run(_close())
    except Exception:
        # PostgreSQL finalization remains authoritative and blocks future tokens.
        return False
