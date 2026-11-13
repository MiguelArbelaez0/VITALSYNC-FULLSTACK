"""Administrative operations. All projections are explicit allowlists, never clinical models."""
from datetime import datetime,timedelta,time
from zoneinfo import ZoneInfo
from sqlalchemy import select,func,text,delete,or_,and_
from fastapi import HTTPException
from app.models.entities import (User,Patient,Doctor,DoctorAccount,DoctorCredentialState,Specialty,Plan,PlanRule,PlanRevision,PatientPlan,SubscriptionTerms,Payment,PaymentTerms,Hold,Appointment,Availability,DoctorBlock,BlockRelease,StatusHistory,Notification,AuditEvent,AdminEvent,AdminPermission,RecoveryRequest,RefundRequest,RefundTransition,AppointmentReschedule,AppSetting,SessionToken,now)
from app.core.security import passwords
from app.services import booking,payments,doctor_portal,plan_terms
import secrets

SCOPES=('dashboard','doctors','patients','appointments','availability','plans','payments','refunds','audit','settings','accounts')
ACTIVE=('CONFIRMED','IN_PROGRESS','TECHNICAL_ERROR')
BOGOTA=ZoneInfo('America/Bogota')

def fail(message,code=409):raise HTTPException(code,message)
def get(db,model,id,lock=False):
    row=db.scalar(select(model).where(model.id==id).with_for_update().execution_options(populate_existing=True)) if lock else db.get(model,id)
    if not row:fail('Registro no encontrado',404)
    return row

def audit(db,actor,action,resource,id=None,reason='Consulta administrativa',details=None):
    db.add(AdminEvent(actor_id=actor.id if actor else None,action=action,resource=resource,entity_id=id,reason=reason,details=details or {}))
    db.flush()

def scopes(db,user):
    grant=db.get(AdminPermission,user.id)
    return set(grant.scopes) if grant else set(SCOPES)

def validate_scopes(db,actor,values):
    if len(values)!=len(set(values)) or not set(values)<=set(SCOPES):fail('Permisos administrativos inválidos',422)
    if not set(values)<=scopes(db,actor):fail('No puedes conceder permisos superiores a los propios',403)

