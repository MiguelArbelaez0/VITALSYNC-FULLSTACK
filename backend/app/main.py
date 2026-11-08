from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Depends, HTTPException, Request, Response, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from app.core.config import *
from app.core.security import current_user, passwords, create_session, digest
from app.db.session import get_db
from app.models.entities import *
from app.schemas.requests import Login, Register, Profile, PaymentInput, Reconcile, HoldInput, Cancel
from app.repositories.queries import *
from app.services import booking, payments

app = FastAPI(title='VITALSYNC · Portal del paciente', version='1.0.0')

@app.middleware('http')
async def browser_security(request: Request, call_next):
    if request.method not in ['GET', 'HEAD', 'OPTIONS']:
        origin = request.headers.get('origin')
        if (origin and origin not in ALLOWED_ORIGINS) or request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse(status_code=403, content={'detail': 'Origen no autorizado'})
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.exception_handler(IntegrityError)
async def conflict(request, exc):
    return JSONResponse(status_code=409, content={'detail': 'La operación entra en conflicto con datos existentes. Actualiza e inténtalo de nuevo'})

@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    import logging
    logging.getLogger('vitalsync').exception('Error transaccional', exc_info=exc)
    return JSONResponse(status_code=503, content={'detail': 'No pudimos guardar la operación. Los cambios se revirtieron; vuelve a intentarlo'})

@app.get('/api/health')
def health(db: Session = Depends(get_db, scope='function')):
    db.execute(text('SELECT 1'))
    return {'status': 'ok', 'database': 'postgresql'}

@app.get('/api/config')
def config():
    return dict(demo_mode=DEMO_MODE, hold_minutes=HOLD_MINUTES, cancellation_hours=CANCELLATION_HOURS, timezone='America/Bogota')

def profile_dict(db, u):
    p = db.get(Patient, u.id)
    return dict(id=u.id, name=u.name, email=u.email, role=u.role, phone=p.phone if p else '')

@app.post('/api/auth/register', status_code=201)
def register(data: Register, response: Response, db: Session = Depends(get_db, scope='function')):
    email = data.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, 'Este correo ya está registrado')
    user = User(email=email, name=data.name, password_hash=passwords.hash(data.password), role='PATIENT')
    db.add(user)
    db.flush()
    db.add(Patient(id=user.id))
    db.flush()
    create_session(db, user, response)
    booking.notify(db, user.id, 'Te damos la bienvenida a VITALSYNC. Activa tu plan para comenzar.')
    return profile_dict(db, user)

