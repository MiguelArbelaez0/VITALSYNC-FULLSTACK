"""Restringe y optimiza las modalidades configuradas."""
from alembic import op

revision = '20261113_modality_guards'
down_revision = '20261112_plan_cancellation'
branch_labels = None
depends_on = None

_VALID_MODALITIES = "jsonb_typeof(modalities) = 'array' AND modalities <> '[]'::jsonb AND modalities <@ '[\"PRESENCIAL\",\"VIRTUAL\"]'::jsonb"


def upgrade():
    op.create_check_constraint('ck_doctors_modalities', 'doctors', _VALID_MODALITIES)
    op.create_check_constraint('ck_doctor_availability_modalities', 'doctor_availability', _VALID_MODALITIES)
    op.create_check_constraint('ck_plans_modalities', 'plans', _VALID_MODALITIES)
    op.create_index('ix_doctors_modalities_gin', 'doctors', ['modalities'], postgresql_using='gin')
    op.create_index('ix_doctor_availability_modalities_gin', 'doctor_availability', ['modalities'], postgresql_using='gin')


def downgrade():
    op.drop_index('ix_doctor_availability_modalities_gin', table_name='doctor_availability')
    op.drop_index('ix_doctors_modalities_gin', table_name='doctors')
    op.drop_constraint('ck_plans_modalities', 'plans', type_='check')
    op.drop_constraint('ck_doctor_availability_modalities', 'doctor_availability', type_='check')
    op.drop_constraint('ck_doctors_modalities', 'doctors', type_='check')
