"""add_staff_column_to_pif_info

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-03-11 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = 'd2e3f4a5b6c7'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('pif_info', sa.Column(
        'staff', JSONB, nullable=True,
        comment='Operational staff: intake specialists, case managers, paralegals, etc.'
    ))
    op.add_column('pif_info', sa.Column(
        'staff_research_status', sa.String(50), nullable=True,
        comment='Staff research status: queued, in_progress, completed, failed'
    ))


def downgrade():
    op.drop_column('pif_info', 'staff_research_status')
    op.drop_column('pif_info', 'staff')
