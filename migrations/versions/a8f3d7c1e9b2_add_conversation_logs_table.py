"""add_conversation_logs_table

Revision ID: a8f3d7c1e9b2
Revises: 4746bc7903a0
Create Date: 2026-02-06 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'a8f3d7c1e9b2'
down_revision = '4746bc7903a0'
branch_labels = None
depends_on = None


def upgrade():
    # Create conversation_logs table for storing worker logs per conversation
    op.create_table('conversation_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('front_conversation_id', sa.String(), nullable=False),
        sa.Column('email_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('log_entries', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('total_entries', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('warning_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('first_log_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('last_log_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text('now()')),

        # Primary key
        sa.PrimaryKeyConstraint('id'),

        # Foreign key to email table
        sa.ForeignKeyConstraint(['email_id'], ['email.id']),

        # Unique constraint on conversation_id
        sa.UniqueConstraint('front_conversation_id', name='uq_conversation_logs_front_conversation_id'),
    )

    # Create indexes for efficient queries
    op.create_index(
        'idx_conversation_logs_conversation_id',
        'conversation_logs',
        ['front_conversation_id']
    )
    op.create_index(
        'idx_conversation_logs_email_id',
        'conversation_logs',
        ['email_id']
    )
    op.create_index(
        'idx_conversation_logs_last_log_at',
        'conversation_logs',
        ['last_log_at']
    )
    op.create_index(
        'idx_conversation_logs_error_count',
        'conversation_logs',
        ['error_count']
    )
    op.create_index(
        'idx_conversation_logs_created_at',
        'conversation_logs',
        ['created_at']
    )


def downgrade():
    # Drop indexes
    op.drop_index('idx_conversation_logs_created_at', table_name='conversation_logs')
    op.drop_index('idx_conversation_logs_error_count', table_name='conversation_logs')
    op.drop_index('idx_conversation_logs_last_log_at', table_name='conversation_logs')
    op.drop_index('idx_conversation_logs_email_id', table_name='conversation_logs')
    op.drop_index('idx_conversation_logs_conversation_id', table_name='conversation_logs')

    # Drop table
    op.drop_table('conversation_logs')
