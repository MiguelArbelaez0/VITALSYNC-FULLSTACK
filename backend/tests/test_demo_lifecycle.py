import pytest
from sqlalchemy import select, func, event
from sqlalchemy.exc import OperationalError
from app import main
from app.db.session import SessionLocal
from app.models.entities import Appointment, VirtualConsultation, StatusHistory, Notification, AuditEvent
from conftest import activate
from test_portal import virtual_slot


def reserve(patient):
    h = patient.post('/api/holds', json={'availability_id': virtual_slot(patient)['id'], 'modality': 'VIRTUAL'})
    assert h.status_code == 201, h.text
    r = patient.post(f"/api/holds/{h.json()['id']}/confirm")
    assert r.status_code == 200, r.text
    return r.json()['id']


def advance(patient, aid, steps):
    for step in steps:
        r = patient.post(f'/api/appointments/{aid}/teleconsult/status', json={'status': step})
        assert r.status_code == 200, r.text


def test_future_completion_is_atomic_persistent_and_excludes_only_completed(patient):
    activate(patient, 'Premium')
    aid, other = reserve(patient), reserve(patient)
    original = patient.get(f'/api/appointments/{aid}').json()['starts_at']
    advance(patient, aid, ['SALA_DISPONIBLE', 'PACIENTE_EN_ESPERA', 'MEDICO_EN_ESPERA', 'EN_ATENCION'])
    detail = patient.get(f'/api/appointments/{aid}').json()
    assert detail['status'] == 'IN_PROGRESS' and detail['virtual_status'] == 'EN_ATENCION'
    advance(patient, aid, ['FINALIZADA'])
    detail = patient.get(f'/api/appointments/{aid}').json()
    assert detail['status'] == 'ATTENDED' and detail['virtual_status'] == 'FINALIZADA'
    assert detail['completion_source'] == 'DEMO' and detail['clinically_attended'] is False
    assert detail['starts_at'] == original and detail['simulated_completed_at'] < original
    assert [a['id'] for a in patient.get('/api/appointments?view=upcoming').json()] == [other]
    assert [a['id'] for a in patient.get('/api/appointments?view=completed').json()] == [aid]
    dashboard = patient.get('/api/dashboard').json()
    assert dashboard['upcoming_count'] == 1 and dashboard['next_appointment']['id'] == other
    notices = patient.get('/api/notifications').json()
    assert sum('Atención simulada finalizada' in n['message'] for n in notices) == 1
    assert patient.post(f'/api/appointments/{aid}/teleconsult/status', json={'status': 'FINALIZADA'}).status_code == 409
    assert len(patient.get('/api/notifications').json()) == len(notices)
    assert patient.post(f'/api/appointments/{aid}/cancel', json={'version': detail['version'], 'reason': 'No cancelar', 'confirmed': True}).status_code == 409
    with SessionLocal() as db:
        a, v = db.get(Appointment, aid), db.get(VirtualConsultation, aid)
        assert a.status == 'ATTENDED' and v.status == 'FINALIZADA'
        assert v.patient_present_at and v.doctor_present_at
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == aid, AuditEvent.action == 'SIMULATED_TELECONSULT_FINALIZADA')) == 1
        history = db.scalars(select(StatusHistory).where(StatusHistory.appointment_id == aid)).all()
        assert len(history) == 8
        assert 'DEMOSTRACIÓN' in history[-1].reason


def test_normal_mode_refuses_patient_simulator_even_with_browser_flag(patient, monkeypatch):
    activate(patient, 'Premium')
    aid = reserve(patient)
    monkeypatch.setattr(main, 'DEMO_MODE', False)
    assert patient.post(f'/api/appointments/{aid}/teleconsult/status', json={'status': 'SALA_DISPONIBLE'}).status_code == 403
    assert patient.get(f'/api/appointments/{aid}').json()['virtual_status'] == 'PROGRAMADA'


