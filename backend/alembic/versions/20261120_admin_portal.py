"""Administrative sidecars and immutable observed economic conditions. No historical row updates."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision='20261120_admin_portal'
down_revision='20261119_clinical_history'
branch_labels=None
depends_on=None

def stamp(name='created_at'):
    return sa.Column(name,sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now())
def fk(name,target,**kw):
    return sa.Column(name,sa.Integer(),sa.ForeignKey(target),**kw)

def upgrade():
    op.create_table('plan_rules',fk('plan_id','plans.id',primary_key=True),sa.Column('version',sa.Integer(),nullable=False,server_default='1'),sa.Column('virtual_copay',sa.Integer()),sa.Column('onsite_copay',sa.Integer()),sa.Column('consultation_limit',sa.Integer()),sa.Column('benefits',sa.Text(),nullable=False,server_default=''),sa.Column('restrictions',sa.Text(),nullable=False,server_default=''),sa.CheckConstraint('(virtual_copay IS NULL OR virtual_copay >= 0) AND (onsite_copay IS NULL OR onsite_copay >= 0) AND (consultation_limit IS NULL OR consultation_limit > 0) AND version > 0',name='ck_plan_rules'))
    op.create_table('subscription_terms',fk('patient_id','patient_plans.patient_id',primary_key=True),fk('plan_id','plans.id',nullable=False),sa.Column('terms',JSONB(),nullable=False),stamp('contracted_at'))
    op.create_table('payment_terms',fk('payment_id','payments.id',primary_key=True),sa.Column('terms',JSONB(),nullable=False),stamp('recorded_at'))
    op.create_table('appointment_snapshots',fk('appointment_id','appointments.id',primary_key=True),sa.Column('terms',JSONB(),nullable=False))
    op.create_table('plan_revisions',sa.Column('id',sa.Integer(),primary_key=True),fk('plan_id','plans.id',nullable=False),sa.Column('version',sa.Integer(),nullable=False),sa.Column('terms',JSONB(),nullable=False),fk('actor_id','users.id'),sa.Column('reason',sa.Text(),nullable=False),stamp(),sa.UniqueConstraint('plan_id','version',name='uq_plan_revision'))
    op.create_index('ix_plan_revisions_plan_id','plan_revisions',['plan_id'])
    op.create_table('admin_events',sa.Column('id',sa.Integer(),primary_key=True),fk('actor_id','users.id'),sa.Column('action',sa.String(60),nullable=False),sa.Column('resource',sa.String(30),nullable=False),sa.Column('entity_id',sa.Integer()),sa.Column('reason',sa.Text(),nullable=False),sa.Column('details',JSONB(),nullable=False),stamp())
    for col in ['actor_id','action','created_at']:op.create_index('ix_admin_events_'+col,'admin_events',[col])
    op.create_table('admin_permissions',fk('user_id','users.id',primary_key=True),sa.Column('scopes',JSONB(),nullable=False),sa.CheckConstraint("jsonb_typeof(scopes) = 'array'",name='ck_admin_scopes'))
    op.create_table('recovery_requests',sa.Column('id',sa.Integer(),primary_key=True),fk('user_id','users.id',nullable=False),fk('requested_by','users.id',nullable=False),sa.Column('reason',sa.Text(),nullable=False),sa.Column('status',sa.String(12),nullable=False),sa.Column('token_hash',sa.String(64),unique=True),sa.Column('expires_at',sa.DateTime(timezone=True)),sa.Column('consumed_at',sa.DateTime(timezone=True)),stamp(),sa.CheckConstraint("status IN ('PENDING','ISSUED','USED','REVOKED')",name='ck_recovery_status'))
    op.create_index('ix_recovery_requests_user_id','recovery_requests',['user_id'])
    op.create_table('refund_requests',sa.Column('id',sa.Integer(),primary_key=True),fk('payment_id','payments.id',nullable=False,unique=True),sa.Column('amount',sa.Integer(),nullable=False),sa.Column('status',sa.String(16),nullable=False),sa.Column('version',sa.Integer(),nullable=False),fk('requested_by','users.id',nullable=False),sa.Column('reason',sa.Text(),nullable=False),stamp(),sa.CheckConstraint("status IN ('REQUESTED','REVIEWING','APPROVED','REJECTED','AUTHORIZED','PROCESSED','FAILED') AND amount > 0 AND version > 0",name='ck_refund_request'))
    op.create_table('refund_transitions',sa.Column('id',sa.Integer(),primary_key=True),fk('refund_id','refund_requests.id',nullable=False),fk('actor_id','users.id',nullable=False),sa.Column('previous_status',sa.String(16)),sa.Column('status',sa.String(16),nullable=False),sa.Column('reason',sa.Text(),nullable=False),sa.Column('operation_key',sa.String(80),nullable=False,unique=True),stamp())
    op.create_index('ix_refund_transitions_refund_id','refund_transitions',['refund_id'])
    op.create_table('appointment_reschedules',sa.Column('id',sa.Integer(),primary_key=True),fk('previous_id','appointments.id',nullable=False,unique=True),fk('replacement_id','appointments.id',nullable=False,unique=True),fk('actor_id','users.id',nullable=False),sa.Column('reason',sa.Text(),nullable=False),stamp(),sa.CheckConstraint('previous_id <> replacement_id',name='ck_distinct_reschedule'))
    op.create_table('block_releases',fk('block_id','doctor_blocks.id',primary_key=True),fk('actor_id','users.id',nullable=False),sa.Column('reason',sa.Text(),nullable=False),stamp())
    op.create_table('app_settings',sa.Column('key',sa.String(40),primary_key=True),sa.Column('value',JSONB(),nullable=False))
    # Legacy conditions are observations at migration time, not invented reconstructions of older contracts.
    op.execute("INSERT INTO plan_rules (plan_id) SELECT id FROM plans")
    terms="to_jsonb(p) || jsonb_build_object('copays',jsonb_build_object('VIRTUAL',p.copay,'PRESENCIAL',p.copay),'consultation_limit',NULL,'benefits','','restrictions','','origin','LEGACY_OBSERVED')"
    op.execute(f"INSERT INTO subscription_terms (patient_id,plan_id,terms) SELECT pp.patient_id,p.id,{terms} FROM patient_plans pp JOIN plans p ON p.id=pp.plan_id")
    op.execute(f"INSERT INTO payment_terms (payment_id,terms) SELECT pay.id,({terms}) || jsonb_build_object('price',pay.amount) FROM payments pay JOIN plans p ON p.id=pay.plan_id WHERE pay.kind='PLAN'")
    op.execute("INSERT INTO appointment_snapshots (appointment_id,terms) SELECT a.id,jsonb_build_object('plan',p.name,'doctor',d.name,'specialty',s.name,'copay',a.copay,'origin','LEGACY_OBSERVED') FROM appointments a JOIN plans p ON p.id=a.plan_id JOIN doctors d ON d.id=a.doctor_id JOIN specialties s ON s.id=d.specialty_id")
    op.execute(f"INSERT INTO plan_revisions (plan_id,version,terms,reason) SELECT p.id,1,{terms},'Condiciones observadas antes de la administración editable' FROM plans p")

def downgrade():
    raise RuntimeError('La reversión destruiría trazabilidad administrativa; revisar primero un respaldo aislado.')
