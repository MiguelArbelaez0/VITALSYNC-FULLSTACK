"""Google ID tokens are exchanged for the same first-party session as passwords."""
import secrets
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from pydantic import Field, ValidationError
from sqlalchemy import select, func, delete
from sqlalchemy.orm import Session

from app.core.config import GOOGLE_CLIENT_ID, COOKIE_SECURE, ALLOWED_ORIGINS
from app.core.security import authenticated_user, passwords, digest, create_session, doctor_for_user
from app.db.session import get_db
from app.models.entities import GoogleChallenge, GoogleIdentity, User, Patient, AuditEvent, SessionToken, now
from app.schemas.requests import Input, Register
from app.services import booking

router = APIRouter(prefix='/api/auth/google', tags=['authentication'])
COOKIE = 'vitalsync_google_flow'

class ChallengeInput(Input):
    purpose: Literal['LOGIN', 'LINK'] = 'LOGIN'
    current_password: str | None = Field(default=None, max_length=128)

class CredentialInput(Input):
    challenge: str = Field(min_length=32, max_length=128)
    credential: str = Field(min_length=20, max_length=16000)

class RegistrationInput(Input):
    challenge: str = Field(min_length=32, max_length=128)
    document_number: str
    phone: str
    privacy_accepted: Literal[True]

class RevokeInput(Input):
    current_password: str = Field(min_length=8, max_length=128)
    reason: str = Field(min_length=10, max_length=300)

def browser(request):
    if request.headers.get('origin') not in ALLOWED_ORIGINS:
        raise HTTPException(403, 'Origen no autorizado')

def reauthenticate(user, password):
    if not password or not passwords.verify(password, user.password_hash):
        raise HTTPException(403, 'Confirma tu contraseña actual para continuar')

def account(db, user):
    if not user or user.status != 'ACTIVE' or user.role != 'PATIENT':
        raise HTTPException(403, 'Google está disponible únicamente para pacientes. Los médicos y administradores deben usar su correo asignado y contraseña.')
    if not db.get(Patient, user.id):
        raise HTTPException(403, 'El perfil de paciente no está disponible')

def result(user):
    return {'id': user.id, 'role': user.role, 'redirect_to': '/portal'}

def verify_credential(credential, nonce):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(503, 'Google no está configurado en este entorno')
    try:
        claims = id_token.verify_oauth2_token(credential, GoogleRequest(), GOOGLE_CLIENT_ID)
        if (claims.get('iss') not in {'accounts.google.com', 'https://accounts.google.com'}
            or claims.get('aud') != GOOGLE_CLIENT_ID
            or claims.get('email_verified') is not True
            or not isinstance(claims.get('sub'), str) or not 1 <= len(claims['sub']) <= 255
            or not isinstance(claims.get('email'), str) or len(claims['email']) > 254
            or not secrets.compare_digest(str(claims.get('nonce', '')), nonce)
            or float(claims.get('exp', 0)) <= now().timestamp()):
            raise ValueError('invalid claims')
        return claims
    except Exception as exc:
        # Never log/echo tokens or provider exception text.
        raise HTTPException(401, 'No se pudo verificar tu identidad con Google. Intenta de nuevo.') from None

def challenge_for(db, request, token):
    browser(request)
    if not secrets.compare_digest(request.cookies.get(COOKIE, ''), token):
        raise HTTPException(403, 'La verificación del navegador no es válida. Inicia de nuevo.')
    row = db.scalar(select(GoogleChallenge).where(GoogleChallenge.token_hash == digest(token)).with_for_update())
    if not row or row.consumed or row.expires_at <= now():
        raise HTTPException(409, 'La solicitud venció o ya fue utilizada. Inicia de nuevo.')
    return row

@router.post('/challenge')
def challenge(data: ChallengeInput, request: Request, response: Response, db: Session = Depends(get_db, scope='function')):
    browser(request)
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(503, 'Google no está configurado en este entorno')
    user = None
    session_hash = None
    if data.purpose == 'LINK':
        user = authenticated_user(request, db)
        account(db, user)
        reauthenticate(user, data.current_password)
        session_hash = digest(request.cookies.get('vitalsync_session', ''))
    # Keep only short-lived metadata, not a Google token.
    db.execute(delete(GoogleChallenge).where(GoogleChallenge.expires_at < now()))
    token = secrets.token_urlsafe(32)
    db.add(GoogleChallenge(token_hash=digest(token), purpose=data.purpose,
        user_id=user.id if user else None, session_hash=session_hash,
        expires_at=now() + timedelta(minutes=5), consumed=False))
    response.set_cookie(COOKIE, token, httponly=True, secure=COOKIE_SECURE, samesite='strict', max_age=300, path='/api/auth/google')
    return {'challenge': token, 'nonce': token, 'client_id': GOOGLE_CLIENT_ID}

