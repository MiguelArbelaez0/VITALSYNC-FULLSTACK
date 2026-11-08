"""Operación administrativa local explícita e idempotente. Nunca restablece datos."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select, text
from app.db.session import SessionLocal
from app.models.entities import *
from app.core.security import passwords
from app.core.config import DEMO_MODE

def seed():
    if not DEMO_MODE:
        return
    with SessionLocal.begin() as db:
        db.execute(text('SELECT pg_advisory_xact_lock(861991)'))
        admin = db.scalar(select(User).where(User.email == 'admin@vitalsync.demo'))
        if not admin:
            admin = User(email='admin@vitalsync.demo', name='Administrador de demostración', password_hash=passwords.hash('AdminDemo2026!'), role='ADMIN')
            db.add(admin)
            db.flush()
        if not db.scalar(select(User).where(User.email == 'paciente@vitalsync.demo')):
            u = User(email='paciente@vitalsync.demo', name='Valentina Torres', password_hash=passwords.hash('Paciente2026!'), role='PATIENT')
            db.add(u)
            db.flush()
            db.add(Patient(id=u.id, phone='300 123 4567'))
            db.flush()
            db.add(Notification(patient_id=u.id, message='Bienvenida a VITALSYNC. Activa un plan para solicitar tu primera cita.'))
        names = ['Medicina general', 'Cardiología', 'Dermatología', 'Psicología', 'Pediatría']
        ids = []
        for name in names:
            s = db.scalar(select(Specialty).where(Specialty.name == name))
            if not s:
                s = Specialty(name=name)
                db.add(s)
                db.flush()
            ids.append(s.id)
        for name, price, copay, covered, modalities, desc in [('Básico', 59000, 15000, ids[:1], ['PRESENCIAL'], 'Tu cuidado esencial. Consultas de medicina general.'), ('Estándar', 109000, 10000, ids[:3], ['PRESENCIAL','VIRTUAL'], 'Más especialistas y consultas presenciales o virtuales.'), ('Premium', 189000, 0, ids, ['PRESENCIAL','VIRTUAL'], 'Todas las especialidades y modalidades, sin copagos por consulta.')]:
            if not db.scalar(select(Plan.id).where(Plan.name == name)):
                db.add(Plan(name=name, price=price, copay=copay, specialty_ids=covered, modalities=modalities, description=desc, duration_days=30))
        for i, name in enumerate(['Dra. Isabella Ríos', 'Dr. Alejandro Méndez', 'Dra. Camila Restrepo', 'Dra. Sofía Herrera', 'Dr. Nicolás Vargas']):
            d = db.scalar(select(Doctor).where(Doctor.name == name))
            if not d:
                d = Doctor(name=name, specialty_id=ids[i], bio=f'Profesional ficticio de demostración en {names[i].lower()}. Atención cercana, orientación preventiva y acompañamiento personalizado. Consultas presenciales y virtuales simuladas de 30 minutos.', modalities=['PRESENCIAL','VIRTUAL'])
                db.add(d)
                db.flush()
            today = datetime.now(ZoneInfo('America/Bogota')).replace(hour=9, minute=0, second=0, microsecond=0)
            for day in range(1, 22):
                for hour in [9, 10, 11, 14, 15, 16]:
                    start = (today + timedelta(days=day)).replace(hour=hour)
                    if not db.scalar(select(Availability.id).where(Availability.doctor_id == d.id, Availability.starts_at == start)):
                        modes = d.modalities
                        db.add(Availability(doctor_id=d.id, starts_at=start, ends_at=start + timedelta(minutes=30), published_by=admin.id, modalities=modes))
            blocked = (today + timedelta(days=1)).replace(hour=11)
            if not db.scalar(select(DoctorBlock.id).where(DoctorBlock.doctor_id == d.id, DoctorBlock.starts_at == blocked)):
                db.add(DoctorBlock(doctor_id=d.id, starts_at=blocked, ends_at=blocked + timedelta(minutes=30), reason='Bloqueo administrativo de demostración'))
        if not db.scalar(select(AuditEvent.id).where(AuditEvent.action == 'DEVELOPMENT_SEED')):
            db.add(AuditEvent(actor_id=admin.id, action='DEVELOPMENT_SEED'))

if __name__ == '__main__':
    seed()
