"""Public applications never grant clinical access; only scoped review provisions doctors."""
import re
import secrets
import unicodedata
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import select, func, text, delete
from app.core.config import DEMO_MODE, DOCTOR_CREDENTIAL_KEY
from app.core.security import passwords, digest
from app.models.entities import (DoctorApplication, DoctorCredentialDelivery, User, Doctor, DoctorAccount,
    DoctorCredentialState, Specialty, SessionToken, RecoveryRequest, AdminEvent, now)
from app.services.doctor_accounts import temporary_password

def fail(message, status=409):
    raise HTTPException(status, message)

def normalized(value):
    return re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in unicodedata.normalize('NFKD', value.lower()) if not unicodedata.combining(c))).strip()

def name_base(given_names, surnames):
    first, last = normalized(given_names).split(), normalized(surnames).split()
    if not first or not last: fail('Indica nombres y apellidos válidos', 422)
    return f'{first[0]}.{last[0]}'

def reserved_email(db, email):
    return db.scalar(select(DoctorApplication.id).where(DoctorApplication.institutional_email == email.lower())) is not None

def proposed_email(db, given_names, surnames):
    db.execute(text('SELECT pg_advisory_xact_lock(861993)'))
    base = name_base(given_names, surnames)
    suffix = 0
    while True:
        candidate = f'{base}{"." + str(suffix) if suffix else ""}@doctor.vitalsync.demo'
        if not db.scalar(select(User.id).where(func.lower(User.email) == candidate)) and not reserved_email(db, candidate):
            return candidate
        suffix += 1

def public_dict(row):
    return dict(id=row.id, status=row.status, institutional_email=row.institutional_email,
        submitted_at=row.submitted_at, reviewed_at=row.reviewed_at, review_reason=row.review_reason,
        verification_kind=row.verification_kind,
        message='Solicitud pendiente de revisión; aún no tienes acceso médico.' if row.status == 'PENDING' else
            'Solicitud aprobada. Solicita al administrador la entrega privada de tus credenciales.' if row.status == 'APPROVED' else
            'Solicitud rechazada. Contacta al administrador para revisar el motivo.')

def admin_dict(db, row):
    delivery = db.scalar(select(DoctorCredentialDelivery).where(DoctorCredentialDelivery.user_id == row.user_id).order_by(DoctorCredentialDelivery.id.desc())) if row.user_id else None
    return dict(**public_dict(row), given_names=row.given_names, surnames=row.surnames,
        document_type=row.document_type, document_number=row.document_number, professional_number=row.professional_number,
        specialty_id=row.specialty_id, specialty=db.get(Specialty, row.specialty_id).name,
        contact_email=row.contact_email, phone=row.phone, bio=row.bio, version=row.version,
        doctor_id=row.doctor_id, user_id=row.user_id, reviewed_by=row.reviewed_by,
        delivery_id=delivery.id if delivery else None, delivery_status=delivery.status if delivery else None)

def submit(db, data):
    email = proposed_email(db, data.given_names, data.surnames)
    if db.scalar(select(DoctorApplication.id).where(
        (DoctorApplication.document_number == data.document_number) | (DoctorApplication.professional_number == data.professional_number))):
        fail('Ya existe una solicitud con ese documento o registro profesional. Conserva tu código de seguimiento o contacta al administrador.')
    if not db.get(Specialty, data.specialty_id): fail('La especialidad seleccionada no está disponible', 422)
    full_name = f'{data.given_names} {data.surnames}'
    for doctor in db.scalars(select(Doctor)):
        if re.sub(r'^(dr|dra|doctor|doctora) ', '', normalized(doctor.name)) == normalized(full_name):
            fail('Ya existe un profesional con ese nombre. Contacta al administrador para usar tu cuenta existente.')
    if data.contact_email and db.scalar(select(User.id).where(func.lower(User.email) == str(data.contact_email).lower(), User.role == 'DOCTOR')):
        fail('Este contacto corresponde a una cuenta médica existente. Solicita asistencia administrativa.')
    receipt = secrets.token_urlsafe(32)
    row = DoctorApplication(given_names=data.given_names, surnames=data.surnames, document_type='CC',
        document_number=data.document_number, professional_number=data.professional_number, specialty_id=data.specialty_id,
        contact_email=str(data.contact_email).lower() if data.contact_email else None, phone=data.phone, bio=data.bio,
        institutional_email=email, receipt_hash=digest(receipt), status='PENDING', version=1)
    db.add(row); db.flush()
    db.add(AdminEvent(actor_id=None, action='DOCTOR_APPLICATION_SUBMITTED', resource='doctor_application',
        entity_id=row.id, reason='Solicitud pública con consentimiento de tratamiento de datos', details={'privacy_notice_version': 'VITALSYNC-MEDICAL-2026-11-v1'}))
    return {**public_dict(row), 'receipt': receipt}

def cipher():
    try:
        return Fernet(DOCTOR_CREDENTIAL_KEY.encode())
    except (ValueError, TypeError):
        fail('La entrega privada de credenciales no está configurada. Contacta al operador.', 503)

