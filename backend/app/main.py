from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Depends, HTTPException, Request, Response, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from app.core.config import *
from app.core.security import current_user, passwords, create_session, digest
from app.db.session import get_db
from app.models.entities import *
from app.schemas.requests import Login, Register, Profile, PaymentInput, Reconcile, HoldInput, Cancel, CancelPlanInput, TeleconsultationStatus
from app.repositories.queries import *
from app.services import booking, payments, plans as plan_services, teleconsultations

app = FastAPI(title='VITALSYNC · Portal del paciente', version='1.0.0')
PRIVACY_NOTICE_VERSION = 'VITALSYNC-PRIVACIDAD-2026-11-v1'

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

@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Pydantic's default response includes submitted values; never echo identity data.
    details = [
        {'loc': error.get('loc', ()), 'msg': error.get('msg', 'Dato inválido'), 'type': error.get('type', 'value_error')}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={'detail': details})

@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    import logging
    logging.getLogger('vitalsync').error('Error transaccional (%s)', type(exc).__name__)
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
    number = p.document_number if p else None
    return dict(
        id=u.id,
        name=u.name,
        email=u.email,
        role=u.role,
        phone=p.phone if p else '',
        document_type=p.document_type if p else None,
        document_masked=('•' * max(0, len(number) - 4) + number[-4:]) if number else None,
        has_document=bool(number),
        account_status=u.status,
        registered_at=u.created_at,
        privacy_notice_version=u.privacy_notice_version,
        privacy_accepted_at=u.privacy_accepted_at,
    )

@app.post('/api/auth/register', status_code=201)
def register(data: Register, response: Response, db: Session = Depends(get_db, scope='function')):
    email = data.email.lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)) or db.scalar(
        select(Patient.id).where(
            Patient.document_type == data.document_type,
            Patient.document_number == data.document_number,
        )
    ):
        raise HTTPException(409, 'No pudimos crear la cuenta con esos datos. Si ya tienes cuenta, inicia sesión.')
    user = User(
        email=email,
        name=f'{data.given_names} {data.surnames}',
        password_hash=passwords.hash(data.password),
        role='PATIENT',
        status='ACTIVE',
        privacy_notice_version=PRIVACY_NOTICE_VERSION,
        privacy_accepted_at=now(),
    )
    db.add(user)
    db.flush()
    db.add(Patient(
        id=user.id,
        phone=data.phone,
        document_type=data.document_type,
        document_number=data.document_number,
    ))
    db.flush()
    create_session(db, user, response)
    db.add(AuditEvent(actor_id=user.id, action='PATIENT_REGISTERED', entity_id=user.id))
    booking.notify(db, user.id, 'Te damos la bienvenida a VITALSYNC. Activa tu plan para comenzar.')
    return profile_dict(db, user)

