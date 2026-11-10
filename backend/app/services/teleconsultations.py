"""Compatibility adapter for callers using the original status-based API."""
from app.services import teleconsultation


def transition(db, user, appointment_id, target, demo_mode):
    event = teleconsultation.LEGACY_EVENTS.get(target)
    if not event:
        from fastapi import HTTPException
        raise HTTPException(422, 'Estado de teleconsulta inválido')
    return teleconsultation.apply_event(
        db, user, appointment_id, event, demo_mode=demo_mode, legacy_status=target,
    )
