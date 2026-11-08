"""Amplía el historial para estados de teleconsulta demostrativa."""
from alembic import op
import sqlalchemy as sa

revision = '20261110_virtual_history'
down_revision = '20261109_virtual'
branch_labels = None
depends_on = None

def upgrade():
    op.alter_column('appointment_status_history','status',existing_type=sa.String(length=16),type_=sa.String(length=32),existing_nullable=False)

def downgrade():
    op.alter_column('appointment_status_history','status',existing_type=sa.String(length=32),type_=sa.String(length=16),existing_nullable=False)