@app.post('/api/auth/login')
def login(data: Login, response: Response, db: Session = Depends(get_db, scope='function')):
    user = db.scalar(select(User).where(func.lower(User.email) == data.email.lower()))
    # Derivación también para correos inexistentes, sin revelar si una cuenta existe.
    valid = passwords.verify(data.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid:
        raise HTTPException(401, 'Correo o contraseña incorrectos')
    if user.role != 'PATIENT':
        raise HTTPException(403, 'Este portal es exclusivo para pacientes')
    if user.status != 'ACTIVE':
        raise HTTPException(403, 'Esta cuenta no está disponible. Contacta al equipo de VITALSYNC.')
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
    patient = db.get(Patient, user.id)
    if data.document_number is not None:
        if patient.document_number and (
            patient.document_type != data.document_type or patient.document_number != data.document_number
        ):
            raise HTTPException(409, 'El documento registrado no se puede cambiar desde este formulario.')
        if not patient.document_number and data.privacy_accepted is not True:
            raise HTTPException(422, 'Acepta el aviso de privacidad para registrar tu documento.')
        duplicate = db.scalar(select(Patient.id).where(
            Patient.document_type == data.document_type,
            Patient.document_number == data.document_number,
            Patient.id != user.id,
        ))
        if duplicate:
            raise HTTPException(409, 'No pudimos guardar este documento. Verifica los datos e inténtalo de nuevo.')
        if not patient.document_number:
            patient.document_type = data.document_type
            patient.document_number = data.document_number
            user.privacy_notice_version = PRIVACY_NOTICE_VERSION
            user.privacy_accepted_at = now()
    user.name = data.name
    patient.phone = data.phone
    db.add(AuditEvent(actor_id=user.id, action='PATIENT_PROFILE_UPDATED', entity_id=user.id))
    return profile_dict(db, user)

def my_plan(db, uid):
    pp = db.get(PatientPlan, uid)
    if not pp:
        return {'status': 'INACTIVE', 'plan': None, 'expires_at': None, 'cancelled_at': None, 'cancelled_by': None, 'cancellation_history': []}
    status = 'EXPIRED' if pp.status == 'ACTIVE' and pp.expires_at <= now() else pp.status
    history = db.execute(
        select(PatientPlanCancellation, Plan.name)
        .join(Plan, Plan.id == PatientPlanCancellation.plan_id)
        .where(PatientPlanCancellation.patient_id == uid)
        .order_by(PatientPlanCancellation.id.desc())
    ).all()
    return {
        'status': status,
        'plan': db.get(Plan, pp.plan_id),
        'expires_at': pp.expires_at,
        'cancelled_at': pp.cancelled_at,
        'cancelled_by': pp.cancelled_by,
        'cancellation_history': [
            {
                'id': item.id,
                'plan_id': item.plan_id,
                'plan_name': name,
                'previous_status': item.previous_status,
                'new_status': item.new_status,
                'policy': item.policy,
                'cancelled_at': item.cancelled_at,
                'effective_at': item.effective_at,
                'changed_by': item.changed_by,
                'reason': item.reason,
            }
            for item, name in history
        ],
    }

@app.get('/api/plans')
def plans(db: Session = Depends(get_db, scope='function')):
    return db.scalars(select(Plan).where(Plan.enabled).order_by(Plan.price)).all()

@app.get('/api/my-plan')
def get_plan(user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    return my_plan(db, user.id)

@app.post('/api/my-plan/cancel')
def cancel_my_plan(data: CancelPlanInput, user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    return plan_services.cancel_subscription(db, user, data.plan_id)

@app.get('/api/dashboard')
def dashboard(user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    rows = db.execute(appointments_query(user.id).where(Appointment.status.in_(['CONFIRMED', 'IN_PROGRESS']), Appointment.ends_at > now()).order_by(Appointment.starts_at)).all()
    unread = len(db.scalars(select(Notification.id).where(Notification.patient_id == user.id, Notification.read == False)).all())
    return dict(name=user.name, plan=my_plan(db, user.id), upcoming_count=len(rows), next_appointment=appointment_dict(*rows[0]) if rows else None, unread_notifications=unread)

@app.get('/api/specialties')
def specialties(db: Session = Depends(get_db, scope='function')):
    return db.scalars(select(Specialty).order_by(Specialty.id)).all()

@app.get('/api/doctors')
def doctors(search: str = Query('', max_length=120), specialty_id: int | None = None, modality: str = Query('PRESENCIAL', pattern='^(PRESENCIAL|VIRTUAL)$'), user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    q = doctors_query().where(Doctor.enabled)
    q = q.where(Doctor.modalities.contains([modality]))
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
def availability(doctor_id: int, day: date | None = None, modality: str = Query('PRESENCIAL', pattern='^(PRESENCIAL|VIRTUAL)$'), user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    d = db.get(Doctor, doctor_id)
    if not d or not d.enabled:
        raise HTTPException(404, 'Médico no disponible')
    if modality not in d.modalities:
        return []
    q = select(Availability).where(Availability.doctor_id == doctor_id, Availability.published, Availability.starts_at > now(), Availability.modalities.contains([modality]))
    if day:
        start = datetime.combine(day, time.min, tzinfo=ZoneInfo('America/Bogota'))
        q = q.where(Availability.starts_at >= start, Availability.starts_at < start + timedelta(days=1))
    slots = db.scalars(q.order_by(Availability.starts_at).limit(500)).all()
    return [dict(id=s.id, starts_at=s.starts_at, ends_at=s.ends_at, modalities=s.modalities, available=booking.available(db, s, user.id)) for s in slots]

@app.post('/api/holds', status_code=201)
def hold(data: HoldInput, user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    return booking.create_hold(db, user, data.availability_id, data.modality)

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
def appointments(view: str = Query('all', pattern='^(all|upcoming|completed|history|cancelled)$'), user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    q = appointments_query(user.id)
    if view == 'upcoming':
        q = q.where(Appointment.status.in_(['CONFIRMED', 'IN_PROGRESS']), Appointment.ends_at > now())
    elif view == 'completed':
        q = q.where(Appointment.status == 'ATTENDED')
    elif view == 'cancelled':
        q = q.where(Appointment.status == 'CANCELLED')
    elif view == 'history':
        q = q.where(Appointment.status != 'CANCELLED', or_(~Appointment.status.in_(['CONFIRMED', 'IN_PROGRESS']), Appointment.ends_at <= now()))
    return [appointment_dict(*row) for row in db.execute(q.order_by(Appointment.starts_at.desc()))]

@app.get('/api/appointments/{appointment_id}')
def appointment(appointment_id: int, user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    row = db.execute(appointments_query(user.id).where(Appointment.id == appointment_id)).first()
    if not row:
        raise HTTPException(404, 'Cita no encontrada')
    result = appointment_dict(*row)
    result['patient'] = user.name
    result['location'] = 'Sede VITALSYNC Bogotá (ficticia)' if result['modality'] == 'PRESENCIAL' else None
    if result['modality'] == 'VIRTUAL':
        vc = db.get(VirtualConsultation, appointment_id)
        result['virtual_status'] = vc.status if vc else 'PROGRAMADA'
    else:
        result['virtual_status'] = None
    result['history'] = db.scalars(select(StatusHistory).where(StatusHistory.appointment_id == appointment_id).order_by(StatusHistory.id)).all()
    return result

@app.get('/api/appointments/{appointment_id}/teleconsult')
def virtual_teleconsult(appointment_id: int, user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    row = db.execute(appointments_query(user.id).where(Appointment.id == appointment_id, Appointment.modality == 'VIRTUAL', Appointment.status != 'CANCELLED')).first()
    if not row:
        raise HTTPException(404, 'Teleconsulta no encontrada o no pertenece a tu cuenta')
    session = db.get(VirtualConsultation, appointment_id)
    if not session or session.status == 'CANCELADA':
        raise HTTPException(404, 'Teleconsulta no disponible')
    result = appointment_dict(*row)
    result['patient'] = user.name
    result['message'] = 'Teleconsulta simulada — sin conexión de audio o video'
    result['virtual_status'] = session.status
    result['demo_mode'] = DEMO_MODE
    result['patient_present_at'] = session.patient_present_at
    result['doctor_present_at'] = session.doctor_present_at
    return result

@app.post('/api/appointments/{appointment_id}/teleconsult/status')
def set_virtual_status(appointment_id: int, data: TeleconsultationStatus, user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    return teleconsultations.transition(db, user, appointment_id, data.status, DEMO_MODE)

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