@router.post('/exchange')
def exchange(data: CredentialInput, request: Request, response: Response, db: Session = Depends(get_db, scope='function')):
    row = challenge_for(db, request, data.challenge)
    if row.purpose not in {'LOGIN', 'LINK'}:
        raise HTTPException(409, 'Completa el registro o inicia una solicitud nueva')
    claims = verify_credential(data.credential, data.challenge)
    identity = db.get(GoogleIdentity, claims['sub'])
    if row.purpose == 'LINK':
        user = authenticated_user(request, db)
        if user.id != row.user_id or not secrets.compare_digest(row.session_hash or '', digest(request.cookies.get('vitalsync_session', ''))):
            raise HTTPException(403, 'La vinculación pertenece a otra sesión')
        user = db.scalar(select(User).where(User.id == user.id).with_for_update())
        account(db, user)
        existing = db.scalar(select(GoogleIdentity).where(GoogleIdentity.user_id == user.id))
        if identity or existing:
            raise HTTPException(409, 'Esta identidad o cuenta ya tiene una vinculación. Revísala desde tu perfil.')
        db.add(GoogleIdentity(sub=claims['sub'], user_id=user.id, email=claims['email'].lower()))
        row.consumed = True
        db.add(AuditEvent(actor_id=user.id, action='GOOGLE_IDENTITY_LINKED', entity_id=user.id))
        return {'linked': True}
    if identity:
        user = db.scalar(select(User).where(User.id == identity.user_id).with_for_update())
        # Serialize with administrator/self revocation; recheck after locking.
        if not db.scalar(select(GoogleIdentity.sub).where(GoogleIdentity.sub == claims['sub'], GoogleIdentity.user_id == user.id)):
            raise HTTPException(403, 'La vinculación fue revocada. Inicia sesión con contraseña.')
        account(db, user)
        row.consumed = True
        create_session(db, user, response)
        db.add(AuditEvent(actor_id=user.id, action='GOOGLE_LOGIN', entity_id=user.id))
        return result(user)
    existing_user = db.scalar(select(User).where(func.lower(User.email) == claims['email'].lower()))
    if existing_user:
        account(db, existing_user)
        raise HTTPException(409, 'Si ya tienes una cuenta, inicia sesión con contraseña y vincula Google desde tu perfil. No se fusionan cuentas por correo.')
    row.purpose = 'REGISTER'
    row.sub = claims['sub']
    row.email = claims['email'].lower()
    row.name = str(claims.get('name') or claims['email'].split('@')[0])[:120]
    return {'registration_required': True, 'name': row.name, 'email': row.email}

@router.post('/register', status_code=201)
def register(data: RegistrationInput, request: Request, response: Response, db: Session = Depends(get_db, scope='function')):
    row = challenge_for(db, request, data.challenge)
    if row.purpose != 'REGISTER' or not row.sub:
        raise HTTPException(409, 'Verifica tu cuenta Google antes de registrarte')
    # Reuse exactly the existing Colombian identity and telephone validation.
    try:
        Register(email=row.email, password='GoogleAccountUnused123!', given_names='Cuenta', surnames='Google',
            document_number=data.document_number, phone=data.phone, privacy_accepted=data.privacy_accepted)
    except ValidationError:
        raise HTTPException(422, 'Revisa la cédula colombiana (6 a 10 dígitos) y el teléfono (7 a 15 dígitos)') from None
    from app.services.medical_registration import reserved_email
    from sqlalchemy import text
    db.execute(text('SELECT pg_advisory_xact_lock(861993)'))
    if (reserved_email(db, row.email) or db.scalar(select(User.id).where(func.lower(User.email) == row.email))
        or db.get(GoogleIdentity, row.sub)
        or db.scalar(select(Patient.id).where(Patient.document_type == 'CC', Patient.document_number == data.document_number))):
        raise HTTPException(409, 'No pudimos crear la cuenta con esos datos. Si ya tienes cuenta, inicia sesión.')
    user = User(email=row.email, name=row.name, password_hash=passwords.hash(secrets.token_urlsafe(48)),
        role='PATIENT', status='ACTIVE', privacy_notice_version='VITALSYNC-PRIVACIDAD-2026-11-v1', privacy_accepted_at=now())
    db.add(user)
    db.flush()
    db.add(Patient(id=user.id, phone=data.phone, document_type='CC', document_number=data.document_number))
    db.flush()
    db.add(GoogleIdentity(sub=row.sub, user_id=user.id, email=row.email))
    row.consumed = True
    create_session(db, user, response)
    db.add(AuditEvent(actor_id=user.id, action='GOOGLE_PATIENT_REGISTERED', entity_id=user.id))
    booking.notify(db, user.id, 'Te damos la bienvenida a VITALSYNC. Activa tu plan para comenzar.')
    return result(user)

@router.get('/identity')
def identity(user=Depends(authenticated_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    account(db, user)
    linked = db.scalar(select(GoogleIdentity).where(GoogleIdentity.user_id == user.id))
    return {'linked': bool(linked), 'email': linked.email if linked else None, 'enabled': bool(GOOGLE_CLIENT_ID)}

@router.post('/unlink')
def unlink(data: RevokeInput, request: Request, user=Depends(authenticated_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    browser(request)
    user = db.scalar(select(User).where(User.id == user.id).with_for_update())
    account(db, user)
    reauthenticate(user, data.current_password)
    db.execute(delete(GoogleIdentity).where(GoogleIdentity.user_id == user.id))
    db.execute(delete(SessionToken).where(SessionToken.user_id == user.id, SessionToken.token_hash != digest(request.cookies.get('vitalsync_session', ''))))
    db.execute(delete(GoogleChallenge).where(GoogleChallenge.user_id == user.id))
    db.add(AuditEvent(actor_id=user.id, action='GOOGLE_IDENTITY_UNLINKED', entity_id=user.id))
    return {'linked': False}
