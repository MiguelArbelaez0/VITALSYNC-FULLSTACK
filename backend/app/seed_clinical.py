"""Explicit academic seed; additional fictitious patients require an administrative option."""
import argparse
import json
from app.core.config import DEMO_MODE
from app.db.session import SessionLocal
from app.services.clinical_history import seed_histories


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--include-demo-patients',action='store_true',help='Crea dos identidades académicas explícitas si no existen')
    args=parser.parse_args()
    if not DEMO_MODE:
        raise SystemExit('El seed clínico requiere DEMO_MODE=true')
    try:
        with SessionLocal.begin() as db:
            result=seed_histories(db,args.include_demo_patients)
    except Exception:
        raise SystemExit("Seed clínico no completado; transacción revertida. Revisar configuración sin registrar contenido clínico") from None
    print(json.dumps(result))


if __name__=='__main__':
    main()
