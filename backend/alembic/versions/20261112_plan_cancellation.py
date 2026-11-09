"""Auditoría y cancelación inmediata genérica de planes."""
from alembic import op
import sqlalchemy as sa

revision = '20261112_plan_cancellation'
down_revision = '20261110_virtual_history'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('patient_plans', sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('patient_plans', sa.Column('cancelled_by', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_patient_plans_cancelled_by_users', 'patient_plans', 'users', ['cancelled_by'], ['id'])
    op.create_table(
        'patient_plan_cancellations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('changed_by', sa.Integer(), nullable=False),
        sa.Column('previous_status', sa.String(length=16), nullable=False),
        sa.Column('new_status', sa.String(length=16), nullable=False),
        sa.Column('policy', sa.String(length=16), nullable=False, server_default='IMMEDIATE'),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('effective_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("previous_status = 'ACTIVE' AND new_status = 'INACTIVE'", name='ck_plan_cancellation_transition'),
        sa.CheckConstraint("policy = 'IMMEDIATE'", name='ck_plan_cancellation_policy'),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id']),
        sa.ForeignKeyConstraint(['plan_id'], ['plans.id']),
        sa.ForeignKeyConstraint(['changed_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_patient_plan_cancellations_patient_id', 'patient_plan_cancellations', ['patient_id'])
    op.create_index('ix_patient_plan_cancellations_plan_id', 'patient_plan_cancellations', ['plan_id'])

def downgrade():
    op.drop_index('ix_patient_plan_cancellations_plan_id', table_name='patient_plan_cancellations')
    op.drop_index('ix_patient_plan_cancellations_patient_id', table_name='patient_plan_cancellations')
    op.drop_table('patient_plan_cancellations')
    op.drop_constraint('fk_patient_plans_cancelled_by_users', 'patient_plans', type_='foreignkey')
    op.drop_column('patient_plans', 'cancelled_by')
    op.drop_column('patient_plans', 'cancelled_at')
