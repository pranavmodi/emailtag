"""create_pif_info_table

Revision ID: 3137943787e8
Revises: 5315fa964383
Create Date: 2026-01-24 14:46:42.902893

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '3137943787e8'
down_revision = '5315fa964383'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('pif_info',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('website', sa.String(length=500), nullable=True, comment='Firm website URL - unique identifier when available'),
        sa.Column('firm_name', sa.String(length=500), nullable=False, comment='Name of the personal injury law firm'),
        sa.Column('emails', sa.ARRAY(sa.String()), nullable=False, comment='All email addresses associated with the firm'),
        sa.Column('phones', sa.ARRAY(sa.String()), nullable=False, comment='All phone numbers for the firm'),
        sa.Column('fax', sa.String(length=50), nullable=True, comment='Fax number if available'),
        sa.Column('addresses', sa.ARRAY(sa.String()), nullable=False, comment='All physical addresses of the firm'),
        sa.Column('contacts', postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment='Array of contact person objects with name, title, email, phone, extension'),
        sa.Column('conversation_ids', sa.ARRAY(sa.String()), nullable=False, comment='Front conversation IDs involving this firm'),
        sa.Column('extraction_notes', sa.Text(), nullable=True, comment='Notes from extraction process'),
        sa.Column('created_at', sa.DateTime(), nullable=False, comment='Timestamp when firm was first seen'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, comment='Timestamp of last update'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_pif_info_conversation_ids'), 'pif_info', ['conversation_ids'], unique=False)
    op.create_index(op.f('ix_pif_info_firm_name'), 'pif_info', ['firm_name'], unique=False)
    op.create_index(op.f('ix_pif_info_website'), 'pif_info', ['website'], unique=True)


def downgrade():
    op.drop_index(op.f('ix_pif_info_website'), table_name='pif_info')
    op.drop_index(op.f('ix_pif_info_firm_name'), table_name='pif_info')
    op.drop_index(op.f('ix_pif_info_conversation_ids'), table_name='pif_info')
    op.drop_table('pif_info')
