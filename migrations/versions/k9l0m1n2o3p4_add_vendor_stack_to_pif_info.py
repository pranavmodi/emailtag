"""Add vendor_stack to pif_info

Revision ID: k9l0m1n2o3p4
Revises: j8k9l0m1n2o3
Create Date: 2026-06-30

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'k9l0m1n2o3p4'
down_revision = 'j8k9l0m1n2o3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('pif_info', sa.Column(
        'vendor_stack', JSONB, nullable=True,
        comment='Detected practice management vendors: [{vendor, source, confidence}]'
    ))


def downgrade():
    op.drop_column('pif_info', 'vendor_stack')