@pytest.mark.parametrize('absence', ['PACIENTE_AUSENTE', 'MEDICO_AUSENTE'])
def test_absence_is_terminal_without_completion(patient, absence):
    activate(patient, 'Premium')
    aid = reserve(patient)
    advance(patient, aid, ['SALA_DISPONIBLE', absence])
    detail = patient.get(f'/api/appointments/{aid}').json()
    assert detail['status'] == {'PACIENTE_AUSENTE': 'PATIENT_ABSENT', 'MEDICO_AUSENTE': 'DOCTOR_ABSENT'}[absence]
    assert detail['simulated_completed_at'] is None
    assert patient.get('/api/appointments?view=upcoming').json() == []
    assert patient.get('/api/appointments?view=completed').json() == []
    assert patient.post(f'/api/appointments/{aid}/teleconsult/status', json={'status': 'FINALIZADA'}).status_code == 409


def test_independent_presence_requires_both(patient):
    activate(patient, 'Premium')
    aid = reserve(patient)
    advance(patient, aid, ['SALA_DISPONIBLE', 'MEDICO_EN_ESPERA'])
    assert patient.post(f'/api/appointments/{aid}/teleconsult/status', json={'status': 'EN_ATENCION'}).status_code == 409
    advance(patient, aid, ['PACIENTE_EN_ESPERA'])
    # Both presence records now allow starting, irrespective of arrival order.
    advance(patient, aid, ['EN_ATENCION'])


def test_database_write_failure_rolls_back_all_required_records(patient):
    activate(patient, 'Premium')
    aid = reserve(patient)
    advance(patient, aid, ['SALA_DISPONIBLE', 'PACIENTE_EN_ESPERA', 'MEDICO_EN_ESPERA', 'EN_ATENCION'])
    before = patient.get(f'/api/appointments/{aid}').json()
    notices = patient.get('/api/notifications').json()
    def fail_notification(mapper, connection, target):
        raise OperationalError('INSERT notification', {}, Exception('Injected persistence failure'))
    event.listen(Notification, 'before_insert', fail_notification)
    try:
        result = patient.post(f'/api/appointments/{aid}/teleconsult/status', json={'status': 'FINALIZADA'})
        assert result.status_code == 503
    finally:
        event.remove(Notification, 'before_insert', fail_notification)
    after = patient.get(f'/api/appointments/{aid}').json()
    assert after == before
    assert patient.get('/api/notifications').json() == notices
    advance(patient, aid, ['FINALIZADA'])


def test_single_completion_clears_dashboard_and_technical_error_is_not_attendance(patient):
    activate(patient, 'Premium')
    aid = reserve(patient)
    advance(patient, aid, ['SALA_DISPONIBLE', 'PACIENTE_EN_ESPERA', 'MEDICO_EN_ESPERA', 'EN_ATENCION', 'FINALIZADA'])
    dashboard = patient.get('/api/dashboard').json()
    assert dashboard['upcoming_count'] == 0 and dashboard['next_appointment'] is None
    incident = reserve(patient)
    advance(patient, incident, ['ERROR_TECNICO'])
    detail = patient.get(f'/api/appointments/{incident}').json()
    assert detail['status'] == 'TECHNICAL_ERROR' and detail['completion_source'] is None
    assert patient.post(f'/api/appointments/{incident}/teleconsult/status', json={'status': 'FINALIZADA'}).status_code == 409


def test_concurrent_completion_creates_one_notification_and_one_event(patient):
    from concurrent.futures import ThreadPoolExecutor
    from fastapi.testclient import TestClient
    activate(patient, 'Premium')
    aid = reserve(patient)
    advance(patient, aid, ['SALA_DISPONIBLE', 'PACIENTE_EN_ESPERA', 'MEDICO_EN_ESPERA', 'EN_ATENCION'])
    cookies = dict(patient.cookies)
    def finish(_):
        with TestClient(main.app, cookies=cookies) as client:
            return client.post(f'/api/appointments/{aid}/teleconsult/status', json={'status': 'FINALIZADA'}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(finish, range(2))) == [200, 409]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == aid, AuditEvent.action == 'SIMULATED_TELECONSULT_FINALIZADA')) == 1
        assert db.scalar(select(func.count()).select_from(Notification).where(Notification.message.contains('Atención simulada finalizada'))) == 1
