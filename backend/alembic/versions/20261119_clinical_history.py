"""Read-only fictional clinical histories with explicit demo patient provenance."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20261119_clinical_history'
down_revision = '20261118_doctor_accounts'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('doctor_credential_states',
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('doctor_accounts.user_id'),primary_key=True),
        sa.Column('must_change_password',sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.Column('issued_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('changed_at',sa.DateTime(timezone=True)))
    op.create_table('demo_patients',
        sa.Column('patient_id', sa.Integer(), sa.ForeignKey('patients.id'), primary_key=True),
        sa.Column('source', sa.String(32), nullable=False),
        sa.Column('confirmed_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("source IN ('BUILTIN_SEED','OPERATOR_CONFIRMED')", name='ck_demo_patient_source'))
    op.create_table('clinical_histories',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('patient_id', sa.Integer(), sa.ForeignKey('demo_patients.patient_id'), nullable=False, unique=True),
        sa.Column('demo_marker', sa.String(80), nullable=False, server_default='DATOS FICTICIOS DE DEMOSTRACIÓN'),
        sa.Column('birth_date', sa.Date()), sa.Column('demographic_note', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("demo_marker = 'DATOS FICTICIOS DE DEMOSTRACIÓN'", name='ck_clinical_history_demo'),
        sa.CheckConstraint('birth_date IS NULL OR birth_date <= CURRENT_DATE',name='ck_clinical_birth_date'))
    op.create_table('clinical_backgrounds',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('history_id', sa.Integer(), sa.ForeignKey('clinical_histories.id'), nullable=False),
        sa.Column('category', sa.String(20), nullable=False), sa.Column('description', sa.Text(), nullable=False),
        sa.UniqueConstraint('history_id','category', name='uq_clinical_background_category'),
        sa.CheckConstraint("category IN ('PERSONAL','FAMILY','SURGICAL','PREVIOUS_DISEASE')", name='ck_clinical_background_category'))
    op.create_index('ix_clinical_backgrounds_history_id','clinical_backgrounds',['history_id'])
    op.create_table('clinical_allergies',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('history_id', sa.Integer(), sa.ForeignKey('clinical_histories.id'), nullable=False),
        sa.Column('substance', sa.String(160), nullable=False), sa.Column('reaction',sa.Text(),nullable=False),
        sa.UniqueConstraint('history_id','substance',name='uq_clinical_allergy'))
    op.create_index('ix_clinical_allergies_history_id','clinical_allergies',['history_id'])
    op.create_table('clinical_medications',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('history_id',sa.Integer(),sa.ForeignKey('clinical_histories.id'),nullable=False),
        sa.Column('name',sa.String(160),nullable=False),sa.Column('note',sa.Text(),nullable=False),
        sa.Column('status',sa.String(16),nullable=False),
        sa.UniqueConstraint('history_id','name',name='uq_clinical_medication'),
        sa.CheckConstraint("status IN ('CURRENT','PREVIOUS')",name='ck_clinical_medication_status'))
    op.create_index('ix_clinical_medications_history_id','clinical_medications',['history_id'])
    op.create_table('clinical_encounters',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('history_id',sa.Integer(),sa.ForeignKey('clinical_histories.id'),nullable=False),
        sa.Column('doctor_id',sa.Integer(),sa.ForeignKey('doctors.id'),nullable=False),
        sa.Column('specialty_id',sa.Integer(),sa.ForeignKey('specialties.id'),nullable=False),
        sa.Column('appointment_id',sa.Integer(),sa.ForeignKey('appointments.id'),unique=True),
        sa.Column('seed_key',sa.String(40),nullable=False),sa.Column('occurred_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('reason',sa.Text(),nullable=False),sa.Column('observations',sa.Text(),nullable=False),
        sa.Column('diagnosis',sa.Text(),nullable=False),sa.Column('recommendations',sa.Text(),nullable=False),
        sa.Column('vitals',postgresql.JSONB(),nullable=False),
        sa.UniqueConstraint('history_id','seed_key',name='uq_clinical_encounter_seed'),
        sa.CheckConstraint("jsonb_typeof(vitals) = 'object'",name='ck_clinical_encounter_vitals'))
    op.create_index('ix_clinical_encounters_doctor_id','clinical_encounters',['doctor_id'])
    op.create_index('ix_clinical_encounters_history_date','clinical_encounters',['history_id','occurred_at'])


def downgrade():
    raise RuntimeError('La reversión eliminaría registros clínicos de demostración y su procedencia; restaura una copia revisada en un entorno aislado.')
