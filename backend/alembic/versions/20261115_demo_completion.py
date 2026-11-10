"""Atomic demo lifecycle and repair of previously disconnected virtual outcomes."""
from alembic import op
import sqlalchemy as sa

revision = '20261115_demo_completion'
down_revision = '20261114_patient_identity'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('appointments', sa.Column('completion_source', sa.String(8)))
    op.add_column('appointments', sa.Column('simulated_completed_at', sa.DateTime(timezone=True)))
    op.add_column('appointments', sa.Column('clinically_attended', sa.Boolean(), nullable=False, server_default=sa.false()))
    for column in ['patient_present_at', 'doctor_present_at']:
        op.add_column('virtual_consultations', sa.Column(column, sa.DateTime(timezone=True)))
    # Original migration used an unnamed check: discover its PostgreSQL name.
    checks = sa.inspect(op.get_bind()).get_check_constraints('appointments')
    for check in checks:
        if 'status' in check['sqltext']:
            op.drop_constraint(check['name'], 'appointments', type_='check')
    op.create_check_constraint('ck_appointments_status', 'appointments', "status IN ('CONFIRMED','CANCELLED','ATTENDED','IN_PROGRESS','PATIENT_ABSENT','DOCTOR_ABSENT')")
    op.create_check_constraint('ck_demo_completion', 'appointments', "(completion_source IS NULL AND simulated_completed_at IS NULL) OR (completion_source = 'DEMO' AND simulated_completed_at IS NOT NULL AND status = 'ATTENDED' AND clinically_attended = false)")
    op.execute("""UPDATE virtual_consultations v SET
        patient_present_at = (SELECT min(created_at) FROM appointment_status_history h WHERE h.appointment_id=v.appointment_id AND h.status='VIRTUAL_PACIENTE_EN_ESPERA'),
        doctor_present_at = (SELECT min(created_at) FROM appointment_status_history h WHERE h.appointment_id=v.appointment_id AND h.status='VIRTUAL_MEDICO_EN_ESPERA')""")
    op.execute("""INSERT INTO appointment_status_history (appointment_id,status,author_id,reason,created_at)
        SELECT a.id, CASE v.status WHEN 'FINALIZADA' THEN 'ATTENDED' WHEN 'EN_ATENCION' THEN 'IN_PROGRESS' WHEN 'PACIENTE_AUSENTE' THEN 'PATIENT_ABSENT' ELSE 'DOCTOR_ABSENT' END,
        a.patient_id, 'DEMOSTRACIÓN · Reparación de sincronización de teleconsulta · No hubo atención médica real', v.updated_at
        FROM appointments a JOIN virtual_consultations v ON v.appointment_id=a.id
        WHERE a.status='CONFIRMED' AND v.status IN ('FINALIZADA','EN_ATENCION','PACIENTE_AUSENTE','MEDICO_AUSENTE')""")
    op.execute("""INSERT INTO notifications (patient_id,message,read,created_at)
        SELECT a.patient_id, 'Cita ' || a.code || ': Finalizada (simulación). Sin atención médica real; registro recuperado.', false, now()
        FROM appointments a JOIN virtual_consultations v ON v.appointment_id=a.id
        WHERE a.status='CONFIRMED' AND v.status='FINALIZADA'""")
    op.execute("""INSERT INTO audit_events (actor_id,action,entity_id,created_at)
        SELECT a.patient_id, 'DEMO_LIFECYCLE_REPAIRED', a.id, now()
        FROM appointments a JOIN virtual_consultations v ON v.appointment_id=a.id
        WHERE a.status='CONFIRMED' AND v.status IN ('FINALIZADA','EN_ATENCION','PACIENTE_AUSENTE','MEDICO_AUSENTE')""")
    op.execute("""UPDATE appointments a SET
        status=CASE v.status WHEN 'FINALIZADA' THEN 'ATTENDED' WHEN 'EN_ATENCION' THEN 'IN_PROGRESS' WHEN 'PACIENTE_AUSENTE' THEN 'PATIENT_ABSENT' ELSE 'DOCTOR_ABSENT' END,
        completion_source=CASE WHEN v.status='FINALIZADA' THEN 'DEMO' END,
        simulated_completed_at=CASE WHEN v.status='FINALIZADA' THEN v.updated_at END,
        clinically_attended=false, version=a.version+1
        FROM virtual_consultations v WHERE v.appointment_id=a.id AND a.status='CONFIRMED'
        AND v.status IN ('FINALIZADA','EN_ATENCION','PACIENTE_AUSENTE','MEDICO_AUSENTE')""")
    op.drop_index('uq_confirmed_slot', 'appointments')
    op.create_index('uq_confirmed_slot', 'appointments', ['doctor_id', 'starts_at'], unique=True, postgresql_where=sa.text("status IN ('CONFIRMED','IN_PROGRESS')"))
    for subject in ['doctor', 'patient']:
        op.execute(f'ALTER TABLE appointments DROP CONSTRAINT no_{subject}_overlap')
        op.execute(f"ALTER TABLE appointments ADD CONSTRAINT no_{subject}_overlap EXCLUDE USING gist ({subject}_id WITH =, tstzrange(starts_at, ends_at, '[)') WITH &&) WHERE (status IN ('CONFIRMED','IN_PROGRESS'))")


def downgrade():
    # Refuse a lossy downgrade of lifecycle metadata.
    raise RuntimeError('La reversión eliminaría evidencia de demostraciones. Restaura una copia previa de la base.')