def queue_credentials(db, actor, user, reason):
    secret = temporary_password()
    encrypted = cipher().encrypt(secret.encode()).decode()
    # All secrets for this account become obsolete when a replacement is authorized.
    for old in db.scalars(select(DoctorCredentialDelivery).where(DoctorCredentialDelivery.user_id == user.id, DoctorCredentialDelivery.status == 'PENDING').with_for_update()):
        old.status = 'REVOKED'; old.encrypted_secret = None
    user.password_hash = passwords.hash(secret)
    db.execute(delete(SessionToken).where(SessionToken.user_id == user.id))
    for request in db.scalars(select(RecoveryRequest).where(RecoveryRequest.user_id == user.id, RecoveryRequest.status.in_(['PENDING', 'ISSUED']))):
        request.status = 'REVOKED'
    state = db.get(DoctorCredentialState, user.id)
    if state: state.must_change_password = False; state.changed_at = now()
    else: db.add(DoctorCredentialState(user_id=user.id, must_change_password=False))
    row = DoctorCredentialDelivery(user_id=user.id, actor_id=actor.id, encrypted_secret=encrypted, reason=reason, status='PENDING')
    db.add(row); db.flush()
    return row

def review(db, actor, application_id, data, approve):
    from app.services.admin_portal import audit
    db.execute(text('SELECT pg_advisory_xact_lock(861993)'))
    row = db.scalar(select(DoctorApplication).where(DoctorApplication.id == application_id).with_for_update())
    if not row: fail('Solicitud médica no encontrada', 404)
    desired = 'APPROVED' if approve else 'REJECTED'
    if row.status == desired:
        return {**admin_dict(db, row), 'idempotent': True}
    if row.status != 'PENDING' or row.version != data.version:
        fail('La solicitud ya fue revisada o cambió. Actualiza la lista.')
    if approve:
        cipher()  # Fail before provisioning if secure delivery cannot be guaranteed.
        if not data.professional_review_confirmed: fail('Confirma la revisión de los datos profesionales', 422)
        expected = 'ACADEMIC_SIMULATED' if DEMO_MODE else 'MANUAL_REVIEW'
        if data.verification_kind != expected: fail('La modalidad de revisión no corresponde a este entorno', 422)
        if db.scalar(select(User.id).where(func.lower(User.email) == row.institutional_email)):
            fail('El correo reservado entra en conflicto. Se requiere revisión administrativa; no se modificó otra cuenta.')
        full_name = f'{row.given_names} {row.surnames}'
        for existing in db.scalars(select(Doctor)):
            if re.sub(r'^(dr|dra|doctor|doctora) ', '', normalized(existing.name)) == normalized(full_name):
                fail('Ya existe un profesional con ese nombre. Revisa la cuenta existente antes de continuar.')
        doctor = Doctor(name=full_name, specialty_id=row.specialty_id, bio=row.bio, enabled=True,
            modalities=['PRESENCIAL', 'VIRTUAL'], is_demo_doctor=False)
        db.add(doctor); db.flush()
        user = User(email=row.institutional_email, name=full_name, role='DOCTOR', status='ACTIVE', password_hash=passwords.hash(secrets.token_urlsafe(48)))
        db.add(user); db.flush()
        db.add(DoctorAccount(user_id=user.id, doctor_id=doctor.id)); db.flush()
        row.user_id = user.id; row.doctor_id = doctor.id; row.verification_kind = expected
        queue_credentials(db, actor, user, data.reason)
    row.status = desired; row.version += 1; row.reviewed_at = now(); row.reviewed_by = actor.id; row.review_reason = data.reason
    audit(db, actor, f'DOCTOR_APPLICATION_{desired}', 'doctor_application', row.id, data.reason,
        {'verification_kind': row.verification_kind, 'doctor_id': row.doctor_id, 'user_id': row.user_id})
    db.flush()
    return {**admin_dict(db, row), 'idempotent': False}

def deliver(db, actor, delivery_id):
    from app.services.admin_portal import scopes, audit
    if actor.role != 'ADMIN' or actor.status != 'ACTIVE' or 'accounts' not in scopes(db, actor): fail('Operador no autorizado', 403)
    user_id = db.scalar(select(DoctorCredentialDelivery.user_id).where(DoctorCredentialDelivery.id == delivery_id))
    user = db.scalar(select(User).where(User.id == user_id).with_for_update()) if user_id else None
    row = db.scalar(select(DoctorCredentialDelivery).where(DoctorCredentialDelivery.id == delivery_id).with_for_update())
    if not row or row.status != 'PENDING' or not row.encrypted_secret: fail('La entrega no está pendiente o ya fue consumida')
    if not user or user.role != 'DOCTOR' or user.status != 'ACTIVE': fail('La cuenta médica no está activa', 403)
    try: secret = cipher().decrypt(row.encrypted_secret.encode()).decode()
    except InvalidToken: fail('No se puede descifrar la entrega con la clave configurada. Revisa la custodia de la clave.', 503)
    if not passwords.verify(secret, user.password_hash): fail('La entrega fue sustituida por otras credenciales')
    row.status = 'DELIVERED'; row.delivered_at = now(); row.encrypted_secret = None
    audit(db, actor, 'DOCTOR_CREDENTIALS_DELIVERED', 'account', user.id, 'Entrega única a archivo local privado', {'delivery_id': row.id})
    return {'delivery_id': row.id, 'email': user.email, 'password': secret, 'role': 'DOCTOR', 'login_url': 'http://localhost:5188/login'}
