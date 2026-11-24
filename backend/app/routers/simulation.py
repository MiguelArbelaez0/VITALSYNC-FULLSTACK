"""Authenticated practice rooms with no clinical or billing records."""
from datetime import timedelta
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from livekit import api
from pydantic import Field
from sqlalchemy import select

from app.core.config import DEMO_MODE
from app.core.security import authenticated_user, digest, doctor_for_user
from app.db.session import get_db
from app.models.entities import DemoPatient, Patient, SimulationAttempt, SimulationPatientAccess, SimulationRoom, User, now
from app.routers.admin import require
from app.schemas.admin import Reason
from app.services.admin_portal import audit
from app.schemas.requests import Input
from app.services import livekit_consultations as livekit

router = APIRouter(prefix='/api/simulation', tags=['simulation'])
admin_router = APIRouter(prefix='/api/admin', tags=['simulation'])


@admin_router.post('/patients/{id}/simulation-access')
def authorize_patient(id: int, data: Reason, admin=Depends(require('accounts'), scope='function'), db=Depends(get_db, scope='function')):
    if not DEMO_MODE:
        raise HTTPException(403, 'La autorización académica solo está disponible en modo demo')
    user = db.scalar(select(User).where(User.id == id).with_for_update())
    if not user or user.role != 'PATIENT' or user.status != 'ACTIVE' or not db.get(Patient, id):
        raise HTTPException(404, 'Paciente activo no encontrado')
    if not db.get(SimulationPatientAccess, id):
        db.add(SimulationPatientAccess(patient_id=id))
        audit(db, admin, 'SIMULATION_PATIENT_AUTHORIZED', 'patient', id, data.reason)
    return {'authorized': True}


def participant(user=Depends(authenticated_user, scope='function'), db=Depends(get_db, scope='function')):
    if DEMO_MODE:
        if user.role == 'PATIENT' and (db.get(DemoPatient, user.id) or db.get(SimulationPatientAccess, user.id)):
            return user
        if user.role == 'DOCTOR' and doctor_for_user(db, user).is_demo_doctor:
            return user
    raise HTTPException(403, 'La sala de simulación requiere una cuenta académica autorizada')


def active(room):
    return room and room.ended_at is None and room.expires_at > now()


def room_name(room):
    return 'simulation-' + room.id


class Create(Input):
    shared: bool = False


class Join(Input):
    invitation: str = Field(min_length=1, max_length=128)


@router.get('/access')
def access(user=Depends(participant, scope='function')):
    return {'available': livekit.enabled()}


@router.post('/rooms', status_code=201)
def create(data: Create, user=Depends(participant, scope='function'), db=Depends(get_db, scope='function')):
    if not livekit.enabled():
        raise HTTPException(503, 'LiveKit no está disponible')
    # Serialize the count and creation for this owner.
    db.execute(select(User.id).where(User.id == user.id).with_for_update())
    existing = db.scalar(select(SimulationRoom.id).where(
        SimulationRoom.owner_id == user.id, SimulationRoom.ended_at.is_(None),
        SimulationRoom.expires_at > now()).limit(1))
    if existing:
        raise HTTPException(409, 'Ya tienes una simulación activa. Reanúdala o espera a que expire.')
    invitation = secrets.token_urlsafe(24) if data.shared else None
    room = SimulationRoom(id=secrets.token_hex(16), owner_id=user.id,
        invite_hash=digest(invitation) if invitation else None, expires_at=now() + timedelta(minutes=30))
    db.add(room)
    return {'id': room.id, 'invitation': invitation, 'owner': True, 'expires_at': room.expires_at}


@router.get('/rooms')
def rooms(user=Depends(participant, scope='function'), db=Depends(get_db, scope='function')):
    available = db.scalars(select(SimulationRoom).where(
        (SimulationRoom.owner_id == user.id) | (SimulationRoom.guest_id == user.id),
        SimulationRoom.ended_at.is_(None), SimulationRoom.expires_at > now()
    ).order_by(SimulationRoom.expires_at.desc()))
    return [{'id': room.id, 'owner': room.owner_id == user.id, 'expires_at': room.expires_at} for room in available]


@router.post('/join')
def join(data: Join, user=Depends(participant, scope='function'), db=Depends(get_db, scope='function')):
    from fastapi.responses import JSONResponse

    db.execute(select(User.id).where(User.id == user.id).with_for_update())
    timestamp = now()
    limit = db.get(SimulationAttempt, user.id)
    if not limit:
        limit = SimulationAttempt(user_id=user.id, window_start=timestamp, attempts=0)
        db.add(limit)
    elif timestamp - limit.window_start >= timedelta(minutes=5):
        limit.window_start, limit.attempts = timestamp, 0
    if limit.attempts >= 8:
        return JSONResponse(status_code=429, content={'detail': 'Intenta de nuevo en cinco minutos'})
    limit.attempts += 1
    room = db.scalar(select(SimulationRoom).where(SimulationRoom.invite_hash == digest(data.invitation)).with_for_update())
    if not active(room) or (room.guest_id is not None and room.guest_id != user.id and room.owner_id != user.id):
        return JSONResponse(status_code=404, content={'detail': 'Invitación inválida, vencida o ya utilizada'})
    if room.owner_id != user.id:
        room.guest_id = user.id
    return {'id': room.id, 'owner': room.owner_id == user.id, 'expires_at': room.expires_at}


@router.post('/rooms/{id}/token')
def token(id: str, user=Depends(participant, scope='function'), db=Depends(get_db, scope='function')):
    room = db.scalar(select(SimulationRoom).where(SimulationRoom.id == id).with_for_update())
    if not room or user.id not in (room.owner_id, room.guest_id):
        raise HTTPException(404, 'Sala no disponible')
    if not active(room):
        raise HTTPException(409, 'La simulación terminó o expiró')
    if not livekit.enabled():
        raise HTTPException(503, 'LiveKit no está disponible')
    ttl = min(45, max(1, int((room.expires_at - now()).total_seconds())))
    livekit.ensure_room(room_name(room), max_participants=2 if room.invite_hash else 1)
    grant = api.VideoGrants(room_join=True, room=room_name(room), can_publish=True,
        can_subscribe=True, can_publish_data=False, can_update_own_metadata=False,
        can_publish_sources=['camera', 'microphone', 'screen_share', 'screen_share_audio'])
    jwt = (api.AccessToken(livekit.LIVEKIT_API_KEY, livekit.LIVEKIT_API_SECRET)
        .with_identity(f'user:{user.id}').with_name(user.name)
        .with_ttl(timedelta(seconds=ttl)).with_grants(grant).to_jwt())
    return {'token': jwt, 'server_url': livekit.LIVEKIT_PUBLIC_URL}


@router.get('/rooms/{id}')
def status(id: str, user=Depends(participant, scope='function'), db=Depends(get_db, scope='function')):
    room = db.get(SimulationRoom, id)
    if not room or user.id not in (room.owner_id, room.guest_id):
        raise HTTPException(404, 'Sala no disponible')
    return {'active': bool(active(room))}


@router.post('/rooms/{id}/end')
def end(id: str, background: BackgroundTasks, user=Depends(participant, scope='function'), db=Depends(get_db, scope='function')):
    room = db.scalar(select(SimulationRoom).where(SimulationRoom.id == id).with_for_update())
    if not room or room.owner_id != user.id:
        raise HTTPException(404, 'Sala no disponible para finalizar')
    if room.ended_at is None:
        room.ended_at = now()
    background.add_task(livekit.close_room, room_name(room))
    return {'ended': True}
