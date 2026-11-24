"""Persist real LiveKit rooms and administrative connection events."""
from alembic import op
import sqlalchemy as sa

revision = '20261121_livekit_rooms'
down_revision = '20261120_admin_portal'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('virtual_consultations', sa.Column('livekit_room_name', sa.String(80), nullable=True))
    op.add_column('virtual_consultations', sa.Column('livekit_patient_connected', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('virtual_consultations', sa.Column('livekit_doctor_connected', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('virtual_consultations', sa.Column('livekit_connection_state', sa.String(20), nullable=False, server_default='WAITING'))
    op.add_column('virtual_consultations', sa.Column('livekit_last_event_at', sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE virtual_consultations SET livekit_room_name = 'vs-' || md5(random()::text || clock_timestamp()::text || appointment_id::text)")
    op.alter_column('virtual_consultations', 'livekit_room_name', nullable=False)
    op.create_unique_constraint('uq_virtual_consultations_livekit_room', 'virtual_consultations', ['livekit_room_name'])
    op.create_check_constraint('ck_virtual_consultations_livekit_connection_state', 'virtual_consultations', "livekit_connection_state IN ('WAITING','CONNECTED','RECONNECTING','DISCONNECTED')")
    op.create_table(
        'livekit_room_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('event_id', sa.String(80), nullable=False, unique=True),
        sa.Column('appointment_id', sa.Integer(), sa.ForeignKey('appointments.id'), nullable=False),
        sa.Column('participant_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('participant_role', sa.String(8), nullable=False),
        sa.Column('event_type', sa.String(32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("participant_role IN ('PATIENT','DOCTOR')", name='ck_livekit_event_role'),
        sa.CheckConstraint("event_type IN ('participant_joined','participant_left')", name='ck_livekit_event_type'),
    )
    op.create_index('ix_livekit_room_events_appointment_id', 'livekit_room_events', ['appointment_id'])


def downgrade():
    raise RuntimeError('La reversión elimina el historial de conexiones; restaura un respaldo verificado si fuera necesario.')
