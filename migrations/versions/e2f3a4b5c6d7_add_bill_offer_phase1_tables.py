"""add bill offer phase 1 tables

Revision ID: e2f3a4b5c6d7
Revises: d1a2b3c4e5f6
Create Date: 2026-06-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'e2f3a4b5c6d7'
down_revision = 'd1a2b3c4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'bill_offer_intake',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('front_conversation_id', sa.String(length=200), nullable=False),
        sa.Column('email_id', sa.UUID(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('patient_id', sa.String(length=100), nullable=True),
        sa.Column('patient_match', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('patient_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('extracted_facts', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('corrected_facts', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('missing_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('confidence', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('original_sender_email', sa.String(length=500), nullable=True),
        sa.Column('last_agent_action', sa.String(length=200), nullable=True),
        sa.Column('last_run_id', sa.String(length=100), nullable=True),
        sa.Column('last_agent_run_status', sa.String(length=50), nullable=True),
        sa.Column('reply_draft', sa.Text(), nullable=True),
        sa.Column('reply_sent_at', sa.DateTime(), nullable=True),
        sa.Column('reviewed_by', sa.String(length=200), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['email_id'], ['email.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('front_conversation_id'),
    )
    op.create_index(op.f('ix_bill_offer_intake_front_conversation_id'), 'bill_offer_intake', ['front_conversation_id'])
    op.create_index(op.f('ix_bill_offer_intake_email_id'), 'bill_offer_intake', ['email_id'])
    op.create_index(op.f('ix_bill_offer_intake_status'), 'bill_offer_intake', ['status'])
    op.create_index(op.f('ix_bill_offer_intake_patient_id'), 'bill_offer_intake', ['patient_id'])
    op.create_index(op.f('ix_bill_offer_intake_last_run_id'), 'bill_offer_intake', ['last_run_id'])

    op.create_table(
        'bill_offer_agent_log',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('front_conversation_id', sa.String(length=200), nullable=False),
        sa.Column('email_id', sa.UUID(), nullable=True),
        sa.Column('intake_id', sa.UUID(), nullable=True),
        sa.Column('run_id', sa.String(length=100), nullable=False),
        sa.Column('step_name', sa.String(length=100), nullable=False),
        sa.Column('step_status', sa.String(length=50), nullable=False),
        sa.Column('input_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('output_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['email_id'], ['email.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['intake_id'], ['bill_offer_intake.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_bill_offer_agent_log_front_conversation_id'), 'bill_offer_agent_log', ['front_conversation_id'])
    op.create_index(op.f('ix_bill_offer_agent_log_email_id'), 'bill_offer_agent_log', ['email_id'])
    op.create_index(op.f('ix_bill_offer_agent_log_intake_id'), 'bill_offer_agent_log', ['intake_id'])
    op.create_index(op.f('ix_bill_offer_agent_log_run_id'), 'bill_offer_agent_log', ['run_id'])
    op.create_index(op.f('ix_bill_offer_agent_log_step_name'), 'bill_offer_agent_log', ['step_name'])
    op.create_index(op.f('ix_bill_offer_agent_log_step_status'), 'bill_offer_agent_log', ['step_status'])

    op.create_table(
        'bill_offer_correction_audit',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('front_conversation_id', sa.String(length=200), nullable=False),
        sa.Column('intake_id', sa.UUID(), nullable=False),
        sa.Column('field_name', sa.String(length=100), nullable=False),
        sa.Column('previous_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('new_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('changed_by', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['intake_id'], ['bill_offer_intake.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('intake_id', 'field_name', 'created_at', name='uq_bill_offer_audit_event'),
    )
    op.create_index(op.f('ix_bill_offer_correction_audit_front_conversation_id'), 'bill_offer_correction_audit', ['front_conversation_id'])
    op.create_index(op.f('ix_bill_offer_correction_audit_intake_id'), 'bill_offer_correction_audit', ['intake_id'])
    op.create_index(op.f('ix_bill_offer_correction_audit_field_name'), 'bill_offer_correction_audit', ['field_name'])

    op.execute(
        """
        INSERT INTO system_settings (id, setting_key, setting_value, description, updated_at, updated_by)
        VALUES
            ('11111111-2222-4333-8444-000000000001', 'autorespond_bill_offer', false, 'Enable/disable the Bill Offer intake agent', now(), 'migration'),
            ('11111111-2222-4333-8444-000000000002', 'autorespond_bill_offer_review_required', true, 'Require Settings2 review before Bill Offer Phase 1 replies are sent', now(), 'migration')
        ON CONFLICT (setting_key) DO NOTHING
        """
    )


def downgrade():
    op.execute(
        """
        DELETE FROM system_settings
        WHERE setting_key IN ('autorespond_bill_offer', 'autorespond_bill_offer_review_required')
          AND updated_by = 'migration'
        """
    )

    op.drop_index(op.f('ix_bill_offer_correction_audit_field_name'), table_name='bill_offer_correction_audit')
    op.drop_index(op.f('ix_bill_offer_correction_audit_intake_id'), table_name='bill_offer_correction_audit')
    op.drop_index(op.f('ix_bill_offer_correction_audit_front_conversation_id'), table_name='bill_offer_correction_audit')
    op.drop_table('bill_offer_correction_audit')

    op.drop_index(op.f('ix_bill_offer_agent_log_step_status'), table_name='bill_offer_agent_log')
    op.drop_index(op.f('ix_bill_offer_agent_log_step_name'), table_name='bill_offer_agent_log')
    op.drop_index(op.f('ix_bill_offer_agent_log_run_id'), table_name='bill_offer_agent_log')
    op.drop_index(op.f('ix_bill_offer_agent_log_intake_id'), table_name='bill_offer_agent_log')
    op.drop_index(op.f('ix_bill_offer_agent_log_email_id'), table_name='bill_offer_agent_log')
    op.drop_index(op.f('ix_bill_offer_agent_log_front_conversation_id'), table_name='bill_offer_agent_log')
    op.drop_table('bill_offer_agent_log')

    op.drop_index(op.f('ix_bill_offer_intake_last_run_id'), table_name='bill_offer_intake')
    op.drop_index(op.f('ix_bill_offer_intake_patient_id'), table_name='bill_offer_intake')
    op.drop_index(op.f('ix_bill_offer_intake_status'), table_name='bill_offer_intake')
    op.drop_index(op.f('ix_bill_offer_intake_email_id'), table_name='bill_offer_intake')
    op.drop_index(op.f('ix_bill_offer_intake_front_conversation_id'), table_name='bill_offer_intake')
    op.drop_table('bill_offer_intake')
