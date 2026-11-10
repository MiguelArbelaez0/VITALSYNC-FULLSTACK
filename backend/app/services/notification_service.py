"""Persistent patient notifications for lifecycle outcomes."""
from app.services.booking import notify


def lifecycle_update(db, patient_id, appointment_code, message):
    notify(db, patient_id, f'Cita {appointment_code}: {message}')
