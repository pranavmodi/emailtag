"""add_tag_settings_table

Revision ID: 8b97ce955403
Revises: add_authentication
Create Date: 2025-11-18 14:29:28.749798

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '8b97ce955403'
down_revision = 'add_authentication'
branch_labels = None
depends_on = None


def upgrade():
    # Create tag_settings table
    op.create_table('tag_settings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tag_name', sa.String(length=255), nullable=False),
        sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('updated_by', sa.String(length=255), nullable=True),

        # Primary key
        sa.PrimaryKeyConstraint('id'),
    )

    # Create unique index on tag_name
    op.create_index('idx_tag_settings_tag_name', 'tag_settings', ['tag_name'], unique=True)


def downgrade():
    # Drop index
    op.drop_index('idx_tag_settings_tag_name', table_name='tag_settings')

    # Drop table
    op.drop_table('tag_settings') 