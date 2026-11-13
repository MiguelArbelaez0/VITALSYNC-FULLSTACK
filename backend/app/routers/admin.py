"""Administrative API: role and per-module permissions checked server-side."""
from datetime import date,datetime,time,timedelta
from fastapi import APIRouter,Depends,Query
from sqlalchemy import select,func,or_,delete,text
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.security import authenticated_user
from app.core.config import DEMO_MODE
from app.models.entities import (User,Patient,Doctor,DoctorAccount,Specialty,Plan,PlanRevision,PatientPlan,Payment,Hold,Appointment,Availability,DoctorBlock,BlockRelease,StatusHistory,Notification,AuditEvent,AdminEvent,AdminPermission,RecoveryRequest,RefundRequest,RefundTransition,AppSetting,SessionToken,now)
from app.schemas.admin import *
from app.schemas.requests import Cancel
from app.services import admin_portal as s,plan_terms,booking,payments,doctor_portal
import secrets

router=APIRouter(prefix='/api/admin',tags=['admin'])
def require(scope):
    def authorized(user=Depends(authenticated_user,scope='function'),db:Session=Depends(get_db,scope='function')):
        if user.role!='ADMIN' or scope not in s.scopes(db,user):s.fail('Acceso administrativo no autorizado para esta operación',403)
        return user
    return authorized

def paging(page:int=Query(1,ge=1),size:int=Query(20,ge=1,le=100)):return page,size

def period(query,column,since,until):
    if since and until and until<since:s.fail('La fecha final debe ser posterior a la inicial',422)
    if since:query=query.where(column>=datetime.combine(since,time.min,tzinfo=s.BOGOTA))
    if until:query=query.where(column<datetime.combine(until+timedelta(days=1),time.min,tzinfo=s.BOGOTA))
    return query

@router.get('/dashboard')
def dashboard(since:date|None=None,until:date|None=None,user=Depends(require('dashboard'),scope='function'),db:Session=Depends(get_db,scope='function')):
    aq=period(select(Appointment),Appointment.starts_at,since,until).subquery()
    pq=period(select(Payment),Payment.created_at,since,until).subquery()
    rq=period(select(RefundRequest),RefundRequest.created_at,since,until).subquery()
    appts=dict(db.execute(select(aq.c.status,func.count()).group_by(aq.c.status)).all())
    modes=dict(db.execute(select(aq.c.modality,func.count()).group_by(aq.c.modality)).all())
    pays=dict(db.execute(select(pq.c.status,func.count()).group_by(pq.c.status)).all())
    patients=dict(db.execute(select(User.status,func.count()).join(Patient,Patient.id==User.id).group_by(User.status)).all())
    enabled=db.scalar(select(func.count()).select_from(Doctor).join(DoctorAccount,DoctorAccount.doctor_id==Doctor.id).join(User,User.id==DoctorAccount.user_id).where(Doctor.enabled,User.status=='ACTIVE'))
    doctors=db.scalar(select(func.count()).select_from(Doctor))
    metrics={'patients_total':sum(patients.values()),'patients_active':patients.get('ACTIVE',0),'patients_inactive':patients.get('DISABLED',0),'doctors_total':doctors,'doctors_active':enabled,'doctors_inactive':doctors-enabled,'pending_holds':db.scalar(select(func.count()).select_from(Hold).where(Hold.status=='ACTIVE',Hold.expires_at>now())),'appointments_confirmed':appts.get('CONFIRMED',0),'appointments_virtual':modes.get('VIRTUAL',0),'appointments_onsite':modes.get('PRESENCIAL',0),'appointments_completed':appts.get('ATTENDED',0),'appointments_cancelled':appts.get('CANCELLED',0),'plans_active':db.scalar(select(func.count()).select_from(Plan).where(Plan.enabled)),'subscriptions_active':db.scalar(select(func.count()).select_from(PatientPlan).where(PatientPlan.status=='ACTIVE',PatientPlan.expires_at>now())),'payments_approved':pays.get('APPROVED',0),'payments_rejected':pays.get('REJECTED',0),'payments_pending':pays.get('PENDING',0)+pays.get('IN_RECONCILIATION',0),'refund_requests':db.scalar(select(func.count()).select_from(rq))}
    return dict(metrics=metrics,appointment_states=appts,modalities=modes,payment_states=pays)

