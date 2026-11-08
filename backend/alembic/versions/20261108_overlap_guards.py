"""Restricciones de solapamiento PostgreSQL para reservas confirmadas."""
from alembic import op

revision = '20261108_overlap'
down_revision = '1dd6f0a05515'
branch_labels = None
depends_on = None

def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS btree_gist')
    op.execute("ALTER TABLE appointments ADD CONSTRAINT no_doctor_overlap EXCLUDE USING gist (doctor_id WITH =, tstzrange(starts_at, ends_at, '[)') WITH &&) WHERE (status = 'CONFIRMED')")
    op.execute("ALTER TABLE appointments ADD CONSTRAINT no_patient_overlap EXCLUDE USING gist (patient_id WITH =, tstzrange(starts_at, ends_at, '[)') WITH &&) WHERE (status = 'CONFIRMED')")

def downgrade():
    op.execute('ALTER TABLE appointments DROP CONSTRAINT no_patient_overlap')
    op.execute('ALTER TABLE appointments DROP CONSTRAINT no_doctor_overlap')
