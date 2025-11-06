"""Initial migration: add sessions and events tables

Revision ID: 001
Revises: 
Create Date: 2025-08-08 06:57:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create sessions table
    op.create_table(
        'sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('status', sa.Enum('INITIALIZING', 'ACTIVE', 'IDLE', 'WAITING_INPUT', 'TERMINATED', 'FAILED', name='sessionstatus'), nullable=False),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('claude_process_id', sa.String(length=255), nullable=True),
        sa.Column('output_buffer', sa.Text(), nullable=True),
        sa.Column('current_directory', sa.String(length=500), nullable=True),
        sa.Column('session_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('last_activity', sa.DateTime(), nullable=False),
        sa.Column('terminated_at', sa.DateTime(), nullable=True),
    )
    
    # Create events table
    op.create_table(
        'events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.Enum(
            'SESSION_CREATED', 'SESSION_STARTED', 'SESSION_IDLE', 'SESSION_RESUMED', 
            'SESSION_TERMINATED', 'SESSION_FAILED', 'COMMAND_SENT', 'COMMAND_EXECUTED', 
            'COMMAND_FAILED', 'OUTPUT_RECEIVED', 'ERROR_RECEIVED', 'PROVIDER_SWITCHED', 
            'PROVIDER_ERROR', 'KEEPALIVE', 'RESOURCE_WARNING', 'TIMEOUT_WARNING',
            name='eventtype'
        ), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ),
    )
    
    # Create indexes for performance
    op.create_index('ix_sessions_status', 'sessions', ['status'])
    op.create_index('ix_sessions_created_at', 'sessions', ['created_at'])
    op.create_index('ix_sessions_last_activity', 'sessions', ['last_activity'])
    op.create_index('ix_sessions_claude_process_id', 'sessions', ['claude_process_id'])
    
    op.create_index('ix_events_session_id', 'events', ['session_id'])
    op.create_index('ix_events_event_type', 'events', ['event_type'])
    op.create_index('ix_events_created_at', 'events', ['created_at'])
    op.create_index('ix_events_session_id_created_at', 'events', ['session_id', 'created_at'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_events_session_id_created_at', 'events')
    op.drop_index('ix_events_created_at', 'events')
    op.drop_index('ix_events_event_type', 'events')
    op.drop_index('ix_events_session_id', 'events')
    
    op.drop_index('ix_sessions_claude_process_id', 'sessions')
    op.drop_index('ix_sessions_last_activity', 'sessions')
    op.drop_index('ix_sessions_created_at', 'sessions')
    op.drop_index('ix_sessions_status', 'sessions')
    
    # Drop tables
    op.drop_table('events')
    op.drop_table('sessions')
    
    # Drop enums
    sa.Enum(name='eventtype').drop(op.get_bind())
    sa.Enum(name='sessionstatus').drop(op.get_bind())