@router.get('/doctors')
def doctors(search:str=Query('',max_length=120),specialty_id:int|None=None,enabled:bool|None=None,p=Depends(paging),user=Depends(require('doctors'),scope='function'),db:Session=Depends(get_db,scope='function')):
    q=select(Doctor)
    if search:q=q.where(Doctor.name.ilike(s.like(search)))
    if specialty_id:q=q.where(Doctor.specialty_id==specialty_id)
    if enabled is not None:q=q.where(Doctor.enabled==enabled)
    return s.page(db,q.order_by(Doctor.name),lambda d:s.doctor_dict(db,d),*p)

@router.post('/doctors',status_code=201)
def create_doctor(data:DoctorCreate,user=Depends(require('doctors'),scope='function'),db:Session=Depends(get_db,scope='function')):
    if 'accounts' not in s.scopes(db,user):s.fail('Crear cuentas médicas requiere permiso de cuentas',403)
    return s.create_doctor(db,user,data)

@router.patch('/doctors/{id}')
def edit_doctor(id:int,data:DoctorInput,user=Depends(require('doctors'),scope='function'),db:Session=Depends(get_db,scope='function')):
    if data.enabled!=s.get(db,Doctor,id).enabled and 'accounts' not in s.scopes(db,user):s.fail('Cambiar el acceso requiere permiso de cuentas',403)
    return s.update_doctor(db,user,id,data)

@router.post('/specialties',status_code=201)
def create_specialty(data:SpecialtyInput,user=Depends(require('doctors'),scope='function'),db:Session=Depends(get_db,scope='function')):
    db.execute(text('SELECT pg_advisory_xact_lock(861995)'))
    if db.scalar(select(Specialty.id).where(func.lower(Specialty.name)==data.name.lower())):s.fail('La especialidad ya existe')
    row=Specialty(name=data.name);db.add(row);db.flush();s.audit(db,user,'ADMIN_SPECIALTY_CREATED','specialty',row.id,data.reason)
    return dict(id=row.id,name=row.name)

@router.patch('/specialties/{id}')
def edit_specialty(id:int,data:SpecialtyInput,user=Depends(require('doctors'),scope='function'),db:Session=Depends(get_db,scope='function')):
    db.execute(text('SELECT pg_advisory_xact_lock(861995)'))
    row=s.get(db,Specialty,id,True)
    if db.scalar(select(Specialty.id).where(func.lower(Specialty.name)==data.name.lower(),Specialty.id!=id)):s.fail('La especialidad ya existe')
    old=row.name;row.name=data.name;s.audit(db,user,'ADMIN_SPECIALTY_UPDATED','specialty',id,data.reason,{'before':old,'after':row.name});return dict(id=id,name=row.name)

@router.get('/patients')
def patients(search:str=Query('',max_length=254),status:Literal['ACTIVE','DISABLED']|None=None,p=Depends(paging),user=Depends(require('patients'),scope='function'),db:Session=Depends(get_db,scope='function')):
    q=select(User,Patient).join(Patient,Patient.id==User.id)
    if search:q=q.where(or_(User.name.ilike(s.like(search)),User.email.ilike(s.like(search)),Patient.document_number==search))
    if status:q=q.where(User.status==status)
    return s.page(db,q.order_by(User.name),s.patient_dict,*p)