@app.post('/api/auth/login')
def login(data: Login, response: Response, db: Session = Depends(get_db, scope='function')):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    # Derivación también para correos inexistentes, sin revelar si una cuenta existe.
    valid = passwords.verify(data.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid:
        raise HTTPException(401, 'Correo o contraseña incorrectos')
    if user.role != 'PATIENT':
        raise HTTPException(403, 'Este portal es exclusivo para pacientes')
    create_session(db, user, response)
    return profile_dict(db, user)

DUMMY_HASH = passwords.hash('dummy-password-not-an-account')

@app.post('/api/auth/logout')
def logout(request: Request, response: Response, db: Session = Depends(get_db, scope='function')):
    session = db.get(SessionToken, digest(request.cookies.get('vitalsync_session', '')))
    if session:
        db.delete(session)
    response.delete_cookie('vitalsync_session', path='/')
    return {'message': 'Sesión cerrada'}

@app.get('/api/auth/me')
def me(user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    return profile_dict(db, user)

@app.patch('/api/auth/me')
def update_me(data: Profile, user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    user.name = data.name
    db.get(Patient, user.id).phone = data.phone
    return profile_dict(db, user)

def my_plan(db, uid):
    pp = db.get(PatientPlan, uid)
    if not pp:
        return {'status': 'INACTIVE', 'plan': None, 'expires_at': None}
    return {'status': 'EXPIRED' if pp.expires_at <= now() else pp.status, 'plan': db.get(Plan, pp.plan_id), 'expires_at': pp.expires_at}

@app.get('/api/plans')
def plans(db: Session = Depends(get_db, scope='function')):
    return db.scalars(select(Plan).where(Plan.enabled).order_by(Plan.price)).all()

@app.get('/api/my-plan')
def get_plan(user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    return my_plan(db, user.id)

@app.get('/api/dashboard')
def dashboard(user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    rows = db.execute(appointments_query(user.id).where(Appointment.status == 'CONFIRMED', Appointment.starts_at > now()).order_by(Appointment.starts_at)).all()
    unread = len(db.scalars(select(Notification.id).where(Notification.patient_id == user.id, Notification.read == False)).all())
    return dict(name=user.name, plan=my_plan(db, user.id), upcoming_count=len(rows), next_appointment=appointment_dict(*rows[0]) if rows else None, unread_notifications=unread)

@app.get('/api/specialties')
def specialties(db: Session = Depends(get_db, scope='function')):
    return db.scalars(select(Specialty).order_by(Specialty.id)).all()

@app.get('/api/doctors')
def doctors(search: str = Query('', max_length=120), specialty_id: int | None = None, user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    q = doctors_query().where(Doctor.enabled)
    if search:
        q = q.where(Doctor.name.ilike('%' + search.replace('%', '').replace('_', '') + '%'))
    if specialty_id:
        q = q.where(Doctor.specialty_id == specialty_id)
    return [doctor_dict(*row) for row in db.execute(q.order_by(Doctor.id))]

@app.get('/api/doctors/{doctor_id}')
def doctor(doctor_id: int, user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    row = db.execute(doctors_query().where(Doctor.id == doctor_id, Doctor.enabled)).first()
    if not row:
        raise HTTPException(404, 'Médico no encontrado')
    return doctor_dict(*row)

@app.get('/api/doctors/{doctor_id}/availability')
def availability(doctor_id: int, day: date | None = None, user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    d = db.get(Doctor, doctor_id)
    if not d or not d.enabled:
        raise HTTPException(404, 'Médico no disponible')
    q = select(Availability).where(Availability.doctor_id == doctor_id, Availability.published, Availability.starts_at > now())
    if day:
        start = datetime.combine(day, time.min, tzinfo=ZoneInfo('America/Bogota'))
        q = q.where(Availability.starts_at >= start, Availability.starts_at < start + timedelta(days=1))
    slots = db.scalars(q.order_by(Availability.starts_at).limit(500)).all()
    return [dict(id=s.id, starts_at=s.starts_at, ends_at=s.ends_at, available=booking.available(db, s, user.id)) for s in slots]

@app.post('/api/holds', status_code=201)
def hold(data: HoldInput, user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    return booking.create_hold(db, user, data.availability_id)

@app.get('/api/holds/{hold_id}')
def get_hold(hold_id: int, user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    return booking.owned_hold(db, user, hold_id)

@app.post('/api/holds/{hold_id}/release')
def release_hold(hold_id: int, user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    booking.lock_patient(db, user.id)
    h = booking.owned_hold(db, user, hold_id)
    if h.status == 'CONFIRMED':
        raise HTTPException(409, 'La retención corresponde a una cita confirmada')
    h.status = 'RELEASED'
    return {'message': 'Retención liberada'}

def demo_only():
    if not DEMO_MODE:
        raise HTTPException(403, 'Los pagos simulados están deshabilitados fuera del entorno de demostración')

@app.post('/api/payments', dependencies=[Depends(demo_only)])
def payment(data: PaymentInput, user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    return payments.pay(db, user, data)

@app.get('/api/payments')
def get_payments(user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    return db.scalars(select(Payment).where(Payment.patient_id == user.id).order_by(Payment.id.desc()).limit(100)).all()

@app.post('/api/payments/{payment_id}/reconcile', dependencies=[Depends(demo_only)])
def reconcile(payment_id: int, data: Reconcile, user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    return payments.reconcile(db, user, payment_id, data.status)

@app.post('/api/holds/{hold_id}/confirm')
def confirm(hold_id: int, user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    a = booking.confirm(db, user, hold_id)
    return {'id': a.id, 'code': a.code, 'status': a.status}

@app.get('/api/appointments')
def appointments(user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    return [appointment_dict(*row) for row in db.execute(appointments_query(user.id).order_by(Appointment.starts_at.desc()))]

@app.get('/api/appointments/{appointment_id}')
def appointment(appointment_id: int, user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    row = db.execute(appointments_query(user.id).where(Appointment.id == appointment_id)).first()
    if not row:
        raise HTTPException(404, 'Cita no encontrada')
    result = appointment_dict(*row)
    result['patient'] = user.name
    result['history'] = db.scalars(select(StatusHistory).where(StatusHistory.appointment_id == appointment_id).order_by(StatusHistory.id)).all()
    return result

@app.post('/api/appointments/{appointment_id}/cancel')
def cancel(appointment_id: int, data: Cancel, user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    a = booking.cancel(db, user, appointment_id, data)
    return {'id': a.id, 'status': a.status, 'economic_review': a.economic_review}

@app.get('/api/notifications')
def notifications(user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    return db.scalars(select(Notification).where(Notification.patient_id == user.id).order_by(Notification.id.desc()).limit(100)).all()

@app.post('/api/notifications/{notification_id}/read')
def read_notification(notification_id: int, user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    n = db.get(Notification, notification_id)
    if not n or n.patient_id != user.id:
        raise HTTPException(404, 'Notificación no encontrada')
    n.read = True
    return {'message': 'Notificación leída'}
