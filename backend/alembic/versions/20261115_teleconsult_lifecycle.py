"""Synchronize simulated teleconsultation and appointment lifecycles."""
from alembic import op
import sqlalchemy as sa

revision = '20261115_teleconsult_lifecycle'
down_revision = '20261114_patient_identity'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('appointments', sa.Column('attended_at', sa.DateTime(timezone=True)))
    op.add_column('appointments', sa.Column('incidence_at', sa.DateTime(timezone=True)))
    op.add_column('appointments', sa.Column('incidence_reason', sa.Text()))
    for name, column in [
        ('patient_present', sa.Column('patient_present', sa.Boolean(), nullable=False, server_default=sa.false())),
        ('doctor_present', sa.Column('doctor_present', sa.Boolean(), nullable=False, server_default=sa.false())),
        ('patient_joined_at', sa.Column('patient_joined_at', sa.DateTime(timezone=True))),
        ('doctor_joined_at', sa.Column('doctor_joined_at', sa.DateTime(timezone=True))),
        ('room_opened_at', sa.Column('room_opened_at', sa.DateTime(timezone=True))),
        ('started_at', sa.Column('started_at', sa.DateTime(timezone=True))),
        ('finalized_at', sa.Column('finalized_at', sa.DateTime(timezone=True))),
        ('demo_clock_advanced_at', sa.Column('demo_clock_advanced_at', sa.DateTime(timezone=True))),
        ('resume_status', sa.Column('resume_status', sa.String(24))),
        ('resume_appointment_status', sa.Column('resume_appointment_status', sa.String(24))),
        ('incident_reason', sa.Column('incident_reason', sa.Text())),
        ('incident_at', sa.Column('incident_at', sa.DateTime(timezone=True))),
        ('incident_resolved_at', sa.Column('incident_resolved_at', sa.DateTime(timezone=True))),
    ]:
        op.add_column('virtual_consultations', column)

    op.drop_constraint('appointments_status_check', 'appointments', type_='check')
    op.create_check_constraint('appointments_status_check', 'appointments',
        "status IN ('CONFIRMED','IN_PROGRESS','CANCELLED','ATTENDED','PATIENT_ABSENT','DOCTOR_ABSENT','TECHNICAL_ISSUE')")
    op.drop_constraint('ck_virtual_consultations_status', 'virtual_consultations', type_='check')

    # Translate legacy presentation states while retaining participant presence.
    op.execute("""
        UPDATE virtual_consultations SET
          patient_present = CASE WHEN status IN ('PACIENTE_EN_ESPERA','MEDICO_EN_ESPERA','EN_ATENCION','FINALIZADA') THEN true ELSE false END,
          doctor_present = CASE WHEN status IN ('MEDICO_EN_ESPERA','EN_ATENCION','FINALIZADA') THEN true ELSE false END,
          patient_joined_at = CASE WHEN status IN ('PACIENTE_EN_ESPERA','MEDICO_EN_ESPERA','EN_ATENCION','FINALIZADA') THEN updated_at ELSE NULL END,
          doctor_joined_at = CASE WHEN status IN ('MEDICO_EN_ESPERA','EN_ATENCION','FINALIZADA') THEN updated_at ELSE NULL END,
          room_opened_at = CASE WHEN status <> 'PROGRAMADA' THEN updated_at ELSE NULL END,
          started_at = CASE WHEN status IN ('EN_ATENCION','FINALIZADA') THEN updated_at ELSE NULL END,
          finalized_at = CASE WHEN status = 'FINALIZADA' THEN updated_at ELSE NULL END,
          status = CASE WHEN status IN ('PACIENTE_EN_ESPERA','MEDICO_EN_ESPERA') THEN 'EN_ESPERA' ELSE status END
    """)
    op.create_check_constraint('ck_virtual_consultations_status', 'virtual_consultations',
        "status IN ('PROGRAMADA','SALA_DISPONIBLE','EN_ESPERA','EN_ATENCION','FINALIZADA','PACIENTE_AUSENTE','MEDICO_AUSENTE','ERROR_TECNICO','CANCELADA')")
    op.execute("""
        CREATE TEMP TABLE teleconsult_reconciled_ids ON COMMIT DROP AS
        SELECT a.id FROM appointments a JOIN virtual_consultations v ON v.appointment_id = a.id
        WHERE (v.status = 'EN_ATENCION' AND a.status <> 'IN_PROGRESS')
           OR (v.status = 'FINALIZADA' AND a.status <> 'ATTENDED')
           OR (v.status = 'PACIENTE_AUSENTE' AND a.status <> 'PATIENT_ABSENT')
           OR (v.status = 'MEDICO_AUSENTE' AND a.status <> 'DOCTOR_ABSENT')
           OR (v.status = 'CANCELADA' AND a.status <> 'CANCELLED')
    """)
    # Reconcile each appointment only through its own virtual_consultations PK/FK.
    op.execute("""
        UPDATE appointments a SET status = CASE
          WHEN v.status = 'EN_ATENCION' THEN 'IN_PROGRESS'
          WHEN v.status = 'FINALIZADA' THEN 'ATTENDED'
          WHEN v.status = 'PACIENTE_AUSENTE' THEN 'PATIENT_ABSENT'
          WHEN v.status = 'MEDICO_AUSENTE' THEN 'DOCTOR_ABSENT'
          WHEN v.status = 'CANCELADA' THEN 'CANCELLED'
          ELSE a.status END,
          attended_at = CASE WHEN v.status = 'FINALIZADA' THEN v.updated_at ELSE a.attended_at END,
          incidence_at = CASE WHEN v.status IN ('PACIENTE_AUSENTE','MEDICO_AUSENTE') THEN v.updated_at ELSE a.incidence_at END,
          version = CASE WHEN v.status IN ('EN_ATENCION','FINALIZADA','PACIENTE_AUSENTE','MEDICO_AUSENTE','CANCELADA') AND a.status = 'CONFIRMED' THEN a.version + 1 ELSE a.version END
        FROM virtual_consultations v WHERE v.appointment_id = a.id
    """)
    op.execute("""
        INSERT INTO appointment_status_history (appointment_id, status, author_id, reason, created_at)
        SELECT a.id, a.status, a.patient_id, 'Migración: reconciliación de estado con la teleconsulta vinculada', now()
        FROM appointments a JOIN teleconsult_reconciled_ids r ON r.id = a.id
    """)
    op.execute("""
        INSERT INTO audit_events (actor_id, action, entity_id, created_at)
        SELECT a.patient_id, 'TELECONSULT_LIFECYCLE_RECONCILED', a.id, now()
        FROM appointments a JOIN teleconsult_reconciled_ids r ON r.id = a.id
    """)
    op.execute("ALTER TABLE appointments DROP CONSTRAINT IF EXISTS no_doctor_overlap")
    op.execute("ALTER TABLE appointments DROP CONSTRAINT IF EXISTS no_patient_overlap")
    op.execute("ALTER TABLE appointments ADD CONSTRAINT no_doctor_overlap EXCLUDE USING gist (doctor_id WITH =, tstzrange(starts_at, ends_at, '[)') WITH &&) WHERE (status IN ('CONFIRMED','IN_PROGRESS','TECHNICAL_ISSUE'))")
    op.execute("ALTER TABLE appointments ADD CONSTRAINT no_patient_overlap EXCLUDE USING gist (patient_id WITH =, tstzrange(starts_at, ends_at, '[)') WITH &&) WHERE (status IN ('CONFIRMED','IN_PROGRESS','TECHNICAL_ISSUE'))")


