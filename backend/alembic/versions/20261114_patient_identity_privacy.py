"""Add optional patient identity and privacy registration metadata."""
from alembic import op
import sqlalchemy as sa


revision = '20261114_patient_identity'
down_revision = '20261113_modality_guards'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('status', sa.String(length=16), nullable=True, server_default='ACTIVE'))
    op.add_column('users', sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')))
    op.add_column('users', sa.Column('privacy_notice_version', sa.String(length=40), nullable=True))
    op.add_column('users', sa.Column('privacy_accepted_at', sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE users SET status = 'ACTIVE' WHERE status IS NULL")
    op.execute('UPDATE users SET created_at = now() WHERE created_at IS NULL')
    op.alter_column('users', 'status', nullable=False)
    op.alter_column('users', 'created_at', nullable=False)
    op.create_check_constraint('ck_users_account_status', 'users', "status IN ('ACTIVE','DISABLED')")

    op.add_column('patients', sa.Column('document_type', sa.String(length=2), nullable=True))
    op.add_column('patients', sa.Column('document_number', sa.String(length=10), nullable=True))
    op.create_unique_constraint('uq_patients_document', 'patients', ['document_type', 'document_number'])
    op.create_check_constraint(
        'ck_patients_document_format',
        'patients',
        "(document_type IS NULL AND document_number IS NULL) OR "
        "(document_type = 'CC' AND document_number ~ '^[0-9]{6,10}$')",
    )


def downgrade():
    op.drop_constraint('ck_patients_document_format', 'patients', type_='check')
    op.drop_constraint('uq_patients_document', 'patients', type_='unique')
    op.drop_column('patients', 'document_number')
    op.drop_column('patients', 'document_type')
    op.drop_constraint('ck_users_account_status', 'users', type_='check')
    op.drop_column('users', 'privacy_accepted_at')
    op.drop_column('users', 'privacy_notice_version')
    op.drop_column('users', 'created_at')
    op.drop_column('users', 'status')
