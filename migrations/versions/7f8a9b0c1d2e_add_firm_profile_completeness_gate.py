"""add firm profile completeness gate

Revision ID: 7f8a9b0c1d2e
Revises: 58a965ee4a52
Create Date: 2026-07-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "7f8a9b0c1d2e"
down_revision = "58a965ee4a52"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "pif_info",
        sa.Column(
            "profile_completeness",
            sa.Integer(),
            nullable=True,
            comment="Count of populated core firm_profile fields used by outreach readiness gate",
        ),
    )
    op.add_column(
        "pif_info",
        sa.Column(
            "outreach_ready",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="True when must-have firm_profile fields are present and completeness >= 8",
        ),
    )
    op.create_index(
        op.f("ix_pif_info_profile_completeness"),
        "pif_info",
        ["profile_completeness"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pif_info_outreach_ready"),
        "pif_info",
        ["outreach_ready"],
        unique=False,
    )
    op.alter_column("pif_info", "outreach_ready", server_default=None)


def downgrade():
    op.drop_index(op.f("ix_pif_info_outreach_ready"), table_name="pif_info")
    op.drop_index(op.f("ix_pif_info_profile_completeness"), table_name="pif_info")
    op.drop_column("pif_info", "outreach_ready")
    op.drop_column("pif_info", "profile_completeness")
