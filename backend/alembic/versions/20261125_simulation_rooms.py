"""Independent academic video rooms."""
from alembic import op
import sqlalchemy as sa

revision = '20261125_simulation_rooms'
down_revision = '20261124_medical_registration'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('simulation_patient_access',
        sa.Column('patient_id', sa.Integer(), sa.ForeignKey('patients.id', ondelete='CASCADE'), primary_key=True))
    op.create_table('simulation_rooms',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('guest_id', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('invite_hash', sa.String(64), unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True)))
    op.create_table('simulation_attempts',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False))


def downgrade():
    op.drop_table('simulation_attempts')
    op.drop_table('simulation_rooms')
    op.drop_table('simulation_patient_access')