@router.get('/patients/{id}')
def patient(id:int,user=Depends(require('patients'),scope='function'),db:Session=Depends(get_db,scope='function')):
    p=s.get(db,Patient,id);u=s.get(db,User,id);pp=db.get(PatientPlan,id)
    s.audit(db,user,'ADMIN_PATIENT_VIEWED','patient',id)
    return dict(**s.patient_dict(u,p),phone=p.phone,document_number=p.document_number,subscription=dict(status=pp.status,expires_at=pp.expires_at,plan=plan_terms.subscription(db,pp)) if pp else None,appointments=[s.appointment_dict(db,a) for a in db.scalars(select(Appointment).where(Appointment.patient_id==id).order_by(Appointment.starts_at.desc()).limit(100))],notifications=[dict(id=n.id,message=n.message,created_at=n.created_at,read=n.read) for n in db.scalars(select(Notification).where(Notification.patient_id==id).order_by(Notification.id.desc()).limit(30))])

@router.patch('/accounts/{id}/status')
def status_account(id:int,data:AccountStatus,user=Depends(require('accounts'),scope='function'),db:Session=Depends(get_db,scope='function')):return s.set_account(db,user,id,data)

@router.post('/accounts/{id}/recovery')
def request_recovery(id:int,data:Reason,user=Depends(require('accounts'),scope='function'),db:Session=Depends(get_db,scope='function')):
    target=s.get(db,User,id)
    if target.role=='ADMIN' and not s.scopes(db,target)<=s.scopes(db,user):s.fail('No puedes recuperar una cuenta con permisos superiores',403)
    r=s.request_recovery(db,user,target,data.reason)
    return dict(request_id=r.id,status=r.status,message='Solicitud registrada. El operador debe emitir el enlace mediante el comando local privado; no se cambió la contraseña.')

@router.get('/appointments')
def appointments(search:str=Query('',max_length=120),patient_id:int|None=None,doctor_id:int|None=None,specialty_id:int|None=None,day:date|None=None,status:str=Query('',max_length=32),modality:Modality|None=None,p=Depends(paging),user=Depends(require('appointments'),scope='function'),db:Session=Depends(get_db,scope='function')):
    q=select(Appointment).join(Doctor,Doctor.id==Appointment.doctor_id).join(User,User.id==Appointment.patient_id)
    if search:q=q.where(or_(Appointment.code.ilike(s.like(search)),User.name.ilike(s.like(search))))
    if patient_id:q=q.where(Appointment.patient_id==patient_id)
    if doctor_id:q=q.where(Appointment.doctor_id==doctor_id)
    if specialty_id:q=q.where(Doctor.specialty_id==specialty_id)
    if day:q=period(q,Appointment.starts_at,day,day)
    if status:q=q.where(Appointment.status==status)
    if modality:q=q.where(Appointment.modality==modality)
    return s.page(db,q.order_by(Appointment.starts_at.desc(),Appointment.id.desc()),lambda a:s.appointment_dict(db,a),*p)

@router.get('/appointments/{id}')
def appointment(id:int,user=Depends(require('appointments'),scope='function'),db:Session=Depends(get_db,scope='function')):
    a=s.get(db,Appointment,id)
    return dict(**s.appointment_dict(db,a),history=[dict(status=h.status,reason=h.reason,author_id=h.author_id,created_at=h.created_at) for h in db.scalars(select(StatusHistory).where(StatusHistory.appointment_id==id).order_by(StatusHistory.id))])

@router.post('/appointments/{id}/cancel')
def cancel(id:int,data:Cancel,user=Depends(require('appointments'),scope='function'),db:Session=Depends(get_db,scope='function')):
    a=s.get(db,Appointment,id)
    result=doctor_portal.cancel(db,s.get(db,Doctor,a.doctor_id),user,id,data,administrative=True)
    s.audit(db,user,'ADMIN_APPOINTMENT_CANCELLED','appointment',id,data.reason,{'before':'CONFIRMED','after':'CANCELLED'})
    return result

@router.post('/appointments/{id}/reschedule')
def reschedule(id:int,data:RescheduleInput,user=Depends(require('appointments'),scope='function'),db:Session=Depends(get_db,scope='function')):return s.reschedule(db,user,id,data)

