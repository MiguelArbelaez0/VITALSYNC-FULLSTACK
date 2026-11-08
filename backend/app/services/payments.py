from datetime import timedelta
from sqlalchemy import select
from app.models.entities import Payment, Plan, PatientPlan, now, AuditEvent
from app.services.booking import lock_patient, owned_hold, valid_hold, fail, notify

def apply_approved(db, user, payment):
    if payment.kind == 'PLAN':
        plan = db.get(Plan, payment.plan_id)
        pp = db.get(PatientPlan, user.id)
        base = now()
        if pp and pp.plan_id == plan.id and pp.status == 'ACTIVE' and pp.expires_at > base:
            base = pp.expires_at
        if not pp:
            pp = PatientPlan(patient_id=user.id, plan_id=plan.id, expires_at=base)
            db.add(pp)
        pp.plan_id = plan.id
        pp.status = 'ACTIVE'
        pp.expires_at = base + timedelta(days=plan.duration_days)
        notify(db, user.id, f'Tu plan {plan.name} está activo. Pago simulado aprobado.')

def pay(db, user, data):
    lock_patient(db, user.id)
    old = db.scalar(select(Payment).where(Payment.idempotency_key == data.idempotency_key))
    if old:
        target = old.plan_id if old.kind == 'PLAN' else old.hold_id
        if old.patient_id != user.id or old.kind != data.kind or target != data.target_id:
            fail('La clave de transacción ya está asociada a otra operación')
        return old
    query = select(Payment).where(Payment.patient_id == user.id)
    if data.kind == 'PLAN':
        plan = db.get(Plan, data.target_id)
        if not plan or not plan.enabled:
            fail('Plan no disponible', 404)
        query = query.where(Payment.kind == 'PLAN', Payment.plan_id == plan.id, Payment.status.in_(['PENDING', 'IN_RECONCILIATION']))
        amount = plan.price
    else:
        h = owned_hold(db, user, data.target_id)
        valid_hold(db, user, h)
        if not h.copay:
            fail('Esta cita no requiere copago')
        query = query.where(Payment.hold_id == h.id, Payment.status.in_(['PENDING', 'IN_RECONCILIATION', 'APPROVED']))
        amount = h.copay
    if db.scalar(query):
        fail('Ya existe un pago aprobado o pendiente. Consulta o concilia la operación antes de reintentar')
    payment = Payment(patient_id=user.id, kind=data.kind, plan_id=data.target_id if data.kind == 'PLAN' else None, hold_id=data.target_id if data.kind == 'COPAY' else None, amount=amount, status=data.status, idempotency_key=data.idempotency_key)
    db.add(payment)
    db.flush()
    if payment.status == 'APPROVED':
        apply_approved(db, user, payment)
    db.add(AuditEvent(actor_id=user.id, action='SIMULATED_PAYMENT_' + payment.status, entity_id=payment.id))
    return payment

def reconcile(db, user, payment_id, status):
    lock_patient(db, user.id)
    p = db.get(Payment, payment_id)
    if not p or p.patient_id != user.id:
        fail('Pago no encontrado', 404)
    if p.status in ['APPROVED', 'REJECTED']:
        if p.status != status:
            fail('Este pago ya tiene un resultado definitivo')
        return p
    if p.kind == 'COPAY' and status == 'APPROVED':
        valid_hold(db, user, owned_hold(db, user, p.hold_id))
    if p.kind == 'PLAN' and status == 'APPROVED' and not db.get(Plan, p.plan_id).enabled:
        fail('El plan ya no está disponible')
    p.status = status
    if status == 'APPROVED':
        apply_approved(db, user, p)
    db.add(AuditEvent(actor_id=user.id, action='PAYMENT_RECONCILED_' + status, entity_id=p.id))
    return p
