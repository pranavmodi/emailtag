"""add_system_settings_table

Revision ID: hvutyz4valca
Revises: ce9f1e1abf91
Create Date: 2025-10-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'hvutyz4valca'
down_revision = 'ce9f1e1abf91'
branch_labels = None
depends_on = None


def upgrade():
    # Create system_settings table
    op.create_table('system_settings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('setting_key', sa.String(), nullable=False),
        sa.Column('setting_value', sa.Boolean(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),

        # Primary key
        sa.PrimaryKeyConstraint('id'),
    )

    # Create unique index on setting_key
    op.create_index('idx_system_settings_key', 'system_settings', ['setting_key'], unique=True)

    # Insert default value for email_processing_enabled (enabled by default)
    op.execute("""
        INSERT INTO system_settings (id, setting_key, setting_value, description, updated_at, updated_by)
        VALUES (
            gen_random_uuid(),
            'email_processing_enabled',
            true,
            'Master switch to enable/disable all incoming email processing. When disabled, emails are received and saved but not classified or tagged.',
            NOW(),
            'migration'
        )
    """)


def downgrade():
    # Drop index
    op.drop_index('idx_system_settings_key', table_name='system_settings')

    # Drop table
    op.drop_table('system_settings')
