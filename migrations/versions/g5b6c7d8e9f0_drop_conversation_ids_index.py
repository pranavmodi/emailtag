"""drop conversation_ids btree index

Revision ID: g5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-04-21 22:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'g5b6c7d8e9f0'
down_revision = 'f4a5b6c7d8e9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index('ix_pif_info_conversation_ids', table_name='pif_info')


def downgrade() -> None:
    op.create_index('ix_pif_info_conversation_ids', 'pif_info', ['conversation_ids'])
