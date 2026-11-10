"""Participant attendance facts and presentation state for a consultation."""
from app.models.entities import now


def register_patient(vc, timestamp=None):
    vc.patient_present = True
    vc.patient_joined_at = timestamp or now()
    vc.patient_present_at = vc.patient_joined_at
    if vc.status == 'SALA_DISPONIBLE':
        vc.status = 'EN_ESPERA'


def register_doctor(vc, timestamp=None):
    vc.doctor_present = True
    vc.doctor_joined_at = timestamp or now()
    vc.doctor_present_at = vc.doctor_joined_at
    if vc.status == 'SALA_DISPONIBLE':
        vc.status = 'EN_ESPERA'


def display_status(vc):
    if vc.status != 'EN_ESPERA':
        return vc.status
    if vc.patient_present and vc.doctor_present:
        return 'AMBOS_PRESENTES'
    return 'PACIENTE_EN_ESPERA' if vc.patient_present else 'MEDICO_EN_ESPERA'
