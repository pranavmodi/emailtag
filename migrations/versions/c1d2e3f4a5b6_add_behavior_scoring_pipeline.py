"""add_behavior_scoring_pipeline

Revision ID: c1d2e3f4a5b6
Revises: b3e7f2a91c45
Create Date: 2026-03-06 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
import uuid
from datetime import datetime


# revision identifiers, used by Alembic.
revision = 'c1d2e3f4a5b6'
down_revision = 'b3e7f2a91c45'
branch_labels = None
depends_on = None


def upgrade():
    # Add behavioral intelligence and ICP scoring columns to pif_info
    op.add_column('pif_info', sa.Column('behavioral_data', JSONB, nullable=True))
    op.add_column('pif_info', sa.Column('icp_score', sa.Integer, nullable=True))
    op.add_column('pif_info', sa.Column('icp_tier', sa.String(10), nullable=True))
    op.add_column('pif_info', sa.Column('score_breakdown', JSONB, nullable=True))
    op.add_column('pif_info', sa.Column('icp_scored_at', sa.DateTime, nullable=True))

    op.create_index('ix_pif_info_icp_score', 'pif_info', ['icp_score'])
    op.create_index('ix_pif_info_icp_tier', 'pif_info', ['icp_tier'])

    # Create pif_outreach_pipeline table
    op.create_table(
        'pif_outreach_pipeline',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            'pif_id', UUID(as_uuid=True),
            sa.ForeignKey('pif_info.id', ondelete='CASCADE'),
            nullable=False, index=True
        ),
        sa.Column('contact_name', sa.String(200), nullable=True),
        sa.Column('contact_linkedin', sa.String(500), nullable=True),
        sa.Column('contact_email', sa.String(200), nullable=True),
        sa.Column('outreach_type', sa.String(50), nullable=False),
        sa.Column('sender_persona', sa.String(20), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='not_started'),
        sa.Column('message_variant', sa.String(50), nullable=True),
        sa.Column('sent_at', sa.DateTime, nullable=True),
        sa.Column('replied_at', sa.DateTime, nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
    )


def downgrade():
    op.drop_table('pif_outreach_pipeline')
    op.drop_index('ix_pif_info_icp_tier', table_name='pif_info')
    op.drop_index('ix_pif_info_icp_score', table_name='pif_info')
    op.drop_column('pif_info', 'icp_scored_at')
    op.drop_column('pif_info', 'score_breakdown')
    op.drop_column('pif_info', 'icp_tier')
    op.drop_column('pif_info', 'icp_score')
    op.drop_column('pif_info', 'behavioral_data')
