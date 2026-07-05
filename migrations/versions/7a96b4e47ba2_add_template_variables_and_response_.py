"""add template variables and response templates tables

Revision ID: 7a96b4e47ba2
Revises: 6f28c3e4c723
Create Date: 2025-11-27 10:01:04.190728

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '7a96b4e47ba2'
down_revision = '6f28c3e4c723'
branch_labels = None
depends_on = None


def upgrade():
    # Create template_variables table
    op.create_table('template_variables',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('variable_key', sa.String(length=255), nullable=False),
        sa.Column('variable_name', sa.String(length=255), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('updated_by', sa.String(length=255), nullable=True),

        # Primary key
        sa.PrimaryKeyConstraint('id'),
    )

    # Create unique index on variable_key
    op.create_index('idx_template_variables_key', 'template_variables', ['variable_key'], unique=True)

    # Create response_templates table
    op.create_table('response_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('template_key', sa.String(length=255), nullable=False),
        sa.Column('template_name', sa.String(length=255), nullable=False),
        sa.Column('tag_type', sa.String(length=255), nullable=False),
        sa.Column('variable_sequence', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('updated_by', sa.String(length=255), nullable=True),

        # Primary key
        sa.PrimaryKeyConstraint('id'),
    )

    # Create unique index on template_key
    op.create_index('idx_response_templates_key', 'response_templates', ['template_key'], unique=True)

    # Create index on tag_type for faster lookups
    op.create_index('idx_response_templates_tag_type', 'response_templates', ['tag_type'])


def downgrade():
    # Drop indices for response_templates
    op.drop_index('idx_response_templates_tag_type', table_name='response_templates')
    op.drop_index('idx_response_templates_key', table_name='response_templates')

    # Drop response_templates table
    op.drop_table('response_templates')

    # Drop index for template_variables
    op.drop_index('idx_template_variables_key', table_name='template_variables')

    # Drop template_variables table
    op.drop_table('template_variables') 