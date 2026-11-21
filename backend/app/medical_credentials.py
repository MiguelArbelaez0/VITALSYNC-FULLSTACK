"""Authenticated local one-time credential handoff. No password HTTP response."""
import argparse
import getpass
import json
import os
from pathlib import Path
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.entities import User
from app.core.security import passwords
from app.services.medical_registration import deliver

def main():
    parser = argparse.ArgumentParser(description='Emite una entrega médica pendiente a un archivo privado local')
    parser.add_argument('--actor-email', required=True)
    parser.add_argument('--delivery-id', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    password = getpass.getpass('Contraseña actual del administrador (no se mostrará): ')
    created = False
    try:
        with SessionLocal.begin() as db:
            actor = db.scalar(select(User).where(User.email == args.actor_email.lower(), User.role == 'ADMIN', User.status == 'ACTIVE'))
            if not actor or not passwords.verify(password, actor.password_hash): raise ValueError('Autenticación administrativa incorrecta')
            credentials = deliver(db, actor, args.delivery_id)
            descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
            with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
                json.dump(credentials, output, ensure_ascii=False, indent=2)
                output.flush(); os.fsync(output.fileno())
        print('Entrega emitida una vez al archivo privado. El secreto cifrado fue retirado de PostgreSQL.')
    except Exception:
        if created: args.output.unlink(missing_ok=True)
        raise SystemExit('No se emitió la entrega. Revisa contraseña, permisos, estado pendiente, clave y ruta exclusiva de salida.') from None

if __name__ == '__main__': main()
