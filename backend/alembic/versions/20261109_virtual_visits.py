"""Modalidad virtual simulada y estado persistente de teleconsulta."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20261109_virtual'
down_revision = '20261108_overlap'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('doctors', sa.Column('modalities', postgresql.JSONB(), nullable=False, server_default=sa.text("'[\"PRESENCIAL\"]'::jsonb")))
    op.add_column('doctor_availability', sa.Column('modalities', postgresql.JSONB(), nullable=False, server_default=sa.text("'[\"PRESENCIAL\"]'::jsonb")))
    op.add_column('plans', sa.Column('modalities', postgresql.JSONB(), nullable=False, server_default=sa.text("'[\"PRESENCIAL\"]'::jsonb")))
    op.add_column('appointment_holds', sa.Column('modality', sa.String(12), nullable=False, server_default='PRESENCIAL'))
    op.add_column('appointments', sa.Column('modality', sa.String(12), nullable=False, server_default='PRESENCIAL'))
    op.create_check_constraint('ck_appointment_holds_modality', 'appointment_holds', "modality IN ('PRESENCIAL','VIRTUAL')")
    op.create_check_constraint('ck_appointments_modality', 'appointments', "modality IN ('PRESENCIAL','VIRTUAL')")
    op.execute("UPDATE plans SET modalities = '[\"PRESENCIAL\",\"VIRTUAL\"]'::jsonb WHERE name IN ('Estándar','Premium')")
    op.execute("UPDATE doctors SET modalities = '[\"PRESENCIAL\",\"VIRTUAL\"]'::jsonb")
    op.execute("UPDATE doctor_availability SET modalities = '[\"PRESENCIAL\",\"VIRTUAL\"]'::jsonb")
    op.create_table(
        'virtual_consultations',
        sa.Column('appointment_id', sa.Integer(), nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=False),
        sa.Column('doctor_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(24), nullable=False, server_default='PROGRAMADA'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('PROGRAMADA','SALA_DISPONIBLE','PACIENTE_EN_ESPERA','MEDICO_EN_ESPERA','EN_ATENCION','FINALIZADA','PACIENTE_AUSENTE','MEDICO_AUSENTE','CANCELADA')", name='ck_virtual_consultations_status'),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id']),
        sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id']),
        sa.PrimaryKeyConstraint('appointment_id'),
    )
    op.create_index('ix_virtual_consultations_patient_id', 'virtual_consultations', ['patient_id'])
    op.create_index('ix_virtual_consultations_doctor_id', 'virtual_consultations', ['doctor_id'])

def downgrade():
    op.drop_index('ix_virtual_consultations_doctor_id', table_name='virtual_consultations')
    op.drop_index('ix_virtual_consultations_patient_id', table_name='virtual_consultations')
    op.drop_table('virtual_consultations')
    op.drop_constraint('ck_appointments_modality', 'appointments', type_='check')
    op.drop_constraint('ck_appointment_holds_modality', 'appointment_holds', type_='check')
    op.drop_column('appointments', 'modality')
    op.drop_column('appointment_holds', 'modality')
    op.drop_column('plans', 'modalities')
    op.drop_column('doctor_availability', 'modalities')
    op.drop_column('doctors', 'modalities')
