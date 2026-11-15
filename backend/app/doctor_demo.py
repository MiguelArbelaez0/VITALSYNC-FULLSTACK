"""Explicit local setup of the demonstration medical account; never used in production."""
import argparse
import getpass
import secrets
from sqlalchemy import select, inspect, text
from app.core.config import DEMO_MODE
from app.core.security import passwords
from app.db.session import SessionLocal
from app.models.entities import User, Doctor, DoctorAccount, AuditEvent

DEMO_EMAIL = 'medico@vitalsync.demo'
DEMO_PROFESSIONAL = 'Dr. Alejandro Méndez'


def ensure_demo_doctor(db):
    if not DEMO_MODE or not inspect(db.connection()).has_table('doctor_accounts', schema=db.scalar(text('SELECT current_schema()'))):
        return
    doctor = db.scalar(select(Doctor).where(Doctor.name == DEMO_PROFESSIONAL))
    if not doctor or db.scalar(select(DoctorAccount).where(DoctorAccount.doctor_id == doctor.id)):
        return
    # Never take ownership of an existing account with this email.
    if db.scalar(select(User.id).where(User.email == DEMO_EMAIL)):
        return
    user = User(email=DEMO_EMAIL, name=doctor.name, role='DOCTOR', password_hash=passwords.hash(secrets.token_urlsafe(48)))
    db.add(user)
    db.flush()
    db.add(DoctorAccount(user_id=user.id, doctor_id=doctor.id))
    db.add(AuditEvent(actor_id=user.id, action='DEMO_DOCTOR_ACCOUNT_CREATED', entity_id=doctor.id))


def main():
    parser = argparse.ArgumentParser(description='Configura explícitamente la contraseña médica de demostración local')
    parser.add_argument('--set-password', action='store_true', required=True)
    parser.parse_args()
    if not DEMO_MODE:
        raise SystemExit('Esta operación requiere DEMO_MODE=true')
    value = getpass.getpass('Nueva contraseña local (10+ caracteres, mayúscula, minúscula y número): ')
    if len(value) < 10 or len(value) > 128 or not any(c.isupper() for c in value) or not any(c.islower() for c in value) or not any(c.isdigit() for c in value):
        raise SystemExit('La contraseña no cumple los requisitos')
    if getpass.getpass('Repite la contraseña: ') != value:
        raise SystemExit('Las contraseñas no coinciden')
    with SessionLocal.begin() as db:
        ensure_demo_doctor(db)
        user = db.scalar(select(User).join(DoctorAccount, DoctorAccount.user_id == User.id).join(Doctor, Doctor.id == DoctorAccount.doctor_id).where(User.email == DEMO_EMAIL, User.role == 'DOCTOR', Doctor.name == DEMO_PROFESSIONAL))
        if not user:
            raise SystemExit('No existe una cuenta de demostración vinculada de forma segura. Revisa el seed y la vinculación institucional.')
        user.password_hash = passwords.hash(value)
        db.add(AuditEvent(actor_id=user.id, action='DEMO_DOCTOR_PASSWORD_SET', entity_id=user.id))
    print('Contraseña local establecida para ' + DEMO_EMAIL)


if __name__ == '__main__':
    main()
