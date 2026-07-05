"""add_research_fields_to_pif_info

Revision ID: 4746bc7903a0
Revises: 364e63a2a846
Create Date: 2026-01-25 13:18:07.504209

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = '4746bc7903a0'
down_revision = '364e63a2a846'
branch_labels = None
depends_on = None


def upgrade():
    # Add research-related columns to pif_info table
    op.add_column('pif_info', sa.Column('leadership', JSONB, nullable=True))
    op.add_column('pif_info', sa.Column('research_data', JSONB, nullable=True))
    op.add_column('pif_info', sa.Column('research_status', sa.String(50), nullable=True))
    op.add_column('pif_info', sa.Column('last_researched_at', sa.DateTime, nullable=True))


def downgrade():
    op.drop_column('pif_info', 'last_researched_at')
    op.drop_column('pif_info', 'research_status')
    op.drop_column('pif_info', 'research_data')
    op.drop_column('pif_info', 'leadership') 