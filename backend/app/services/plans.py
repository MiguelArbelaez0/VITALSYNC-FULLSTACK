from sqlalchemy import select
from app.models.entities import (
    PatientPlan, PatientPlanCancellation, Plan, Payment, Hold, AuditEvent, now,
)
from app.services.booking import lock_patient, fail, notify


def cancel_subscription(db, user, plan_id):
    """Cancel the patient's active subscription immediately for any plan ID."""
    lock_patient(db, user.id)
    subscription = db.scalar(
        select(PatientPlan)
        .where(PatientPlan.patient_id == user.id, PatientPlan.plan_id == plan_id)
        .with_for_update()
    )
    if not subscription:
        fail('Suscripción no encontrada o no corresponde a tu cuenta', 404)
    if subscription.status != 'ACTIVE' or subscription.expires_at <= now():
        fail('Solo puedes cancelar una suscripción activa y vigente')

    pending_payment = db.scalar(
        select(Payment.id).where(
            Payment.patient_id == user.id,
            Payment.kind == 'PLAN',
            Payment.plan_id == plan_id,
            Payment.status.in_(['PENDING', 'IN_RECONCILIATION']),
        ).limit(1)
    )
    if pending_payment:
        fail('Resuelve el pago pendiente de este plan antes de cancelarlo')

    active_hold = db.scalar(
        select(Hold.id).where(
            Hold.patient_id == user.id,
            Hold.plan_id == plan_id,
            Hold.status == 'ACTIVE',
            Hold.expires_at > now(),
        ).limit(1)
    )
    if active_hold:
        fail('Libera o completa la retención activa antes de cancelar este plan')

    plan = db.get(Plan, plan_id)
    if not plan:
        fail('Plan no encontrado', 404)

    changed_at = now()
    previous_status = subscription.status
    subscription.status = 'INACTIVE'
    subscription.cancelled_at = changed_at
    subscription.cancelled_by = user.id
    db.add(PatientPlanCancellation(
        patient_id=user.id,
        plan_id=plan.id,
        changed_by=user.id,
        previous_status=previous_status,
        new_status=subscription.status,
        policy='IMMEDIATE',
        reason='Cancelación inmediata solicitada y confirmada por el paciente',
        cancelled_at=changed_at,
        effective_at=changed_at,
    ))
    db.add(AuditEvent(actor_id=user.id, action='PATIENT_PLAN_CANCELLED', entity_id=plan.id))
    notify(
        db, user.id,
        f'Cancelaste el plan {plan.name}. La cobertura terminó inmediatamente. '
        'Tus citas, pagos e historial se conservan; no se hizo una devolución automática.'
    )
    return {
        'plan_id': plan.id,
        'plan_name': plan.name,
        'previous_status': previous_status,
        'status': subscription.status,
        'policy': 'IMMEDIATE',
        'cancelled_at': changed_at,
        'effective_at': changed_at,
        'message': 'El plan se canceló y la cobertura terminó inmediatamente.',
    }
