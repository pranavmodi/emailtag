"""create_usage_events_table

Revision ID: 364e63a2a846
Revises: 3137943787e8
Create Date: 2026-01-25 11:34:45.360986

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision = '364e63a2a846'
down_revision = '3137943787e8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'usage_events',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('username', sa.String(100), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),  # page_view, click, action, api_call
        sa.Column('event_name', sa.String(200), nullable=False),  # specific event identifier
        sa.Column('page_path', sa.String(500), nullable=True),
        sa.Column('component', sa.String(200), nullable=True),  # UI component involved
        sa.Column('details', JSONB, nullable=True),  # additional metadata
        sa.Column('ip_address', sa.String(50), nullable=True),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('session_id', sa.String(100), nullable=True),
        sa.Column('duration_ms', sa.Integer, nullable=True),  # time spent on page/action
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    # Create indexes for efficient querying
    op.create_index('ix_usage_events_user_id', 'usage_events', ['user_id'])
    op.create_index('ix_usage_events_username', 'usage_events', ['username'])
    op.create_index('ix_usage_events_event_type', 'usage_events', ['event_type'])
    op.create_index('ix_usage_events_event_name', 'usage_events', ['event_name'])
    op.create_index('ix_usage_events_page_path', 'usage_events', ['page_path'])
    op.create_index('ix_usage_events_created_at', 'usage_events', ['created_at'])
    op.create_index('ix_usage_events_session_id', 'usage_events', ['session_id'])


def downgrade():
    op.drop_index('ix_usage_events_session_id')
    op.drop_index('ix_usage_events_created_at')
    op.drop_index('ix_usage_events_page_path')
    op.drop_index('ix_usage_events_event_name')
    op.drop_index('ix_usage_events_event_type')
    op.drop_index('ix_usage_events_username')
    op.drop_index('ix_usage_events_user_id')
    op.drop_table('usage_events') 