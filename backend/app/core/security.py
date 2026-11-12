import hashlib
import secrets
from datetime import timedelta
from fastapi import Depends, HTTPException, Request
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.entities import SessionToken, User, Doctor, DoctorAccount, Patient, now
from app.core.config import SESSION_HOURS, COOKIE_SECURE

passwords = PasswordHash.recommended()

def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

def create_session(db, user, response):
    token = secrets.token_urlsafe(48)
    db.add(SessionToken(token_hash=digest(token), user_id=user.id, expires_at=now() + timedelta(hours=SESSION_HOURS)))
    response.set_cookie('vitalsync_session', token, httponly=True, samesite='strict', secure=COOKIE_SECURE, max_age=SESSION_HOURS * 3600, path='/')

def authenticated_user(request: Request, db: Session = Depends(get_db, scope='function')):
    token = request.cookies.get('vitalsync_session', '')
    session = db.get(SessionToken, digest(token))
    if not session or session.expires_at <= now():
        raise HTTPException(401, 'Tu sesión ha vencido. Inicia sesión para continuar')
    user = db.get(User, session.user_id)
    if not user or user.status != 'ACTIVE':
        raise HTTPException(401, 'Tu sesión no está disponible. Inicia sesión nuevamente')
    return user


def current_user(user=Depends(authenticated_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    if user.role != 'PATIENT' or not db.get(Patient, user.id):
        raise HTTPException(403, 'Esta operación requiere el rol de paciente')
    return user


current_patient = current_user


def doctor_for_user(db, user):
    doctor = db.scalar(select(Doctor).join(DoctorAccount, DoctorAccount.doctor_id == Doctor.id).where(DoctorAccount.user_id == user.id, Doctor.enabled.is_(True)))
    if user.role != 'DOCTOR' or not doctor:
        raise HTTPException(403, 'La cuenta médica no tiene un perfil profesional activo vinculado. Contacta a VITALSYNC.')
    return doctor


def current_doctor(user=Depends(authenticated_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    return doctor_for_user(db, user)
