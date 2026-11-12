"""Read-only verification of both portals and PostgreSQL persistence.

Uses existing accounts; never registers users, books, cancels, pays or changes passwords.
Credentials come from environment variables or hidden prompts, never from the report.
"""
import argparse
import getpass
import http.cookiejar
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BASE = ''
COMPOSE = ['docker', 'compose', '-p', 'vitalsync']


class Session:
    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(self, path, body=None, expected=200):
        request = urllib.request.Request(BASE + '/api' + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=20) as response:
                assert response.status == expected, path
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == expected:
                return None
            raise RuntimeError(f'{path}: HTTP {error.code}; no se modificaron credenciales') from None


def snapshot():
    script = (ROOT / 'infrastructure/database_snapshot.py').read_text(encoding='utf-8')
    data = subprocess.check_output(COMPOSE + ['exec', '-T', 'backend', 'python', '-'],
                                   cwd=ROOT, input=script, text=True)
    return json.loads(data)


def collect(patient, doctor):
    return dict(patient=patient.request('/auth/me'), patient_appointments=patient.request('/appointments'),
                doctor=doctor.request('/auth/me'), doctor_appointments=doctor.request('/doctor/appointments?view=all'))


def main():
    global BASE
    parser = argparse.ArgumentParser(description='Comprueba ambos portales sin crear ni modificar datos de negocio')
    parser.add_argument('--restart', action='store_true', help='Reinicia db, backend y frontend conservando el volumen')
    parser.add_argument('--output', type=Path, help='Informe JSON sin datos personales ni credenciales')
    args = parser.parse_args()
    config = json.loads(subprocess.check_output(COMPOSE + ['config', '--format', 'json'], cwd=ROOT, text=True))
    assert config['name'] == 'vitalsync'
    assert config['volumes']['vitalsync_data'] == {'name':'vitalsync_vitalsync_data','external':True}
    assert set(config['services']) == {'db', 'backend', 'frontend'}
    frontend_port = config['services']['frontend']['ports'][0]['published']
    BASE = os.getenv('VITALSYNC_BASE_URL', f'http://localhost:{frontend_port}').rstrip('/')
    assert BASE in {f'http://localhost:{frontend_port}', f'http://127.0.0.1:{frontend_port}'}, 'La URL debe corresponder al frontend local del proyecto principal'
    patient_password = os.getenv('VITALSYNC_PATIENT_PASSWORD') or getpass.getpass('Contraseña del paciente existente: ')
    doctor_password = os.getenv('VITALSYNC_DOCTOR_PASSWORD') or getpass.getpass('Contraseña del medico existente: ')
    patient, doctor = Session(), Session()
    baseline = snapshot()
    try:
        patient.request('/auth/login', {'email':os.getenv('VITALSYNC_PATIENT_EMAIL','paciente@vitalsync.demo'),'password':patient_password})
        doctor.request('/auth/login', {'email':os.getenv('VITALSYNC_DOCTOR_EMAIL','medico@vitalsync.demo'),'password':doctor_password})
        before = collect(patient, doctor)
        assert before['patient']['role'] == 'PATIENT' and before['doctor']['role'] == 'DOCTOR'
        patient.request('/doctor/dashboard', expected=403)
        doctor.request('/dashboard', expected=403)
        doctor_id = int(before['doctor']['doctor_id'])
        expected_script = f"""import json
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.entities import Appointment
with SessionLocal() as db:
    print(json.dumps([dict(id=a.id,patient_id=a.patient_id) for a in db.scalars(select(Appointment).where(Appointment.doctor_id=={doctor_id}))]))
"""
        assigned = json.loads(subprocess.check_output(COMPOSE + ['exec','-T','backend','python','-'],cwd=ROOT,input=expected_script,text=True))
        assert {a['id'] for a in assigned} == {a['id'] for a in before['doctor_appointments']}
        own_assigned = {a['id'] for a in assigned if a['patient_id'] == before['patient']['id']}
        assert own_assigned <= {a['id'] for a in before['patient_appointments']}
        if args.restart:
            subprocess.run(COMPOSE + ['restart','db'],cwd=ROOT,check=True)
            subprocess.run(COMPOSE + ['up','-d','--wait','db'],cwd=ROOT,check=True)
            subprocess.run(COMPOSE + ['restart','backend','frontend'],cwd=ROOT,check=True)
            subprocess.run(COMPOSE + ['up','-d','--wait','--wait-timeout','90'],cwd=ROOT,check=True)
        after = collect(patient, doctor)
        assert before == after, 'Cambios en las citas o sesiones tras reiniciar'
        assert snapshot() == baseline, 'Cambios en el contenido persistido (se excluyen solamente las sesiones de acceso)'
        assert patient.request('/dashboard') is not None and doctor.request('/doctor/dashboard') is not None
        result = dict(result='PASS',project='vitalsync',services=['db','backend','frontend'],database='vitalsync',
                      volume='vitalsync_vitalsync_data',roles=['PATIENT','DOCTOR'],assigned_appointments_verified=len(assigned),
                      shared_patient_doctor_appointments=len(own_assigned),tables_verified=len(baseline),
                      restart_verified=args.restart,sessions_persisted=True,domain_rows_created=0,passwords_changed=0)
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))
    finally:
        for session in (patient,doctor):
            try:
                session.request('/auth/logout', {})
            except Exception:
                pass


if __name__ == '__main__':
    main()
