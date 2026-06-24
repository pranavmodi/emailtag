"""add reversible firm merge audit

Revision ID: 0b91c2d3e4f5
Revises: f0a1b2c3d4e5
Create Date: 2026-06-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0b91c2d3e4f5"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("pif_info", sa.Column("merged_into", sa.UUID(), nullable=True))
    op.add_column(
        "pif_info",
        sa.Column("merge_status", sa.String(length=50), nullable=False, server_default="active"),
    )
    op.add_column("pif_info", sa.Column("merged_at", sa.DateTime(), nullable=True))
    op.add_column("pif_info", sa.Column("merged_from", postgresql.JSONB(), nullable=True))
    op.create_foreign_key(
        "fk_pif_info_merged_into_pif_info",
        "pif_info",
        "pif_info",
        ["merged_into"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_pif_info_merged_into"), "pif_info", ["merged_into"], unique=False)
    op.create_index(op.f("ix_pif_info_merge_status"), "pif_info", ["merge_status"], unique=False)
    op.create_check_constraint(
        "ck_pif_info_merge_status",
        "pif_info",
        "merge_status IS NULL OR merge_status IN ('active', 'merged')",
    )
    op.alter_column("pif_info", "merge_status", server_default=None)

    op.create_table(
        "firm_merge_audit",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("canonical_domain", sa.String(length=500), nullable=False),
        sa.Column("survivor_id", sa.UUID(), nullable=False),
        sa.Column("loser_ids", postgresql.JSONB(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("plan", postgresql.JSONB(), nullable=False),
        sa.Column("before_state", postgresql.JSONB(), nullable=False),
        sa.Column("after_state", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("undone_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('applied', 'undone')", name="ck_firm_merge_audit_status"),
        sa.ForeignKeyConstraint(["survivor_id"], ["pif_info.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_firm_merge_audit_canonical_domain"),
        "firm_merge_audit",
        ["canonical_domain"],
        unique=False,
    )
    op.create_index(
        op.f("ix_firm_merge_audit_survivor_id"),
        "firm_merge_audit",
        ["survivor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_firm_merge_audit_status"),
        "firm_merge_audit",
        ["status"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_firm_merge_audit_status"), table_name="firm_merge_audit")
    op.drop_index(op.f("ix_firm_merge_audit_survivor_id"), table_name="firm_merge_audit")
    op.drop_index(op.f("ix_firm_merge_audit_canonical_domain"), table_name="firm_merge_audit")
    op.drop_table("firm_merge_audit")

    op.drop_constraint("ck_pif_info_merge_status", "pif_info", type_="check")
    op.drop_index(op.f("ix_pif_info_merge_status"), table_name="pif_info")
    op.drop_index(op.f("ix_pif_info_merged_into"), table_name="pif_info")
    op.drop_constraint("fk_pif_info_merged_into_pif_info", "pif_info", type_="foreignkey")
    op.drop_column("pif_info", "merged_from")
    op.drop_column("pif_info", "merged_at")
    op.drop_column("pif_info", "merge_status")
    op.drop_column("pif_info", "merged_into")
