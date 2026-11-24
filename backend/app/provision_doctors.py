"""Administrative credential handoff to a private local file, never to an HTTP endpoint."""
import argparse
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from sqlalchemy import select, text
from app.core.config import DEMO_MODE
from app.db.session import SessionLocal
from app.models.entities import Availability, Doctor, Specialty, User
from app.services.doctor_accounts import provision


def add_academic_profiles(db, actor):
    """Create the named demonstration cohort without updating existing profiles."""
    if not DEMO_MODE or not actor or actor.role != 'ADMIN' or actor.status != 'ACTIVE':
        raise ValueError('Se requiere modo demostración y un administrador activo')
    db.execute(text('SELECT pg_advisory_xact_lock(861993)'))
    names = [
        'Alba Prado', 'Benjamín Solar', 'Clara Niebla', 'Darío Pinar', 'Elena Brisa',
        'Fabio Duna', 'Gabriela Roble', 'Hugo Miral', 'Inés Ladera', 'Julián Arroyo',
    ]
    specialties = db.scalars(select(Specialty).order_by(Specialty.id).limit(5)).all()
    if not specialties:
        raise ValueError('Se requieren especialidades inicializadas')
    tomorrow = datetime.now(ZoneInfo('America/Bogota')).replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
    for index, full_name in enumerate(names):
        if db.scalar(select(Doctor.id).where(Doctor.name == full_name)):
            continue
        doctor = Doctor(name=full_name, specialty_id=specialties[index % len(specialties)].id,
            bio='Profesional ficticio para demostraciones académicas de VITALSYNC.',
            enabled=True, is_demo_doctor=True, modalities=['PRESENCIAL', 'VIRTUAL'])
        db.add(doctor)
        db.flush()
        for day in range(7):
            start = tomorrow + timedelta(days=day)
            db.add(Availability(doctor_id=doctor.id, published_by=actor.id,
                starts_at=start, ends_at=start + timedelta(minutes=30),
                modalities=doctor.modalities, published=True))


def main():
    parser = argparse.ArgumentParser(description='Aprovisiona únicamente profesionales sin cuenta y exporta sus claves iniciales una sola vez')
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--actor-email',default='admin@vitalsync.demo')
    parser.add_argument('--domain',default='doctor.vitalsync.demo')
    parser.add_argument('--add-academic-profiles', action='store_true')
    args=parser.parse_args()
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]*\.[a-z]{2,}',args.domain) or '..' in args.domain:
        raise SystemExit('Dominio de correo inválido')
    if not DEMO_MODE and args.domain=='doctor.vitalsync.demo':
        raise SystemExit('En un entorno no demostrativo se requiere un dominio institucional explícito')
    created_file=False
    try:
        with SessionLocal.begin() as db:
            actor=db.scalar(select(User).where(User.email==args.actor_email))
            if args.add_academic_profiles:
                add_academic_profiles(db, actor)
            result=provision(db,actor,args.domain)
            # Exclusive creation and mode 0600 prevent overwriting a previous handoff.
            descriptor=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            created_file=True
            with os.fdopen(descriptor,'w',encoding='utf-8') as stream:
                json.dump(result,stream,ensure_ascii=False,indent=2); stream.flush(); os.fsync(stream.fileno())
        print(json.dumps({'created':len(result['new_credentials']),'preserved':len(result['preserved_doctor_ids']),'credential_file':str(args.output)}))
    except Exception:
        if created_file:
            args.output.unlink(missing_ok=True)
        raise SystemExit('No se completó el aprovisionamiento; se revirtió la transacción y no se modificaron cuentas existentes') from None


if __name__=='__main__':
    main()
