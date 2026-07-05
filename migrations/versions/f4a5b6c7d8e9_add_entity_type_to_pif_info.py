"""add entity_type to pif_info

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-04-21 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f4a5b6c7d8e9'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'pif_info',
        sa.Column('entity_type', sa.String(50), nullable=False, server_default='pi_law_firm')
    )
    op.create_index('ix_pif_info_entity_type', 'pif_info', ['entity_type'])


def downgrade() -> None:
    op.drop_index('ix_pif_info_entity_type', table_name='pif_info')
    op.drop_column('pif_info', 'entity_type')
