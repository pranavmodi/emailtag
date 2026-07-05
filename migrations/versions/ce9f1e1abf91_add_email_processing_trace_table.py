"""add_email_processing_trace_table

Revision ID: ce9f1e1abf91
Revises: 2c646810cc11
Create Date: 2025-09-28 14:15:29.744127

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'ce9f1e1abf91'
down_revision = '2c646810cc11'
branch_labels = None
depends_on = None


def upgrade():
    # Create email_processing_trace table
    op.create_table('email_processing_trace',
        # Primary identification
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=sa.text('gen_random_uuid()')),
        sa.Column('front_conversation_id', sa.String(), nullable=False),
        sa.Column('email_id', postgresql.UUID(as_uuid=True), nullable=True),
        
        # Trace step identification
        sa.Column('step_name', sa.String(length=100), nullable=False),
        sa.Column('step_type', sa.String(length=50), nullable=False),
        sa.Column('step_order', sa.Integer(), nullable=False),
        
        # Processing context
        sa.Column('task_id', sa.String(length=100), nullable=True),
        sa.Column('parent_trace_id', postgresql.UUID(as_uuid=True), nullable=True),
        
        # Status and timing
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('started_at', postgresql.TIMESTAMP(timezone=True), nullable=False, default=sa.text('NOW()')),
        sa.Column('completed_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        
        # Input and output data
        sa.Column('input_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('output_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        
        # Additional metadata
        sa.Column('trace_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=True, default=sa.text('NOW()')),
        
        # Primary key
        sa.PrimaryKeyConstraint('id'),
        
        # Foreign keys
        sa.ForeignKeyConstraint(['email_id'], ['email.id'], ),
        sa.ForeignKeyConstraint(['parent_trace_id'], ['email_processing_trace.id'], ),
    )
    
    # Create indexes
    op.create_index('idx_trace_conversation_id', 'email_processing_trace', ['front_conversation_id'])
    op.create_index('idx_trace_email_id', 'email_processing_trace', ['email_id'])
    op.create_index('idx_trace_step_name', 'email_processing_trace', ['step_name'])
    op.create_index('idx_trace_status', 'email_processing_trace', ['status'])
    op.create_index('idx_trace_created_at', 'email_processing_trace', ['created_at'])
    op.create_index('idx_trace_conversation_step_order', 'email_processing_trace', ['front_conversation_id', 'step_order'])


def downgrade():
    # Drop indexes
    op.drop_index('idx_trace_conversation_step_order', table_name='email_processing_trace')
    op.drop_index('idx_trace_created_at', table_name='email_processing_trace')
    op.drop_index('idx_trace_status', table_name='email_processing_trace')
    op.drop_index('idx_trace_step_name', table_name='email_processing_trace')
    op.drop_index('idx_trace_email_id', table_name='email_processing_trace')
    op.drop_index('idx_trace_conversation_id', table_name='email_processing_trace')
    
    # Drop table
    op.drop_table('email_processing_trace') 