@router.get('/availability')
def availability(doctor_id:int|None=None,day:date|None=None,published:bool|None=None,p=Depends(paging),user=Depends(require('availability'),scope='function'),db:Session=Depends(get_db,scope='function')):
    q=select(Availability)
    if doctor_id:q=q.where(Availability.doctor_id==doctor_id)
    if day:q=period(q,Availability.starts_at,day,day)
    if published is not None:q=q.where(Availability.published==published)
    return s.page(db,q.order_by(Availability.starts_at.desc()),lambda a:s.slot_dict(db,a),*p)

@router.post('/availability',status_code=201)
def create_slot(data:SlotInput,user=Depends(require('availability'),scope='function'),db:Session=Depends(get_db,scope='function')):return s.save_slot(db,user,data)

@router.patch('/availability/{id}')
def edit_slot(id:int,data:SlotInput,user=Depends(require('availability'),scope='function'),db:Session=Depends(get_db,scope='function')):return s.save_slot(db,user,data,id)

@router.post('/schedules',status_code=201)
def schedule(data:ScheduleInput,user=Depends(require('availability'),scope='function'),db:Session=Depends(get_db,scope='function')):return s.publish_schedule(db,user,data)

@router.get('/blocks')
def blocks(doctor_id:int|None=None,p=Depends(paging),user=Depends(require('availability'),scope='function'),db:Session=Depends(get_db,scope='function')):
    q=select(DoctorBlock)
    if doctor_id:q=q.where(DoctorBlock.doctor_id==doctor_id)
    return s.page(db,q.order_by(DoctorBlock.starts_at.desc()),lambda b:dict(id=b.id,doctor_id=b.doctor_id,doctor=db.get(Doctor,b.doctor_id).name,starts_at=b.starts_at,ends_at=b.ends_at,reason=b.reason,released=db.get(BlockRelease,b.id) is not None),*p)

@router.post('/blocks',status_code=201)
def create_block(data:BlockInput,user=Depends(require('availability'),scope='function'),db:Session=Depends(get_db,scope='function')):return s.block(db,user,data)

@router.post('/blocks/{id}/release')
def release_block(id:int,data:Reason,user=Depends(require('availability'),scope='function'),db:Session=Depends(get_db,scope='function')):
    b=s.get(db,DoctorBlock,id);s.get(db,Doctor,b.doctor_id,True)
    if db.get(BlockRelease,id):s.fail('El bloqueo ya fue liberado')
    db.add(BlockRelease(block_id=id,actor_id=user.id,reason=data.reason));s.audit(db,user,'ADMIN_BLOCK_RELEASED','block',id,data.reason)
    return dict(id=id,released=True)

@router.get('/plans')
def plans(search:str=Query('',max_length=120),p=Depends(paging),user=Depends(require('plans'),scope='function'),db:Session=Depends(get_db,scope='function')):
    q=select(Plan)
    if search:q=q.where(Plan.name.ilike(s.like(search)))
    return s.page(db,q.order_by(Plan.id),lambda plan:dict(**plan_terms.catalog(db,plan),subscribers=db.scalar(select(func.count()).select_from(PatientPlan).where(PatientPlan.plan_id==plan.id,PatientPlan.status=='ACTIVE',PatientPlan.expires_at>now()))),*p)

@router.post('/plans',status_code=201)
def create_plan(data:PlanInput,user=Depends(require('plans'),scope='function'),db:Session=Depends(get_db,scope='function')):return s.save_plan(db,user,data)

@router.patch('/plans/{id}')
def edit_plan(id:int,data:PlanInput,user=Depends(require('plans'),scope='function'),db:Session=Depends(get_db,scope='function')):return s.save_plan(db,user,data,id)

@router.get('/plans/{id}')
def plan(id:int,user=Depends(require('plans'),scope='function'),db:Session=Depends(get_db,scope='function')):
    p=s.get(db,Plan,id)
    return dict(**plan_terms.catalog(db,p),revisions=[dict(version=r.version,terms=r.terms,reason=r.reason,actor_id=r.actor_id,created_at=r.created_at) for r in db.scalars(select(PlanRevision).where(PlanRevision.plan_id==id).order_by(PlanRevision.version.desc()))],subscriptions=[dict(patient_id=pp.patient_id,status=pp.status,expires_at=pp.expires_at,terms=plan_terms.subscription(db,pp)) for pp in db.scalars(select(PatientPlan).where(PatientPlan.plan_id==id).limit(100))])

