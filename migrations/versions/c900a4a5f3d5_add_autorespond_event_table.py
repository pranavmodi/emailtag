"""add autorespond_event table

Revision ID: c900a4a5f3d5
Revises: g5b6c7d8e9f0
Create Date: 2026-04-27 21:36:37.907541

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'c900a4a5f3d5'
down_revision = 'g5b6c7d8e9f0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('autorespond_event',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('pif_id', sa.UUID(), nullable=True, comment='Matched PIF firm (nullable if no match found)'),
        sa.Column('firm_name', sa.String(length=500), nullable=True, comment='Firm name (denormalized for display even when pif_id is null)'),
        sa.Column('agent_type', sa.String(length=100), nullable=False, comment='Agent that handled the autorespond'),
        sa.Column('contact_email', sa.String(length=500), nullable=False, comment='Sender email that triggered the autorespond'),
        sa.Column('contact_name', sa.String(length=500), nullable=True, comment='Contact name resolved from PIF contacts'),
        sa.Column('conversation_id', sa.String(length=200), nullable=False, comment='Front conversation ID'),
        sa.Column('email_subject', sa.Text(), nullable=True, comment='Subject of the triggering email'),
        sa.Column('tags', sa.ARRAY(sa.String()), nullable=False, comment='Classification tags applied to the email'),
        sa.Column('response_sent', sa.Boolean(), nullable=False, comment='Whether the reply was actually sent'),
        sa.Column('test_mode', sa.Boolean(), nullable=False, comment='Whether this was a sandbox/test mode response'),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Agent result details'),
        sa.Column('created_at', sa.DateTime(), nullable=False, comment='When the autorespond was sent'),
        sa.ForeignKeyConstraint(['pif_id'], ['pif_info.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_autorespond_event_agent_type'), 'autorespond_event', ['agent_type'], unique=False)
    op.create_index(op.f('ix_autorespond_event_conversation_id'), 'autorespond_event', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_autorespond_event_created_at'), 'autorespond_event', ['created_at'], unique=False)
    op.create_index(op.f('ix_autorespond_event_pif_id'), 'autorespond_event', ['pif_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_autorespond_event_pif_id'), table_name='autorespond_event')
    op.drop_index(op.f('ix_autorespond_event_created_at'), table_name='autorespond_event')
    op.drop_index(op.f('ix_autorespond_event_conversation_id'), table_name='autorespond_event')
    op.drop_index(op.f('ix_autorespond_event_agent_type'), table_name='autorespond_event')
    op.drop_table('autorespond_event')
