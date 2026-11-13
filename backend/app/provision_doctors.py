"""Administrative credential handoff to a private local file, never to an HTTP endpoint."""
import argparse
import json
import os
import re
from pathlib import Path
from sqlalchemy import select
from app.core.config import DEMO_MODE
from app.db.session import SessionLocal
from app.models.entities import User
from app.services.doctor_accounts import provision


def main():
    parser = argparse.ArgumentParser(description='Aprovisiona únicamente profesionales sin cuenta y exporta sus claves iniciales una sola vez')
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--actor-email',default='admin@vitalsync.demo')
    parser.add_argument('--domain',default='vitalsync.demo')
    args=parser.parse_args()
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]*\.[a-z]{2,}',args.domain) or '..' in args.domain:
        raise SystemExit('Dominio de correo inválido')
    if not DEMO_MODE and args.domain=='vitalsync.demo':
        raise SystemExit('En un entorno no demostrativo se requiere un dominio institucional explícito')
    created_file=False
    try:
        with SessionLocal.begin() as db:
            actor=db.scalar(select(User).where(User.email==args.actor_email))
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