@router.get('/payments')
def payment_list(search:str=Query('',max_length=120),patient_id:int|None=None,status:str=Query('',max_length=32),p=Depends(paging),user=Depends(require('payments'),scope='function'),db:Session=Depends(get_db,scope='function')):
    q=select(Payment,User.name).join(User,User.id==Payment.patient_id)
    if patient_id:q=q.where(Payment.patient_id==patient_id)
    if search:q=q.where(or_(User.name.ilike(s.like(search)),Payment.idempotency_key.ilike(s.like(search))))
    if status:q=q.where(Payment.status==status)
    def project(pay,name):
        refund=db.scalar(select(RefundRequest.id).where(RefundRequest.payment_id==pay.id))
        return dict(id=pay.id,reference='SIM-'+str(pay.id),patient_id=pay.patient_id,patient=name,kind=pay.kind,plan_id=pay.plan_id,hold_id=pay.hold_id,amount=pay.amount,status=pay.status,created_at=pay.created_at,refund_id=refund)
    return s.page(db,q.order_by(Payment.id.desc()),project,*p)

@router.get('/payments/{id}')
def payment_detail(id:int,user=Depends(require('payments'),scope='function'),db:Session=Depends(get_db,scope='function')):
    p=s.get(db,Payment,id)
    return dict(id=p.id,patient_id=p.patient_id,kind=p.kind,plan_id=p.plan_id,hold_id=p.hold_id,amount=p.amount,status=p.status,created_at=p.created_at,history=[dict(action=a.action,actor_id=a.actor_id,created_at=a.created_at) for a in db.scalars(select(AuditEvent).where(AuditEvent.entity_id==id,or_(AuditEvent.action.like('SIMULATED_PAYMENT_%'),AuditEvent.action.like('PAYMENT_RECONCILED_%'))).order_by(AuditEvent.id))],administrative_history=[dict(action=a.action,actor_id=a.actor_id,reason=a.reason,created_at=a.created_at,details=a.details) for a in db.scalars(select(AdminEvent).where(AdminEvent.resource=='payment',AdminEvent.entity_id==id).order_by(AdminEvent.id))])

@router.post('/payments/{id}/reconcile')
def reconcile(id:int,data:ReconcileInput,user=Depends(require('payments'),scope='function'),db:Session=Depends(get_db,scope='function')):
    if not DEMO_MODE:s.fail('La conciliación simulada requiere modo demostración',403)
    p=s.get(db,Payment,id);booking.lock_patient(db,p.patient_id);p=s.get(db,Payment,id,True)
    old=p.status;result=payments.reconcile(db,s.get(db,User,p.patient_id),id,data.status,actor=user)
    if old!=result.status:s.audit(db,user,'ADMIN_PAYMENT_RECONCILED','payment',id,data.reason,{'before':old,'after':result.status,'amount':result.amount})
    return dict(id=result.id,status=result.status,amount=result.amount)

@router.get('/refunds')
def refunds(status:str=Query('',max_length=32),p=Depends(paging),user=Depends(require('refunds'),scope='function'),db:Session=Depends(get_db,scope='function')):
    q=select(RefundRequest)
    if status:q=q.where(RefundRequest.status==status)
    return s.page(db,q.order_by(RefundRequest.id.desc()),lambda r:s.refund_dict(db,r),*p)

@router.get('/refunds/{id}')
def refund_detail(id:int,user=Depends(require('refunds'),scope='function'),db:Session=Depends(get_db,scope='function')):
    r=s.get(db,RefundRequest,id)
    return dict(**s.refund_dict(db,r),history=[dict(status=h.status,previous_status=h.previous_status,reason=h.reason,actor_id=h.actor_id,created_at=h.created_at) for h in db.scalars(select(RefundTransition).where(RefundTransition.refund_id==id).order_by(RefundTransition.id))])

