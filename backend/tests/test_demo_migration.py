"""Exercise the legacy mismatch in a fresh, isolated PostgreSQL schema."""
import os
import subprocess
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, text
from app.db.session import engine


def test_upgrade_repairs_legacy_finalized_room_without_changing_scheduled_date():
    schema = 'lifecycle_migration_' + uuid4().hex
    assert engine.url.database == 'vitalsync_test'
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        # Shadow the public version table before Alembic inspects search_path.
        connection.execute(text(f'CREATE TABLE "{schema}".alembic_version (version_num varchar(32) PRIMARY KEY)'))
    url = engine.url.set(query={'options': f'-csearch_path={schema},public'})
    isolated = create_engine(url)
    environment = {**os.environ, 'DATABASE_URL': url.render_as_string(hide_password=False)}
    try:
        subprocess.run(['alembic', 'upgrade', '20261114_patient_identity'], env=environment, check=True, capture_output=True)
        subprocess.run(['python', '-m', 'app.seed'], env=environment, check=True, capture_output=True)
        with isolated.begin() as connection:
            assert connection.scalar(text('SELECT current_schema()')) == schema
            assert connection.scalar(text("SELECT to_regclass('appointments')::oid = to_regclass(:table)::oid"), {'table': schema + '.appointments'})
            aid = connection.scalar(text("""WITH h AS (
                INSERT INTO appointment_holds (patient_id,doctor_id,availability_id,plan_id,starts_at,ends_at,expires_at,copay,modality,status)
                SELECT 2,doctor_id,id,3,starts_at,ends_at,now()+interval '10 minutes',0,'VIRTUAL','CONFIRMED'
                FROM doctor_availability ORDER BY starts_at,id LIMIT 1 RETURNING *
            ) INSERT INTO appointments (code,patient_id,doctor_id,hold_id,plan_id,starts_at,ends_at,copay,modality,status,version,economic_review)
                SELECT 'VS-MIGRATION',patient_id,doctor_id,id,plan_id,starts_at,ends_at,0,'VIRTUAL','CONFIRMED',1,false FROM h RETURNING id"""))
            connection.execute(text("""INSERT INTO virtual_consultations (appointment_id,patient_id,doctor_id,status,updated_at)
                SELECT id,patient_id,doctor_id,'FINALIZADA',now() FROM appointments WHERE id=:id"""), {'id': aid})
            scheduled = connection.scalar(text('SELECT starts_at FROM appointments WHERE id=:id'), {'id': aid})
        subprocess.run(['alembic', 'upgrade', 'head'], env=environment, check=True, capture_output=True)
        # Running upgrade a second time must not repeat repairs or notifications.
        subprocess.run(['alembic', 'upgrade', 'head'], env=environment, check=True, capture_output=True)
        with isolated.connect() as connection:
            row = connection.execute(text('SELECT * FROM appointments WHERE id=:id'), {'id': aid}).mappings().one()
            assert row['status'] == 'ATTENDED' and row['completion_source'] == 'DEMO'
            assert row['starts_at'] == scheduled and row['simulated_completed_at'] < scheduled
            assert row['clinically_attended'] is False
            assert connection.scalar(text("SELECT count(*) FROM notifications WHERE message LIKE '%registro recuperado%'")) == 1
            assert connection.scalar(text("SELECT count(*) FROM audit_events WHERE action='DEMO_LIFECYCLE_REPAIRED'")) == 1
    finally:
        isolated.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


