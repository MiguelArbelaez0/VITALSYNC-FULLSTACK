from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import EmailStr, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.entities import DoctorApplication, DoctorCredentialDelivery, User, DoctorAccount, Specialty
from app.schemas.requests import Input, Register, DoctorPasswordChange
from app.schemas.admin import Reason
from app.routers.admin import require, paging
from app.services import medical_registration as service, admin_portal
from app.core.security import passwords, current_user, digest

router = APIRouter(tags=['medical-registration'])

@router.post('/api/auth/password')
def patient_password(data: DoctorPasswordChange, request: Request, user=Depends(current_user, scope='function'), db: Session = Depends(get_db, scope='function')):
    from app.models.entities import SessionToken, AuditEvent, GoogleChallenge
    from sqlalchemy import delete
    user = db.scalar(select(User).where(User.id == user.id).with_for_update().execution_options(populate_existing=True))
    if not passwords.verify(data.current_password, user.password_hash): raise HTTPException(400, 'La contraseña actual no es correcta')
    if passwords.verify(data.new_password, user.password_hash): raise HTTPException(422, 'Elige una contraseña diferente de la actual')
    user.password_hash = passwords.hash(data.new_password)
    db.execute(delete(SessionToken).where(SessionToken.user_id == user.id, SessionToken.token_hash != digest(request.cookies.get('vitalsync_session', ''))))
    db.execute(delete(GoogleChallenge).where(GoogleChallenge.user_id == user.id))
    db.add(AuditEvent(actor_id=user.id, action='PATIENT_PASSWORD_CHANGED', entity_id=user.id))
    return {'message': 'Contraseña actualizada. Las demás sesiones se cerraron.'}

class Names(Input):
    given_names: str = Field(min_length=2, max_length=60)
    surnames: str = Field(min_length=2, max_length=60)

    @model_validator(mode='after')
    def names_fit(self):
        if len(self.given_names) + len(self.surnames) + 1 > 120:
            raise ValueError('El nombre completo debe tener como máximo 120 caracteres')
        service.name_base(self.given_names, self.surnames)
        return self

class MedicalApplication(Names):
    document_type: Literal['CC'] = 'CC'
    document_number: str
    specialty_id: int = Field(gt=0)
    professional_number: str = Field(min_length=4, max_length=50, pattern=r'^[A-Za-z0-9./\-]+$')
    contact_email: EmailStr | None = None
    phone: str = Field(min_length=7, max_length=30, pattern=r'^[+\d\s()\-]+$')
    bio: str = Field(min_length=20, max_length=2000)
    privacy_accepted: Literal[True]

    @field_validator('document_number', mode='before')
    @classmethod
    def document(cls, value): return Register.validate_document_number(value)

    @field_validator('phone')
    @classmethod
    def phone_digits(cls, value): return Register.validate_phone_digits(value)

    @field_validator('professional_number')
    @classmethod
    def professional(cls, value): return value.upper()

class Receipt(Input):
    receipt: str = Field(min_length=32, max_length=128)

class Review(Reason):
    version: int = Field(gt=0)
    professional_review_confirmed: bool = False
    verification_kind: Literal['ACADEMIC_SIMULATED', 'MANUAL_REVIEW'] | None = None

class ResetCredentials(Reason):
    current_password: str = Field(min_length=8, max_length=128)

@router.get('/api/auth/medical-registration/options')
def options(db: Session = Depends(get_db, scope='function')):
    return {'specialties': [dict(id=s.id, name=s.name) for s in db.scalars(select(Specialty).order_by(Specialty.name))],
        'document_types': ['CC'], 'verification_kind': 'ACADEMIC_SIMULATED' if service.DEMO_MODE else 'MANUAL_REVIEW'}

@router.post('/api/auth/doctor-applications/preview')
def preview(data: Names, db: Session = Depends(get_db, scope='function')):
    return {'institutional_email': service.proposed_email(db, data.given_names, data.surnames), 'reserved': False}

@router.post('/api/auth/doctor-applications', status_code=201)
def submit(data: MedicalApplication, db: Session = Depends(get_db, scope='function')):
    return service.submit(db, data)