@router.post('/refunds',status_code=201)
def create_refund(data:RefundCreate,user=Depends(require('refunds'),scope='function'),db:Session=Depends(get_db,scope='function')):
    if not DEMO_MODE:s.fail('Las devoluciones simuladas requieren modo demostración',403)
    return s.create_refund(db,user,data)

@router.post('/refunds/{id}/transition')
def refund_step(id:int,data:RefundStep,user=Depends(require('refunds'),scope='function'),db:Session=Depends(get_db,scope='function')):
    if not DEMO_MODE:s.fail('Las devoluciones simuladas requieren modo demostración',403)
    return s.transition_refund(db,user,id,data)

@router.get('/audit')
def audit_list(search:str=Query('',max_length=120),actor_id:int|None=None,since:date|None=None,until:date|None=None,p=Depends(paging),user=Depends(require('audit'),scope='function'),db:Session=Depends(get_db,scope='function')):
    q=select(AdminEvent)
    if search:q=q.where(or_(AdminEvent.action.ilike(s.like(search)),AdminEvent.resource.ilike(s.like(search))))
    if actor_id:q=q.where(AdminEvent.actor_id==actor_id)
    q=period(q,AdminEvent.created_at,since,until)
    return s.page(db,q.order_by(AdminEvent.id.desc()),lambda a:dict(id=a.id,actor_id=a.actor_id,action=a.action,resource=a.resource,entity_id=a.entity_id,reason=a.reason,details=a.details,created_at=a.created_at),*p)

@router.get('/audit/legacy')
def audit_legacy(p=Depends(paging),user=Depends(require('audit'),scope='function'),db:Session=Depends(get_db,scope='function')):
    q=select(AuditEvent).where(~AuditEvent.action.like('CLINICAL_%'))
    return s.page(db,q.order_by(AuditEvent.id.desc()),lambda a:dict(id=a.id,actor_id=a.actor_id,action=a.action,entity_id=a.entity_id,created_at=a.created_at),*p)

@router.get('/settings')
def settings(user=Depends(require('settings'),scope='function'),db:Session=Depends(get_db,scope='function')):
    row=db.get(AppSetting,'institution')
    return dict(institution=row.value if row else dict(display_name='VITALSYNC',support_email='soporte@vitalsync.demo',support_phone='+57 300 000 0000'),demo_mode=DEMO_MODE,scopes=sorted(s.scopes(db,user)),available_scopes=list(s.SCOPES),policies=dict(deactivation='Resolve future appointments and holds before disabling',plan_changes='Current contracts retain purchased conditions; renewals use the current catalogue',refunds='Manual review and authorization; simulated transfers only',clinical='Administrator has no clinical access'))

@router.put('/settings')
def save_settings(data:SettingsInput,user=Depends(require('settings'),scope='function'),db:Session=Depends(get_db,scope='function')):
    row=db.get(AppSetting,'institution')
    values=data.model_dump(exclude={'reason'});values['support_email']=str(values['support_email'])
    if row:row.value=values
    else:db.add(AppSetting(key='institution',value=values))
    s.audit(db,user,'ADMIN_SETTINGS_UPDATED','settings',reason=data.reason)
    return dict(institution=values)

@router.get('/administrators')
def administrators(user=Depends(require('accounts'),scope='function'),db:Session=Depends(get_db,scope='function')):
    return [dict(**s.user_dict(u),scopes=sorted(s.scopes(db,u))) for u in db.scalars(select(User).where(User.role=='ADMIN').order_by(User.id))]

