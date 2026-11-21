"""Medical applications, explicit review and encrypted one-time credential delivery."""
from alembic import op
import sqlalchemy as sa

revision = '20261124_medical_registration'
down_revision = '20261123_google_identity'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('doctor_applications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('given_names', sa.String(60), nullable=False),
        sa.Column('surnames', sa.String(60), nullable=False),
        sa.Column('document_type', sa.String(2), nullable=False),
        sa.Column('document_number', sa.String(10), nullable=False),
        sa.Column('professional_number', sa.String(50), nullable=False, unique=True),
        sa.Column('specialty_id', sa.Integer(), sa.ForeignKey('specialties.id'), nullable=False),
        sa.Column('contact_email', sa.String(254)), sa.Column('phone', sa.String(30), nullable=False),
        sa.Column('bio', sa.Text(), nullable=False),
        sa.Column('institutional_email', sa.String(254), nullable=False, unique=True),
        sa.Column('receipt_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('status', sa.String(16), nullable=False), sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('doctor_id', sa.Integer(), sa.ForeignKey('doctors.id'), unique=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), unique=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(timezone=True)),
        sa.Column('reviewed_by', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('review_reason', sa.Text()), sa.Column('verification_kind', sa.String(32)),
        sa.UniqueConstraint('document_type', 'document_number', name='uq_doctor_applications_document'),
        sa.CheckConstraint("status IN ('PENDING','APPROVED','REJECTED')", name='ck_doctor_applications_status'),
        sa.CheckConstraint("document_type = 'CC' AND document_number ~ '^[0-9]{6,10}$'", name='ck_doctor_applications_document'))
    op.create_table('doctor_credential_deliveries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('status', sa.String(16), nullable=False), sa.Column('encrypted_secret', sa.Text()),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('delivered_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('PENDING','DELIVERED','REVOKED')", name='ck_doctor_delivery_status'))
    op.create_index('ix_doctor_credential_deliveries_user_id', 'doctor_credential_deliveries', ['user_id'])

def downgrade():
    op.drop_table('doctor_credential_deliveries')
    op.drop_table('doctor_applications')
