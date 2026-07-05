"""add_template_attachments_table

Revision ID: 5315fa964383
Revises: 7a96b4e47ba2
Create Date: 2026-01-14 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '5315fa964383'
down_revision = '7a96b4e47ba2'
branch_labels = None
depends_on = None


def upgrade():
    # Create template_attachments table
    op.create_table('template_attachments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tag_name', sa.String(length=255), nullable=False),
        sa.Column('template_key', sa.String(length=255), nullable=True),
        sa.Column('filename', sa.String(length=512), nullable=False),
        sa.Column('file_path', sa.String(length=1024), nullable=False),
        sa.Column('mime_type', sa.String(length=255), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('description', sa.String(length=1024), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('uploaded_by', sa.String(length=255), nullable=True),

        # Primary key
        sa.PrimaryKeyConstraint('id'),
    )

    # Create index on tag_name for faster lookups
    op.create_index('idx_template_attachments_tag_name', 'template_attachments', ['tag_name'])

    # Create index on template_key for filtering by specific template
    op.create_index('idx_template_attachments_template_key', 'template_attachments', ['template_key'])


def downgrade():
    # Drop indices
    op.drop_index('idx_template_attachments_template_key', table_name='template_attachments')
    op.drop_index('idx_template_attachments_tag_name', table_name='template_attachments')

    # Drop table
    op.drop_table('template_attachments')