def page(db,query,project,page=1,size=20):
    total=db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    rows=db.execute(query.offset((page-1)*size).limit(size)).all()
    return dict(items=[project(*row) for row in rows],total=total,page=page,pages=max(1,(total+size-1)//size))

def like(value):return '%'+value.replace('%','').replace('_','')+'%'
def user_dict(u):return dict(id=u.id,name=u.name,email=u.email,role=u.role,status=u.status,created_at=u.created_at)
def doctor_dict(db,d):
    link=db.scalar(select(DoctorAccount).where(DoctorAccount.doctor_id==d.id))
    u=db.get(User,link.user_id) if link else None
    return dict(id=d.id,name=d.name,specialty_id=d.specialty_id,specialty=db.get(Specialty,d.specialty_id).name,bio=d.bio,modalities=d.modalities,enabled=d.enabled,email=u.email if u else None,user_id=u.id if u else None,account_status=u.status if u else 'UNLINKED',active_appointments=db.scalar(select(func.count()).select_from(Appointment).where(Appointment.doctor_id==d.id,Appointment.status.in_(ACTIVE))),appointments_total=db.scalar(select(func.count()).select_from(Appointment).where(Appointment.doctor_id==d.id)))

def patient_dict(u,p):
    return dict(**user_dict(u),document_type=p.document_type,document_masked=('•'*max(0,len(p.document_number)-4)+p.document_number[-4:]) if p.document_number else None)

def appointment_dict(db,a):
    d=db.get(Doctor,a.doctor_id);snap=a.snapshot.terms if a.snapshot else {}
    replacement=db.scalar(select(AppointmentReschedule).where(or_(AppointmentReschedule.previous_id==a.id,AppointmentReschedule.replacement_id==a.id)))
    return dict(id=a.id,code=a.code,patient_id=a.patient_id,patient=db.get(User,a.patient_id).name,doctor_id=a.doctor_id,doctor=snap.get('doctor',d.name),specialty_id=d.specialty_id,specialty=snap.get('specialty',db.get(Specialty,d.specialty_id).name),plan_id=a.plan_id,plan=snap.get('plan',db.get(Plan,a.plan_id).name),starts_at=a.starts_at,ends_at=a.ends_at,modality=a.modality,status=a.status,version=a.version,copay=a.copay,payment_id=a.payment_id,cancellation_reason=a.cancellation_reason,cancelled_by=a.cancelled_by,completion_source=a.completion_source,clinically_attended=a.clinically_attended,reschedule=dict(previous_id=replacement.previous_id,replacement_id=replacement.replacement_id,reason=replacement.reason) if replacement else None)

def request_recovery(db,actor,user,reason):
    # The user lock serializes duplicate requests; password hashes remain untouched.
    get(db,User,user.id,True)
    if user.status!='ACTIVE':fail('Activa la cuenta antes de solicitar recuperación')
    request=db.scalar(select(RecoveryRequest).where(RecoveryRequest.user_id==user.id,RecoveryRequest.status.in_(['PENDING','ISSUED'])).order_by(RecoveryRequest.id.desc()))
    if request and (request.status=='PENDING' or request.expires_at>now()):return request
    row=RecoveryRequest(user_id=user.id,requested_by=actor.id,reason=reason)
    db.add(row);db.flush();audit(db,actor,'ACCESS_RECOVERY_REQUESTED','account',user.id,reason,{'request_id':row.id})
    return row

def create_doctor(db,actor,data):
    db.execute(text('SELECT pg_advisory_xact_lock(861995)'))
    get(db,Specialty,data.specialty_id)
    if db.scalar(select(User.id).where(func.lower(User.email)==str(data.email).lower())):fail('El correo ya pertenece a una cuenta')
    if db.scalar(select(Doctor.id).where(func.lower(Doctor.name)==data.name.lower())):fail('Ya existe un profesional con ese nombre')
    d=Doctor(**data.model_dump(exclude={'reason','email'}));db.add(d);db.flush()
    u=User(email=str(data.email).lower(),name=d.name,role='DOCTOR',status='ACTIVE' if d.enabled else 'DISABLED',password_hash=passwords.hash(secrets.token_urlsafe(48)))
    db.add(u);db.flush();db.add(DoctorAccount(user_id=u.id,doctor_id=d.id));db.flush();db.add(DoctorCredentialState(user_id=u.id,must_change_password=True))
    if d.enabled:request_recovery(db,actor,u,'Primer acceso individual del profesional: '+data.reason)
    audit(db,actor,'ADMIN_DOCTOR_CREATED','doctor',d.id,data.reason,{'user_id':u.id,'enabled':d.enabled})
    return doctor_dict(db,d)

def affected(db,doctor_id=None,patient_id=None):
    field=Appointment.doctor_id if doctor_id else Appointment.patient_id
    value=doctor_id or patient_id
    rows=db.scalars(select(Appointment).where(field==value,Appointment.status.in_(ACTIVE),or_(Appointment.ends_at>now(),Appointment.status.in_(['IN_PROGRESS','TECHNICAL_ERROR']))).order_by(Appointment.id)).all()
    holds=db.scalar(select(func.count()).select_from(Hold).where((Hold.doctor_id if doctor_id else Hold.patient_id)==value,Hold.status=='ACTIVE',Hold.expires_at>now()))
    return rows,holds

def no_affected(db,doctor_id=None,patient_id=None):
    rows,holds=affected(db,doctor_id,patient_id)
    if rows or holds:fail('Primero resuelve las citas activas '+', '.join(a.code for a in rows[:20])+f' y las {holds} retenciones pendientes. Cancela con motivo o completa una nueva reserva y registra su reprogramación; no se desactiva una cuenta con atención pendiente.')

def update_doctor(db,actor,id,data):
    d=get(db,Doctor,id,True);get(db,Specialty,data.specialty_id)
    if db.scalar(select(Doctor.id).where(func.lower(Doctor.name)==data.name.lower(),Doctor.id!=id)):fail('Nombre profesional duplicado')
    if d.enabled and not data.enabled:no_affected(db,doctor_id=id)
    # A modality/specialty change cannot strand future reservations or holds.
    if d.specialty_id!=data.specialty_id or not set(d.modalities)<=set(data.modalities):no_affected(db,doctor_id=id)
    before={k:getattr(d,k) for k in ['name','specialty_id','modalities','enabled']}
    for k,v in data.model_dump(exclude={'reason'}).items():setattr(d,k,v)
    link=db.scalar(select(DoctorAccount).where(DoctorAccount.doctor_id==id))
    if link:
        u=get(db,User,link.user_id,True);u.name=d.name;u.status='ACTIVE' if d.enabled else 'DISABLED'
        if not d.enabled:db.execute(delete(SessionToken).where(SessionToken.user_id==u.id))
    audit(db,actor,'ADMIN_DOCTOR_UPDATED','doctor',id,data.reason,{'before':before,'after':{k:getattr(d,k) for k in before}})
    return doctor_dict(db,d)

def set_account(db,actor,id,data):
    db.execute(text('SELECT pg_advisory_xact_lock(861996)'))
    u=get(db,User,id)
    if id==actor.id:fail('No puedes desactivar tu propia cuenta administrativa')
    if u.role=='PATIENT':
        booking.lock_patient(db,id)
        if data.status=='DISABLED':no_affected(db,patient_id=id)
    if u.role=='DOCTOR':
        link=db.scalar(select(DoctorAccount).where(DoctorAccount.user_id==id))
        if not link:fail('Revisa primero la vinculación profesional')
        d=get(db,Doctor,link.doctor_id,True)
        if data.status=='DISABLED':no_affected(db,doctor_id=d.id)
        d.enabled=data.status=='ACTIVE'
    if u.role=='ADMIN' and not scopes(db,u)<=scopes(db,actor):fail('No puedes administrar permisos superiores a los tuyos',403)
    if u.role=='ADMIN' and data.status=='DISABLED':ensure_owner_remains(db,id)
    u=get(db,User,id,True);old=u.status;u.status=data.status
    if data.status=='DISABLED':db.execute(delete(SessionToken).where(SessionToken.user_id==id))
    audit(db,actor,'ADMIN_ACCOUNT_STATUS','account',id,data.reason,{'before':old,'after':u.status,'role':u.role})
    return user_dict(u)

def ensure_owner_remains(db,excluding):
    others=db.scalars(select(User).where(User.role=='ADMIN',User.status=='ACTIVE',User.id!=excluding)).all()
    if not any(scopes(db,u)==set(SCOPES) for u in others):fail('Debe conservarse al menos un administrador activo con todos los permisos')

def save_plan(db,actor,data,id=None):
    db.execute(text('SELECT pg_advisory_xact_lock(861997)'))
    found=set(db.scalars(select(Specialty.id).where(Specialty.id.in_(data.specialty_ids))))
    if found!=set(data.specialty_ids):fail('Hay especialidades inexistentes',422)
    if db.scalar(select(Plan.id).where(func.lower(Plan.name)==data.name.lower(),Plan.id!=(id or 0))):fail('Ya existe un plan con ese nombre')
    p=get(db,Plan,id,True) if id else Plan()
    old=plan_terms.catalog(db,p) if id else None
    rule=db.get(PlanRule,id) if id else None
    if rule and data.version!=rule.version:fail('El plan fue editado por otra sesión. Actualiza antes de guardar')
    for k in ['name','description','price','duration_days','copay','specialty_ids','modalities','enabled']:setattr(p,k,getattr(data,k))
    if not id:db.add(p);db.flush()
    if not rule:rule=PlanRule(plan_id=p.id,version=1);db.add(rule)
    elif id:rule.version+=1
    for k in ['virtual_copay','onsite_copay','consultation_limit','benefits','restrictions']:setattr(rule,k,getattr(data,k))
    db.flush();current=plan_terms.catalog(db,p)
    db.add(PlanRevision(plan_id=p.id,version=rule.version,terms=current,actor_id=actor.id,reason=data.reason))
    audit(db,actor,'ADMIN_PLAN_UPDATED' if id else 'ADMIN_PLAN_CREATED','plan',p.id,data.reason,{'before':old,'after':current,'policy':'Existing subscriptions keep purchased conditions; renewal purchases current catalogue'})
    return current

def slot_dict(db,s):return dict(id=s.id,doctor_id=s.doctor_id,doctor=db.get(Doctor,s.doctor_id).name,starts_at=s.starts_at,ends_at=s.ends_at,modalities=s.modalities,published=s.published)

def no_booking_overlap(db,doctor_id,start,end):
    appointments=db.scalars(select(Appointment).where(Appointment.doctor_id==doctor_id,Appointment.status.in_(ACTIVE),booking.overlaps(Appointment,start,end))).all()
    hold=db.scalar(select(Hold.id).where(Hold.doctor_id==doctor_id,Hold.status=='ACTIVE',Hold.expires_at>now(),booking.overlaps(Hold,start,end)).limit(1))
    if appointments or hold:fail('El horario afecta citas o retenciones activas: '+', '.join(a.code for a in appointments[:20])+'. Resuélvelas primero; no se modificaron sus fechas.')

def save_slot(db,actor,data,id=None):
    d=get(db,Doctor,data.doctor_id,True)
    if not d.enabled or not set(data.modalities)<=set(d.modalities):fail('Médico inactivo o modalidad fuera de su oferta')
    if data.starts_at<=now():fail('Solo se publican o modifican horarios futuros')
    s=get(db,Availability,id,True) if id else None
    if s and s.doctor_id!=data.doctor_id:fail('No se puede trasladar un turno a otro profesional')
    if s:
        if s.starts_at<=now():fail('No se modifica disponibilidad histórica')
        no_booking_overlap(db,d.id,s.starts_at,s.ends_at)
    no_booking_overlap(db,d.id,data.starts_at,data.ends_at)
    if data.published:
        conflict=db.scalar(select(Availability.id).where(Availability.doctor_id==d.id,Availability.id!=(id or 0),Availability.published,booking.overlaps(Availability,data.starts_at,data.ends_at)).limit(1))
        if conflict:fail('La jornada se solapa con un horario publicado')
        blocked=db.scalar(select(DoctorBlock.id).where(DoctorBlock.doctor_id==d.id,~DoctorBlock.id.in_(select(BlockRelease.block_id)),booking.overlaps(DoctorBlock,data.starts_at,data.ends_at)).limit(1))
        if blocked:fail('El intervalo está bloqueado')
    if not s:s=Availability(published_by=actor.id);db.add(s)
    for k,v in data.model_dump(exclude={'reason'}).items():setattr(s,k,v)
    db.flush();audit(db,actor,'ADMIN_AVAILABILITY_UPDATED' if id else 'ADMIN_AVAILABILITY_CREATED','availability',s.id,data.reason,{'doctor_id':d.id,'published':s.published,'starts_at':s.starts_at.isoformat(),'ends_at':s.ends_at.isoformat()})
    return slot_dict(db,s)

def publish_schedule(db,actor,data):
    from app.schemas.admin import SlotInput
    day=data.first_day;result=[]
    while day<=data.last_day:
        if day.weekday() in data.weekdays:
            start=datetime.combine(day,data.start_time,tzinfo=BOGOTA);end=datetime.combine(day,data.end_time,tzinfo=BOGOTA)
            while start+timedelta(minutes=data.minutes)<=end:
                result.append(save_slot(db,actor,SlotInput(doctor_id=data.doctor_id,starts_at=start,ends_at=start+timedelta(minutes=data.minutes),modalities=data.modalities,published=data.published,reason=data.reason)))
                start+=timedelta(minutes=data.minutes)
        day+=timedelta(days=1)
    if not result:fail('La jornada no contiene ningún turno completo',422)
    return dict(created=len(result),items=result)

def block(db,actor,data):
    get(db,Doctor,data.doctor_id,True)
    if data.starts_at<=now():fail('Los bloqueos nuevos deben ser futuros')
    no_booking_overlap(db,data.doctor_id,data.starts_at,data.ends_at)
    if db.scalar(select(DoctorBlock.id).where(DoctorBlock.doctor_id==data.doctor_id,~DoctorBlock.id.in_(select(BlockRelease.block_id)),booking.overlaps(DoctorBlock,data.starts_at,data.ends_at)).limit(1)):fail('Ya existe un bloqueo en ese intervalo')
    b=DoctorBlock(**data.model_dump());db.add(b);db.flush();audit(db,actor,'ADMIN_DATE_BLOCKED','block',b.id,data.reason,{'doctor_id':b.doctor_id})
    return dict(id=b.id,doctor_id=b.doctor_id,starts_at=b.starts_at,ends_at=b.ends_at,reason=b.reason,released=False)

def reschedule(db,actor,id,data):
    old=get(db,Appointment,id);booking.lock_patient(db,old.patient_id)
    old=get(db,Appointment,id,True);replacement=get(db,Appointment,data.replacement_id,True)
    if old.patient_id!=replacement.patient_id or old.id==replacement.id:fail('La nueva reserva debe ser otra cita del mismo paciente')
    if old.status!='CANCELLED' or replacement.status!='CONFIRMED' or replacement.starts_at<=now():fail('Reprograma una cita cancelada hacia una reserva nueva confirmada y futura')
    if db.scalar(select(AppointmentReschedule.id).where(or_(AppointmentReschedule.previous_id==id,AppointmentReschedule.replacement_id==replacement.id))):fail('La reprogramación ya está registrada')
    row=AppointmentReschedule(previous_id=id,replacement_id=replacement.id,actor_id=actor.id,reason=data.reason);db.add(row)
    audit(db,actor,'ADMIN_APPOINTMENT_RESCHEDULED','appointment',id,data.reason,{'replacement_id':replacement.id})
    booking.notify(db,old.patient_id,f'Se registró la reprogramación de {old.code} a {replacement.code}. Ambas reservas y sus condiciones económicas se conservan.')
    return appointment_dict(db,replacement)

REFUND_NEXT={'REQUESTED':['REVIEWING'],'REVIEWING':['APPROVED','REJECTED'],'APPROVED':['AUTHORIZED'],'AUTHORIZED':['PROCESSED','FAILED']}

def refund_dict(db,r):
    p=db.get(Payment,r.payment_id)
    return dict(id=r.id,payment_id=r.payment_id,patient_id=p.patient_id,patient=db.get(User,p.patient_id).name,amount=r.amount,status=r.status,version=r.version,reason=r.reason,created_at=r.created_at,available_actions=REFUND_NEXT.get(r.status,[]))

def refund_eligible(db,p):
    if p.status!='APPROVED' or p.amount<=0:fail('Solo se revisan devoluciones de pagos aprobados con importe positivo')
    if p.kind=='PLAN':
        pp=db.get(PatientPlan,p.patient_id)
        if pp and pp.plan_id==p.plan_id and pp.status=='ACTIVE' and pp.expires_at>now():fail('Cancela la suscripción antes de solicitar devolución; no se retira cobertura automáticamente')
    else:
        a=db.scalar(select(Appointment).where(Appointment.hold_id==p.hold_id))
        if not a or a.status!='CANCELLED':fail('El copago requiere una cita cancelada antes de solicitar devolución')

def create_refund(db,actor,data):
    candidate=get(db,Payment,data.payment_id)
    booking.lock_patient(db,candidate.patient_id)
    p=get(db,Payment,data.payment_id,True)
    previous=db.scalar(select(RefundTransition).where(RefundTransition.operation_key==data.operation_key))
    if previous:
        r=db.get(RefundRequest,previous.refund_id)
        if r.payment_id!=p.id:fail('La clave ya corresponde a otra solicitud')
        return refund_dict(db,r)
    if db.scalar(select(RefundRequest.id).where(RefundRequest.payment_id==p.id)):fail('Ya existe una solicitud para este pago; consulta su historial')
    refund_eligible(db,p)
    r=RefundRequest(payment_id=p.id,amount=p.amount,requested_by=actor.id,reason=data.reason);db.add(r);db.flush()
    db.add(RefundTransition(refund_id=r.id,actor_id=actor.id,status='REQUESTED',reason=data.reason,operation_key=data.operation_key))
    audit(db,actor,'ADMIN_REFUND_REQUESTED','refund',r.id,data.reason,{'payment_id':p.id,'amount':p.amount})
    return refund_dict(db,r)

def transition_refund(db,actor,id,data):
    candidate=get(db,RefundRequest,id)
    payment=get(db,Payment,candidate.payment_id)
    booking.lock_patient(db,payment.patient_id)
    get(db,Payment,payment.id,True)
    r=get(db,RefundRequest,id,True)
    existing=db.scalar(select(RefundTransition).where(RefundTransition.operation_key==data.operation_key))
    if existing:
        if existing.refund_id!=r.id or existing.status!=data.status:fail('La clave corresponde a otra operación')
        return refund_dict(db,r)
    if data.version!=r.version:fail('La devolución cambió. Actualiza antes de continuar')
    if data.status not in REFUND_NEXT.get(r.status,[]):fail('Transición de devolución no permitida')
    if data.status in ['AUTHORIZED','PROCESSED']:refund_eligible(db,db.get(Payment,r.payment_id))
    before=r.status;r.status=data.status;r.version+=1
    db.add(RefundTransition(refund_id=r.id,actor_id=actor.id,previous_status=before,status=r.status,reason=data.reason,operation_key=data.operation_key))
    audit(db,actor,'ADMIN_REFUND_'+r.status,'refund',r.id,data.reason,{'before':before,'after':r.status,'amount':r.amount})
    if r.status in ['PROCESSED','REJECTED','FAILED']:
        p=db.get(Payment,r.payment_id);booking.notify(db,p.patient_id,f'La solicitud de devolución simulada #{r.id} quedó en estado {r.status}. Motivo: {data.reason}. No se efectuó una transferencia real.')
    return refund_dict(db,r)
