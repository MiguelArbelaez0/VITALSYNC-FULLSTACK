"""Complete technical incident outcomes and require unambiguous demo metadata."""
from alembic import op
import sqlalchemy as sa

revision = '20261116_demo_metadata'
down_revision = '20261115_demo_completion'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('ck_demo_completion', 'appointments', type_='check')
    op.create_check_constraint('ck_demo_completion', 'appointments', "(completion_source IS NULL AND simulated_completed_at IS NULL) OR (completion_source IS NOT NULL AND completion_source = 'DEMO' AND simulated_completed_at IS NOT NULL AND status = 'ATTENDED' AND clinically_attended = false)")
    op.drop_constraint('ck_appointments_status', 'appointments', type_='check')
    op.create_check_constraint('ck_appointments_status', 'appointments', "status IN ('CONFIRMED','CANCELLED','ATTENDED','IN_PROGRESS','PATIENT_ABSENT','DOCTOR_ABSENT','TECHNICAL_ISSUE','TECHNICAL_ERROR')")
    for check in sa.inspect(op.get_bind()).get_check_constraints('virtual_consultations'):
        sql = (check.get('sqltext') or '').lower()
        if check.get('name') in {'ck_virtual_consultations_status', 'ck_virtual_status'} or ('programada' in sql and 'status' in sql):
            op.drop_constraint(check['name'], 'virtual_consultations', type_='check')
    op.create_check_constraint('ck_virtual_status', 'virtual_consultations', "status IN ('PROGRAMADA','SALA_DISPONIBLE','PACIENTE_EN_ESPERA','MEDICO_EN_ESPERA','EN_ESPERA','EN_ATENCION','FINALIZADA','PACIENTE_AUSENTE','MEDICO_AUSENTE','CANCELADA','ERROR_TECNICO')")


def downgrade():
    raise RuntimeError('La reversión perdería estados terminales. Restaura una copia previa de la base.')
