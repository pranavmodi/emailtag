"""add_summary_and_reason_to_classification_trace

Revision ID: 6f28c3e4c723
Revises: 669457c4859e
Create Date: 2025-11-19 08:30:09.640426

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6f28c3e4c723'
down_revision = '669457c4859e'
branch_labels = None
depends_on = None


def upgrade():
    # Add conversation_summary and classification_reason columns
    op.add_column('classification_trace', sa.Column('conversation_summary', sa.Text(), nullable=True))
    op.add_column('classification_trace', sa.Column('classification_reason', sa.Text(), nullable=True))


def downgrade():
    # Drop the new columns
    op.drop_column('classification_trace', 'classification_reason')
    op.drop_column('classification_trace', 'conversation_summary') 