def downgrade():
    op.execute("ALTER TABLE appointments DROP CONSTRAINT IF EXISTS no_patient_overlap")
    op.execute("ALTER TABLE appointments DROP CONSTRAINT IF EXISTS no_doctor_overlap")
    op.execute("ALTER TABLE appointments ADD CONSTRAINT no_doctor_overlap EXCLUDE USING gist (doctor_id WITH =, tstzrange(starts_at, ends_at, '[)') WITH &&) WHERE (status = 'CONFIRMED')")
    op.execute("ALTER TABLE appointments ADD CONSTRAINT no_patient_overlap EXCLUDE USING gist (patient_id WITH =, tstzrange(starts_at, ends_at, '[)') WITH &&) WHERE (status = 'CONFIRMED')")
    op.drop_constraint('ck_virtual_consultations_status', 'virtual_consultations', type_='check')
    op.create_check_constraint('ck_virtual_consultations_status', 'virtual_consultations',
        "status IN ('PROGRAMADA','SALA_DISPONIBLE','PACIENTE_EN_ESPERA','MEDICO_EN_ESPERA','EN_ATENCION','FINALIZADA','PACIENTE_AUSENTE','MEDICO_AUSENTE','CANCELADA')")
    op.drop_constraint('appointments_status_check', 'appointments', type_='check')
    op.create_check_constraint('appointments_status_check', 'appointments', "status IN ('CONFIRMED','CANCELLED','ATTENDED')")
    for name in ('incident_resolved_at','incident_at','incident_reason','resume_appointment_status','resume_status','demo_clock_advanced_at','finalized_at','started_at','room_opened_at','doctor_joined_at','patient_joined_at','doctor_present','patient_present'):
        op.drop_column('virtual_consultations', name)
    for name in ('incidence_reason','incidence_at','attended_at'):
        op.drop_column('appointments', name)
