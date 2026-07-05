"""add_classification_trace_table

Revision ID: 669457c4859e
Revises: 8b97ce955403
Create Date: 2025-11-19 06:26:33.860353

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '669457c4859e'
down_revision = '8b97ce955403'
branch_labels = None
depends_on = None


def upgrade():
    # Create classification_trace table
    op.create_table('classification_trace',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('front_conversation_id', sa.String(), nullable=False),
        sa.Column('email_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('step_name', sa.String(length=200), nullable=False),
        sa.Column('step_order', sa.Integer(), nullable=False),
        sa.Column('classification_path', sa.String(length=500), nullable=True),
        sa.Column('llm_model', sa.String(length=100), nullable=True),
        sa.Column('prompt_template', sa.Text(), nullable=True),
        sa.Column('full_prompt', sa.Text(), nullable=True),
        sa.Column('llm_response', sa.Text(), nullable=True),
        sa.Column('chosen_option', sa.String(length=200), nullable=True),
        sa.Column('email_format', sa.String(length=50), nullable=True),
        sa.Column('message_count', sa.Integer(), nullable=True),
        sa.Column('started_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('completed_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('prompt_tokens', sa.Integer(), nullable=True),
        sa.Column('completion_tokens', sa.Integer(), nullable=True),
        sa.Column('total_tokens', sa.Integer(), nullable=True),
        sa.Column('document_analysis', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('trace_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False),

        # Primary key
        sa.PrimaryKeyConstraint('id'),
    )

    # Create indexes
    op.create_index('idx_classification_trace_conversation_id', 'classification_trace', ['front_conversation_id'])
    op.create_index('idx_classification_trace_email_id', 'classification_trace', ['email_id'])
    op.create_index('idx_classification_trace_created_at', 'classification_trace', ['created_at'])
    op.create_index('idx_classification_trace_conversation_order', 'classification_trace', ['front_conversation_id', 'step_order'])


def downgrade():
    # Drop indexes
    op.drop_index('idx_classification_trace_conversation_order', table_name='classification_trace')
    op.drop_index('idx_classification_trace_created_at', table_name='classification_trace')
    op.drop_index('idx_classification_trace_email_id', table_name='classification_trace')
    op.drop_index('idx_classification_trace_conversation_id', table_name='classification_trace')

    # Drop table
    op.drop_table('classification_trace') 