@router.post('/api/auth/doctor-applications/status')
def status(data: Receipt, db: Session = Depends(get_db, scope='function')):
    row = db.scalar(select(DoctorApplication).where(DoctorApplication.receipt_hash == service.digest(data.receipt)))
    if not row: raise HTTPException(404, 'Código de seguimiento no encontrado')
    return service.public_dict(row)

@router.get('/api/admin/doctor-applications')
def applications(search: str = '', status: Literal['PENDING', 'APPROVED', 'REJECTED'] | None = None,
        p=Depends(paging), user=Depends(require('accounts'), scope='function'), db: Session = Depends(get_db, scope='function')):
    q = select(DoctorApplication)
    if search: q = q.where((DoctorApplication.given_names + ' ' + DoctorApplication.surnames).icontains(search[:120], autoescape=True))
    if status: q = q.where(DoctorApplication.status == status)
    return admin_portal.page(db, q.order_by(DoctorApplication.submitted_at.desc()), lambda r: service.admin_dict(db, r), *p)

@router.get('/api/admin/doctor-applications/{id}')
def detail(id: int, user=Depends(require('accounts'), scope='function'), db: Session = Depends(get_db, scope='function')):
    from app.models.entities import AdminEvent
    row = admin_portal.get(db, DoctorApplication, id)
    admin_portal.audit(db, user, 'DOCTOR_APPLICATION_VIEWED', 'doctor_application', id)
    return {**service.admin_dict(db, row), 'administrative_history': [dict(action=e.action, actor_id=e.actor_id, created_at=e.created_at, reason=e.reason) for e in db.scalars(select(AdminEvent).where(AdminEvent.resource == 'doctor_application', AdminEvent.entity_id == id).order_by(AdminEvent.id))]}

@router.post('/api/admin/doctor-applications/{id}/approve')
def approve(id: int, data: Review, user=Depends(require('accounts'), scope='function'), db: Session = Depends(get_db, scope='function')):
    return service.review(db, user, id, data, True)

@router.post('/api/admin/doctor-applications/{id}/reject')
def reject(id: int, data: Review, user=Depends(require('accounts'), scope='function'), db: Session = Depends(get_db, scope='function')):
    return service.review(db, user, id, data, False)

@router.post('/api/admin/accounts/{id}/doctor-credentials')
def reset_credentials(id: int, data: ResetCredentials, user=Depends(require('accounts'), scope='function'), db: Session = Depends(get_db, scope='function')):
    if not passwords.verify(data.current_password, user.password_hash): raise HTTPException(403, 'Confirma tu contraseña administrativa')
    target = admin_portal.get(db, User, id, True)
    if target.role != 'DOCTOR' or not db.scalar(select(DoctorAccount.doctor_id).where(DoctorAccount.user_id == id)):
        raise HTTPException(404, 'Cuenta médica no encontrada')
    if target.status != 'ACTIVE': raise HTTPException(409, 'Activa primero la cuenta médica tras verificar su identidad')
    delivery = service.queue_credentials(db, user, target, data.reason)
    admin_portal.audit(db, user, 'DOCTOR_CREDENTIALS_RESET', 'account', id, data.reason, {'delivery_id': delivery.id})
    return {'delivery_id': delivery.id, 'status': delivery.status, 'email': target.email,
        'message': 'Credenciales reemplazadas y sesiones anteriores revocadas. El operador debe emitir la entrega privada local.'}

@router.get('/api/admin/doctor-credential-deliveries')
def deliveries(p=Depends(paging), user=Depends(require('accounts'), scope='function'), db: Session = Depends(get_db, scope='function')):
    q = select(DoctorCredentialDelivery).order_by(DoctorCredentialDelivery.id.desc())
    return admin_portal.page(db, q, lambda r: dict(id=r.id, user_id=r.user_id, email=db.get(User, r.user_id).email,
        status=r.status, created_at=r.created_at, delivered_at=r.delivered_at, reason=r.reason), *p)
