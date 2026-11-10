"""Exercise the legacy mismatch in a fresh, isolated PostgreSQL schema."""
import os
import subprocess
from uuid import uuid4
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
