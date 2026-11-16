"""Local administrative provisioning. Existing accounts, passwords and links are preserved."""
import secrets
import re
import unicodedata
from sqlalchemy import select, text, func
from app.models.entities import Doctor, DoctorAccount, DoctorCredentialState, User, AuditEvent
from app.core.security import passwords


def temporary_password():
    while True:
        value = secrets.token_urlsafe(24)
        if any(c.islower() for c in value) and any(c.isupper() for c in value) and any(c.isdigit() for c in value):
            return value


def _doctor_email_name(name, doctor_id):
    normalized = unicodedata.normalize('NFKD', name)
    ascii_name = ''.join(char for char in normalized if not unicodedata.combining(char))
    parts = re.findall(r'[a-zA-Z0-9]+', ascii_name.lower())
    if parts and parts[0] in {'dr', 'dra', 'doctor', 'doctora'}:
        parts = parts[1:]
    local = f'{parts[0]}.{parts[-1]}' if len(parts) >= 2 else f'medico.{doctor_id}'
    return local


def available_doctor_email(db, name, doctor_id, domain='doctor.vitalsync.demo'):
    base = _doctor_email_name(name, doctor_id)
    suffix = 0
    while True:
        local = base if suffix == 0 else f'{base}.{doctor_id}' + (f'.{suffix}' if suffix > 1 else '')
        email = f'{local}@{domain.lower()}'
        if not db.scalar(select(User.id).where(func.lower(User.email) == email.lower())):
            return email
        suffix += 1


def provision(db, actor, domain='doctor.vitalsync.demo'):
    if not actor or actor.role != 'ADMIN' or actor.status != 'ACTIVE':
        raise ValueError('Se requiere un actor administrativo activo para aprovisionar')
    db.execute(text('SELECT pg_advisory_xact_lock(861993)'))
    domain=domain.lower()
    created = []
    preserved = []
    for doctor in db.scalars(select(Doctor).order_by(Doctor.id).with_for_update()):
        link = db.scalar(select(DoctorAccount).where(DoctorAccount.doctor_id == doctor.id))
        if link:
            user = db.get(User, link.user_id)
            if not user or user.role != 'DOCTOR':
                raise ValueError(f'Vinculación incompatible en profesional {doctor.id}; se requiere revisión administrativa')
            preserved.append(doctor.id)
            continue
        email = available_doctor_email(db, doctor.name, doctor.id, domain)
        secret = temporary_password()
        user = User(email=email,name=doctor.name,role='DOCTOR',status='ACTIVE' if doctor.enabled else 'DISABLED',password_hash=passwords.hash(secret))
        db.add(user); db.flush()
        db.add(DoctorAccount(user_id=user.id,doctor_id=doctor.id)); db.flush()
        db.add(DoctorCredentialState(user_id=user.id,must_change_password=True))
        db.add(AuditEvent(actor_id=actor.id,action='DOCTOR_ACCOUNT_PROVISIONED',entity_id=doctor.id))
        created.append(dict(doctor_id=doctor.id,user_id=user.id,name=doctor.name,email=email,temporary_password=secret,enabled=doctor.enabled))
    db.flush()
    return dict(new_credentials=created,preserved_doctor_ids=preserved)
