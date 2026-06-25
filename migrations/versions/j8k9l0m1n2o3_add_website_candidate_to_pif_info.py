"""Add website_candidate to pif_info and expand website_source check constraint.

Revision ID: j8k9l0m1n2o3
Revises: hvutyz4valca
Create Date: 2026-06-25

"""
from alembic import op
import sqlalchemy as sa

revision = 'j8k9l0m1n2o3'
down_revision = '0b91c2d3e4f5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('pif_info', sa.Column('website_candidate', sa.String(500), nullable=True,
                                        comment='Unverified website candidate from web search, pending human review'))

    # Expand website_source check constraint to include human_confirmed
    op.drop_constraint('ck_pif_info_website_source', 'pif_info', type_='check')
    op.create_check_constraint(
        'ck_pif_info_website_source',
        'pif_info',
        "website_source IS NULL OR website_source IN ('email_verified', 'web_search', 'human', 'human_confirmed')",
    )


def downgrade() -> None:
    op.drop_column('pif_info', 'website_candidate')

    op.drop_constraint('ck_pif_info_website_source', 'pif_info', type_='check')
    op.create_check_constraint(
        'ck_pif_info_website_source',
        'pif_info',
        "website_source IS NULL OR website_source IN ('email_verified', 'web_search', 'human')",
    )
