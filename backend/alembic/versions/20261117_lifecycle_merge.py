"""Merge patient portal and simulated teleconsultation lifecycle histories."""
from alembic import op
import sqlalchemy as sa

revision = '20261117_lifecycle_merge'
down_revision = ('20261115_teleconsult_lifecycle', '20261116_demo_metadata')
branch_labels = None
depends_on = None


def _add_column_if_missing(table, column):
    if column.name not in {item['name'] for item in sa.inspect(op.get_bind()).get_columns(table)}:
        op.add_column(table, column)


def upgrade():
    # The local and published branches introduced complementary fields. Make this
    # mergepoint safe from either upgrade path and for databases at either head.
    for column in (
        sa.Column('completion_source', sa.String(8)),
        sa.Column('simulated_completed_at', sa.DateTime(timezone=True)),
        sa.Column('clinically_attended', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('attended_at', sa.DateTime(timezone=True)),
        sa.Column('incidence_at', sa.DateTime(timezone=True)),
        sa.Column('incidence_reason', sa.Text()),
    ):
        _add_column_if_missing('appointments', column)
    for column in (
        sa.Column('patient_present_at', sa.DateTime(timezone=True)),
        sa.Column('doctor_present_at', sa.DateTime(timezone=True)),
        sa.Column('patient_present', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('doctor_present', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('patient_joined_at', sa.DateTime(timezone=True)),
        sa.Column('doctor_joined_at', sa.DateTime(timezone=True)),
        sa.Column('room_opened_at', sa.DateTime(timezone=True)),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('finalized_at', sa.DateTime(timezone=True)),
        sa.Column('demo_clock_advanced_at', sa.DateTime(timezone=True)),
        sa.Column('resume_status', sa.String(24)),
        sa.Column('resume_appointment_status', sa.String(24)),
        sa.Column('incident_reason', sa.Text()),
        sa.Column('incident_at', sa.DateTime(timezone=True)),
        sa.Column('incident_resolved_at', sa.DateTime(timezone=True)),
    ):
        _add_column_if_missing('virtual_consultations', column)

    bind = op.get_bind()
    for check in sa.inspect(bind).get_check_constraints('appointments'):
        sql = (check.get('sqltext') or '').lower()
        if 'status' in sql or 'completion_source' in sql:
            op.drop_constraint(check['name'], 'appointments', type_='check')
    for check in sa.inspect(bind).get_check_constraints('virtual_consultations'):
        if 'status' in (check.get('sqltext') or '').lower():
            op.drop_constraint(check['name'], 'virtual_consultations', type_='check')

    op.execute("UPDATE appointments SET status='TECHNICAL_ERROR' WHERE status='TECHNICAL_ISSUE'")
    op.execute("UPDATE virtual_consultations SET status='EN_ESPERA' WHERE status IN ('PACIENTE_EN_ESPERA','MEDICO_EN_ESPERA')")
    op.execute("""
        UPDATE virtual_consultations SET
          patient_present = patient_present OR status IN ('EN_ESPERA','EN_ATENCION','FINALIZADA'),
          doctor_present = doctor_present OR status IN ('EN_ATENCION','FINALIZADA'),
          patient_joined_at = COALESCE(patient_joined_at, patient_present_at),
          doctor_joined_at = COALESCE(doctor_joined_at, doctor_present_at),
          patient_present_at = COALESCE(patient_present_at, patient_joined_at),
          doctor_present_at = COALESCE(doctor_present_at, doctor_joined_at)
    """)

    # Repair mismatched demo completion once. The remote migration may already
    # have repaired a row; completion metadata prevents duplicate audit/notice.
    op.execute("""
        INSERT INTO appointment_status_history (appointment_id,status,author_id,reason,created_at)
        SELECT a.id, 'ATTENDED', a.patient_id,
          'DEMOSTRACIÓN · Reparación de sincronización de teleconsulta · No hubo atención médica real', v.updated_at
        FROM appointments a JOIN virtual_consultations v ON v.appointment_id=a.id
        WHERE v.status='FINALIZADA' AND a.status <> 'ATTENDED'
    """)
    op.execute("""
        INSERT INTO audit_events (actor_id,action,entity_id,created_at)
        SELECT a.patient_id,'DEMO_LIFECYCLE_REPAIRED',a.id,now()
        FROM appointments a JOIN virtual_consultations v ON v.appointment_id=a.id
        WHERE v.status='FINALIZADA' AND a.completion_source IS NULL
    """)
    op.execute("""
        UPDATE appointments a SET status='ATTENDED', version=a.version+1
        FROM virtual_consultations v
        WHERE v.appointment_id=a.id AND v.status='FINALIZADA' AND a.status <> 'ATTENDED'
    """)
    op.execute("""
        UPDATE appointments a SET
          completion_source='DEMO',
          simulated_completed_at=COALESCE(a.simulated_completed_at, v.finalized_at, v.updated_at),
          attended_at=COALESCE(a.attended_at, v.finalized_at, v.updated_at),
          clinically_attended=false
        FROM virtual_consultations v
        WHERE v.appointment_id=a.id AND v.status='FINALIZADA' AND a.status='ATTENDED'
          AND a.completion_source IS NULL
    """)
    op.execute("""
        INSERT INTO notifications (patient_id,message,read,created_at)
        SELECT a.patient_id,'Cita ' || a.code || ': Finalizada (simulación). Sin atención médica real; registro recuperado.',false,now()
        FROM appointments a JOIN virtual_consultations v ON v.appointment_id=a.id
        WHERE v.status='FINALIZADA' AND a.completion_source='DEMO'
          AND NOT EXISTS (
            SELECT 1 FROM notifications n WHERE n.patient_id=a.patient_id
              AND n.message ILIKE '%' || a.code || '%' AND n.message ILIKE '%finalizada%'
          )
    """)

    op.create_check_constraint('ck_appointments_status', 'appointments',
        "status IN ('CONFIRMED','CANCELLED','ATTENDED','IN_PROGRESS','PATIENT_ABSENT','DOCTOR_ABSENT','TECHNICAL_ERROR')")
    op.create_check_constraint('ck_demo_completion', 'appointments',
        "(completion_source IS NULL AND simulated_completed_at IS NULL) OR (completion_source = 'DEMO' AND simulated_completed_at IS NOT NULL AND status = 'ATTENDED' AND clinically_attended = false)")
    op.create_check_constraint('ck_virtual_status', 'virtual_consultations',
        "status IN ('PROGRAMADA','SALA_DISPONIBLE','EN_ESPERA','EN_ATENCION','FINALIZADA','PACIENTE_AUSENTE','MEDICO_AUSENTE','CANCELADA','ERROR_TECNICO')")

    op.execute('ALTER TABLE appointments DROP CONSTRAINT IF EXISTS no_doctor_overlap')
    op.execute('ALTER TABLE appointments DROP CONSTRAINT IF EXISTS no_patient_overlap')
    op.execute("ALTER TABLE appointments ADD CONSTRAINT no_doctor_overlap EXCLUDE USING gist (doctor_id WITH =, tstzrange(starts_at, ends_at, '[)') WITH &&) WHERE (status IN ('CONFIRMED','IN_PROGRESS','TECHNICAL_ERROR'))")
    op.execute("ALTER TABLE appointments ADD CONSTRAINT no_patient_overlap EXCLUDE USING gist (patient_id WITH =, tstzrange(starts_at, ends_at, '[)') WITH &&) WHERE (status IN ('CONFIRMED','IN_PROGRESS','TECHNICAL_ERROR'))")
    op.drop_index('uq_confirmed_slot', 'appointments', if_exists=True)
    op.create_index('uq_confirmed_slot', 'appointments', ['doctor_id', 'starts_at'], unique=True,
                    postgresql_where=sa.text("status IN ('CONFIRMED','IN_PROGRESS','TECHNICAL_ERROR')"))


def downgrade():
    raise RuntimeError('La reversión perdería estados y evidencia del ciclo de teleconsulta. Restaura una copia previa de la base.')
