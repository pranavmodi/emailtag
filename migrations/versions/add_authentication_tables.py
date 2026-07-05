"""add_authentication_tables

Revision ID: add_authentication
Revises: 864445f4d2d3
Create Date: 2025-11-16 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision = 'add_authentication'
down_revision = '864445f4d2d3'
branch_labels = None
depends_on = None


def upgrade():
    """Add users and sessions tables for authentication."""
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('username', sa.String(), nullable=False, unique=True),
        sa.Column('hashed_password', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('last_login', sa.DateTime(), nullable=True),
    )

    # Create index on username
    op.create_index('ix_users_username', 'users', ['username'])

    # Create sessions table
    op.create_table(
        'sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('session_token', sa.String(), nullable=False, unique=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('last_activity', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )

    # Create indexes on sessions table
    op.create_index('ix_sessions_session_token', 'sessions', ['session_token'])


def downgrade():
    """Remove users and sessions tables."""
    op.drop_index('ix_sessions_session_token', table_name='sessions')
    op.drop_table('sessions')
    op.drop_index('ix_users_username', table_name='users')
    op.drop_table('users')
