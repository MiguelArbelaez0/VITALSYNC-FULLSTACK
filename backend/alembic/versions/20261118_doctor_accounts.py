"""Link each medical account to one existing professional profile."""
from alembic import op
import sqlalchemy as sa

revision = '20261118_doctor_accounts'
down_revision = '20261117_lifecycle_merge'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('doctor_accounts',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('doctor_id', sa.Integer(), sa.ForeignKey('doctors.id'), nullable=False),
        sa.UniqueConstraint('doctor_id', name='uq_doctor_accounts_doctor_id'))


def downgrade():
    # Accounts and historical authorship remain in users; professionals and visits are untouched.
    op.drop_table('doctor_accounts')
