"""Isolated academic instant LiveKit consultations."""
from alembic import op
import sqlalchemy as sa

revision = '20261122_demo_instant_calls'
down_revision = '20261121_livekit_rooms'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('doctors', sa.Column('is_demo_doctor', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('appointments', sa.Column('is_demo_test', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('virtual_consultations', sa.Column('is_demo_test', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column('appointments', 'hold_id', nullable=True)
    op.alter_column('appointments', 'plan_id', nullable=True)
    op.create_check_constraint(
        'ck_appointments_demo_test_financial_isolation', 'appointments',
        "(is_demo_test AND hold_id IS NULL AND plan_id IS NULL AND payment_id IS NULL AND copay = 0 AND modality = 'VIRTUAL') OR (NOT is_demo_test AND hold_id IS NOT NULL AND plan_id IS NOT NULL)",
    )
    op.create_index(
        'uq_demo_test_active_doctor', 'appointments', ['doctor_id'], unique=True,
        postgresql_where=sa.text("is_demo_test AND status IN ('CONFIRMED','IN_PROGRESS','TECHNICAL_ERROR')"),
    )


def downgrade():
    raise RuntimeError('La reversión podría perder consultas académicas; restaura un respaldo verificado si fuera necesario.')