@router.post('/administrators',status_code=201)
def create_admin(data:AdminCreate,user=Depends(require('accounts'),scope='function'),db:Session=Depends(get_db,scope='function')):
    db.execute(text('SELECT pg_advisory_xact_lock(861996)'));s.validate_scopes(db,user,data.scopes)
    if db.scalar(select(User.id).where(func.lower(User.email)==str(data.email).lower())):s.fail('Correo ya registrado')
    u=User(name=data.name,email=str(data.email).lower(),role='ADMIN',password_hash=s.passwords.hash(secrets.token_urlsafe(48)))
    db.add(u);db.flush();db.add(AdminPermission(user_id=u.id,scopes=data.scopes));s.request_recovery(db,user,u,data.reason)
    s.audit(db,user,'ADMIN_ACCOUNT_CREATED','account',u.id,data.reason,{'role':'ADMIN','scopes':data.scopes})
    return s.user_dict(u)

@router.patch('/administrators/{id}/permissions')
def permissions(id:int,data:PermissionInput,user=Depends(require('accounts'),scope='function'),db:Session=Depends(get_db,scope='function')):
    db.execute(text('SELECT pg_advisory_xact_lock(861996)'));s.validate_scopes(db,user,data.scopes)
    target=s.get(db,User,id,True)
    if target.role!='ADMIN':s.fail('Los permisos de módulo se asignan únicamente a administradores',422)
    if not s.scopes(db,target)<=s.scopes(db,user):s.fail('No puedes modificar permisos superiores a los tuyos',403)
    if id==user.id:s.fail('Otro administrador autorizado debe modificar tus permisos para evitar bloqueo propio')
    if set(data.scopes)!=set(s.SCOPES):s.ensure_owner_remains(db,id)
    row=db.get(AdminPermission,id)
    if row:row.scopes=data.scopes
    else:db.add(AdminPermission(user_id=id,scopes=data.scopes))
    db.execute(delete(SessionToken).where(SessionToken.user_id==id))
    s.audit(db,user,'ADMIN_PERMISSIONS_UPDATED','account',id,data.reason,{'scopes':data.scopes})
    return dict(id=id,scopes=data.scopes)


@router.get('/recoveries')
def recoveries(p=Depends(paging),user=Depends(require('accounts'),scope='function'),db:Session=Depends(get_db,scope='function')):
    q=select(RecoveryRequest,User.email).join(User,User.id==RecoveryRequest.user_id)
    return s.page(db,q.order_by(RecoveryRequest.id.desc()),lambda r,email:dict(id=r.id,user_id=r.user_id,email=email,status=r.status,expires_at=r.expires_at,created_at=r.created_at),*p)

@router.post('/recoveries/{id}/revoke')
def revoke_recovery(id:int,data:Reason,user=Depends(require('accounts'),scope='function'),db:Session=Depends(get_db,scope='function')):
    r=s.get(db,RecoveryRequest,id,True)
    target=s.get(db,User,r.user_id)
    if target.role=='ADMIN' and not s.scopes(db,target)<=s.scopes(db,user):s.fail('No puedes revocar enlaces de una cuenta superior',403)
    if r.status not in ['PENDING','ISSUED']:s.fail('El enlace ya no está pendiente')
    r.status='REVOKED';s.audit(db,user,'ACCESS_RECOVERY_REVOKED','account',r.user_id,data.reason,{'request_id':id})
    return dict(id=id,status=r.status)


@router.get('/options')
def options(user=Depends(authenticated_user,scope='function'),db:Session=Depends(get_db,scope='function')):
    if user.role!='ADMIN':s.fail('Acceso exclusivo para administradores',403)
    return dict(scopes=sorted(s.scopes(db,user)),doctors=[dict(id=d.id,name=d.name,specialty_id=d.specialty_id,modalities=d.modalities,enabled=d.enabled) for d in db.scalars(select(Doctor).order_by(Doctor.name))],specialties=[dict(id=x.id,name=x.name) for x in db.scalars(select(Specialty).order_by(Specialty.name))])


@router.get('/audit-event/{id}')
def audit_detail(id:int,user=Depends(require('audit'),scope='function'),db:Session=Depends(get_db,scope='function')):
    a=s.get(db,AdminEvent,id)
    return dict(id=a.id,actor_id=a.actor_id,action=a.action,resource=a.resource,entity_id=a.entity_id,reason=a.reason,details=a.details,created_at=a.created_at)
