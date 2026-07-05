"""add_message_templates_table

Revision ID: 864445f4d2d3
Revises: hvutyz4valca
Create Date: 2025-11-12 09:16:12.720154

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '864445f4d2d3'
down_revision = 'hvutyz4valca'
branch_labels = None
depends_on = None


def upgrade():
    # Create message_templates table
    op.create_table('message_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('template_key', sa.String(), nullable=False),
        sa.Column('template_name', sa.String(), nullable=False),
        sa.Column('template_body', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('updated_by', sa.String(), nullable=True),

        # Primary key
        sa.PrimaryKeyConstraint('id'),
    )

    # Create unique index on template_key
    op.create_index('idx_message_templates_key', 'message_templates', ['template_key'], unique=True)


def downgrade():
    # Drop index
    op.drop_index('idx_message_templates_key', table_name='message_templates')

    # Drop table
    op.drop_table('message_templates') 