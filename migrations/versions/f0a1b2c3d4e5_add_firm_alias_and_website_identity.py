"""add firm alias and website identity fields

Revision ID: f0a1b2c3d4e5
Revises: e2f3a4b5c6d7
Create Date: 2026-06-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f0a1b2c3d4e5'
down_revision = 'e2f3a4b5c6d7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('pif_info', sa.Column('canonical_website', sa.String(length=500), nullable=True))
    op.add_column('pif_info', sa.Column('website_status', sa.String(length=50), nullable=True))
    op.add_column('pif_info', sa.Column('website_source', sa.String(length=50), nullable=True))
    op.add_column('pif_info', sa.Column('website_confidence', sa.Float(), nullable=True))
    op.create_index(op.f('ix_pif_info_canonical_website'), 'pif_info', ['canonical_website'], unique=True)
    op.create_index(op.f('ix_pif_info_website_status'), 'pif_info', ['website_status'], unique=False)
    op.create_check_constraint(
        'ck_pif_info_website_status',
        'pif_info',
        "website_status IS NULL OR website_status IN ('resolved', 'pending', 'none')",
    )
    op.create_check_constraint(
        'ck_pif_info_website_source',
        'pif_info',
        "website_source IS NULL OR website_source IN ('email_verified', 'web_search', 'human')",
    )

    op.create_table(
        'firm_alias',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('alias_type', sa.String(length=50), nullable=False),
        sa.Column('alias_value', sa.String(length=500), nullable=False),
        sa.Column('firm_id', sa.UUID(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "alias_type IN ('legacy_pif_id', 'domain', 'alt_domain', 'email_domain', "
            "'vanity_domain', 'firm_name_fuzzy')",
            name='ck_firm_alias_type',
        ),
        sa.ForeignKeyConstraint(['firm_id'], ['pif_info.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('alias_type', 'alias_value', name='uq_firm_alias_type_value'),
    )
    op.create_index(op.f('ix_firm_alias_alias_type'), 'firm_alias', ['alias_type'], unique=False)
    op.create_index(op.f('ix_firm_alias_alias_value'), 'firm_alias', ['alias_value'], unique=False)
    op.create_index(op.f('ix_firm_alias_firm_id'), 'firm_alias', ['firm_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_firm_alias_firm_id'), table_name='firm_alias')
    op.drop_index(op.f('ix_firm_alias_alias_value'), table_name='firm_alias')
    op.drop_index(op.f('ix_firm_alias_alias_type'), table_name='firm_alias')
    op.drop_table('firm_alias')

    op.drop_constraint('ck_pif_info_website_source', 'pif_info', type_='check')
    op.drop_constraint('ck_pif_info_website_status', 'pif_info', type_='check')
    op.drop_index(op.f('ix_pif_info_website_status'), table_name='pif_info')
    op.drop_index(op.f('ix_pif_info_canonical_website'), table_name='pif_info')
    op.drop_column('pif_info', 'website_confidence')
    op.drop_column('pif_info', 'website_source')
    op.drop_column('pif_info', 'website_status')
    op.drop_column('pif_info', 'canonical_website')
