"""Recuperación local autorizada: no simula envío de correo."""
import argparse
from getpass import getpass
from sqlalchemy import select, delete
from app.core.config import DEMO_MODE
from app.core.security import passwords
from app.db.session import SessionLocal
from app.models.entities import User, SessionToken, AuditEvent

def main():
    parser = argparse.ArgumentParser(description='Restablecer contraseña local de un paciente ficticio')
    parser.add_argument('email')
    args = parser.parse_args()
    if not DEMO_MODE:
        parser.error('Disponible exclusivamente con DEMO_MODE=true')
    password = getpass('Nueva contraseña (mínimo 10 caracteres): ')
    if len(password) < 10 or len(password) > 128 or password != getpass('Repetir contraseña: '):
        parser.error('Las contraseñas deben coincidir y contener entre 10 y 128 caracteres')
    with SessionLocal.begin() as db:
        user = db.scalar(select(User).where(User.email == args.email.lower(), User.role == 'PATIENT').with_for_update())
        if not user:
            parser.error('Paciente no encontrado')
        user.password_hash = passwords.hash(password)
        db.execute(delete(SessionToken).where(SessionToken.user_id == user.id))
        admin = db.scalar(select(User).where(User.role == 'ADMIN').order_by(User.id))
        db.add(AuditEvent(actor_id=admin.id if admin else user.id, action='LOCAL_PASSWORD_RESET', entity_id=user.id))
    print('Contraseña actualizada y sesiones anteriores revocadas.')

if __name__ == '__main__':
    main()
