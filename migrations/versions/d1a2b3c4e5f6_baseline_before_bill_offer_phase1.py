"""add inbox_audit_run and inbox_audit_miss tables

Revision ID: d1a2b3c4e5f6
Revises: c900a4a5f3d5
Create Date: 2026-05-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd1a2b3c4e5f6'
down_revision = 'c900a4a5f3d5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'inbox_audit_run',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('inbox_id', sa.String(length=200), nullable=False),
        sa.Column('inbox_name', sa.String(length=500), nullable=True),
        sa.Column('inbox_address', sa.String(length=500), nullable=True),
        sa.Column('run_at', sa.DateTime(), nullable=False),
        sa.Column('lookback_start', sa.DateTime(), nullable=False),
        sa.Column('lookback_end', sa.DateTime(), nullable=False),
        sa.Column('total_received', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_processed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_missed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='success'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_inbox_audit_run_inbox_id'), 'inbox_audit_run', ['inbox_id'])
    op.create_index(op.f('ix_inbox_audit_run_run_at'), 'inbox_audit_run', ['run_at'])

    op.create_table(
        'inbox_audit_miss',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('audit_run_id', sa.UUID(), nullable=False),
        sa.Column('conversation_id', sa.String(length=200), nullable=False),
        sa.Column('front_url', sa.String(length=1000), nullable=True),
        sa.Column('inbox_id', sa.String(length=200), nullable=False),
        sa.Column('inbox_name', sa.String(length=500), nullable=True),
        sa.Column('state', sa.String(length=50), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('subject', sa.Text(), nullable=True),
        sa.Column('detected_at', sa.DateTime(), nullable=False),
        sa.Column('reviewed', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('reviewed_by', sa.String(length=200), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['audit_run_id'], ['inbox_audit_run.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_inbox_audit_miss_audit_run_id'), 'inbox_audit_miss', ['audit_run_id'])
    op.create_index(op.f('ix_inbox_audit_miss_conversation_id'), 'inbox_audit_miss', ['conversation_id'])
    op.create_index(op.f('ix_inbox_audit_miss_inbox_id'), 'inbox_audit_miss', ['inbox_id'])
    op.create_index(op.f('ix_inbox_audit_miss_state'), 'inbox_audit_miss', ['state'])
    op.create_index(op.f('ix_inbox_audit_miss_reviewed'), 'inbox_audit_miss', ['reviewed'])


def downgrade():
    op.drop_index(op.f('ix_inbox_audit_miss_reviewed'), table_name='inbox_audit_miss')
    op.drop_index(op.f('ix_inbox_audit_miss_state'), table_name='inbox_audit_miss')
    op.drop_index(op.f('ix_inbox_audit_miss_inbox_id'), table_name='inbox_audit_miss')
    op.drop_index(op.f('ix_inbox_audit_miss_conversation_id'), table_name='inbox_audit_miss')
    op.drop_index(op.f('ix_inbox_audit_miss_audit_run_id'), table_name='inbox_audit_miss')
    op.drop_table('inbox_audit_miss')

    op.drop_index(op.f('ix_inbox_audit_run_run_at'), table_name='inbox_audit_run')
    op.drop_index(op.f('ix_inbox_audit_run_inbox_id'), table_name='inbox_audit_run')
    op.drop_table('inbox_audit_run')