@pytest.mark.parametrize('branch_head', [
    '20261115_teleconsult_lifecycle',
    '20261116_demo_metadata',
])
def test_each_divergent_branch_upgrades_to_the_single_merge_head(branch_head):
    schema = 'lifecycle_branch_' + uuid4().hex
    assert engine.url.database == 'vitalsync_test'
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'CREATE TABLE "{schema}".alembic_version (version_num varchar(32) PRIMARY KEY)'))
    url = engine.url.set(query={'options': f'-csearch_path={schema},public'})
    isolated = create_engine(url)
    environment = {**os.environ, 'DATABASE_URL': url.render_as_string(hide_password=False)}
    try:
        subprocess.run(['alembic', 'upgrade', '20261114_patient_identity'], env=environment, check=True, capture_output=True)
        subprocess.run(['python', '-m', 'app.seed'], env=environment, check=True, capture_output=True)
        for step, target in enumerate((branch_head, 'head', 'head')):
            if step == 1:
                with isolated.begin() as connection:
                    patient_id = connection.scalar(text("SELECT id FROM users WHERE role='PATIENT' ORDER BY id LIMIT 1"))
                    doctor_id = connection.scalar(text('SELECT id FROM doctors ORDER BY id LIMIT 1'))
                    plan_id = connection.scalar(text("SELECT id FROM plans WHERE name='Premium'"))
                    slot = connection.execute(text("""
                        SELECT id,starts_at,ends_at FROM doctor_availability
                        WHERE doctor_id=:doctor_id AND modalities ? 'VIRTUAL' AND starts_at > now()
                        ORDER BY starts_at LIMIT 1
                    """), {'doctor_id': doctor_id}).mappings().one()
                    hold_id = connection.scalar(text("""
                        INSERT INTO appointment_holds (patient_id,doctor_id,availability_id,plan_id,starts_at,ends_at,expires_at,copay,modality,status)
                        VALUES (:patient_id,:doctor_id,:availability_id,:plan_id,:starts_at,:ends_at,now()+interval '10 minutes',0,'VIRTUAL','CONFIRMED') RETURNING id
                    """), {'patient_id': patient_id, 'doctor_id': doctor_id, 'availability_id': slot['id'], 'plan_id': plan_id, 'starts_at': slot['starts_at'], 'ends_at': slot['ends_at']})
                    appointment_id = connection.scalar(text("""
                        INSERT INTO appointments (code,patient_id,doctor_id,hold_id,plan_id,starts_at,ends_at,copay,modality,status,version,economic_review)
                        VALUES (:code,:patient_id,:doctor_id,:hold_id,:plan_id,:starts_at,:ends_at,0,'VIRTUAL','CONFIRMED',1,false) RETURNING id
                    """), {'code': f'VS-BRANCH-{uuid4().hex[:8]}', 'patient_id': patient_id, 'doctor_id': doctor_id, 'hold_id': hold_id, 'plan_id': plan_id, 'starts_at': slot['starts_at'], 'ends_at': slot['ends_at']})
                    connection.execute(text("INSERT INTO virtual_consultations (appointment_id,patient_id,doctor_id,status,updated_at) VALUES (:id,:patient_id,:doctor_id,'FINALIZADA',now())"), {'id': appointment_id, 'patient_id': patient_id, 'doctor_id': doctor_id})
            result = subprocess.run(['alembic', 'upgrade', target], env=environment, capture_output=True, text=True)
            assert result.returncode == 0, f'alembic upgrade {target} failed:\n{result.stdout}\n{result.stderr}'
        with isolated.connect() as connection:
            revisions = connection.execute(text('SELECT version_num FROM alembic_version')).scalars().all()
            assert revisions == ['20261120_admin_portal']
            repaired = connection.execute(text('SELECT status,completion_source,simulated_completed_at,starts_at FROM appointments WHERE id=:id'), {'id': appointment_id}).mappings().one()
            assert repaired['status'] == 'ATTENDED' and repaired['completion_source'] == 'DEMO'
            assert repaired['simulated_completed_at'] < repaired['starts_at']
            assert connection.scalar(text("SELECT count(*) FROM notifications WHERE message LIKE :code AND message ILIKE '%finalizada%'"), {'code': f'%VS-BRANCH-%'}) == 1
            assert connection.scalar(text("SELECT count(*) FROM audit_events WHERE entity_id=:id AND action='DEMO_LIFECYCLE_REPAIRED'"), {'id': appointment_id}) == 1
    finally:
        isolated.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
