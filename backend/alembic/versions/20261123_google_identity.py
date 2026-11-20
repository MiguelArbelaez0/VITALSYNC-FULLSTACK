"""Optional Google identities and short-lived browser-bound challenges."""
from alembic import op
import sqlalchemy as sa

revision = '20261123_google_identity'
down_revision = '20261122_demo_instant_calls'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('google_identities',
        sa.Column('sub', sa.String(255), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, unique=True),
        sa.Column('email', sa.String(254), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('google_challenges',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('purpose', sa.String(16), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('session_hash', sa.String(64)),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumed', sa.Boolean(), nullable=False),
        sa.Column('sub', sa.String(255)),
        sa.Column('email', sa.String(254)),
        sa.Column('name', sa.String(120)))

def downgrade():
    op.drop_table('google_challenges')
    op.drop_table('google_identities')
