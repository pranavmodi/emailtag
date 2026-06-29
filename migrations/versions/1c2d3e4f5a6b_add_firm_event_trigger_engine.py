"""add firm event trigger engine

Revision ID: 1c2d3e4f5a6b
Revises: 0b91c2d3e4f5
Create Date: 2026-06-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "1c2d3e4f5a6b"
down_revision = "0b91c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "firm_event",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("firm_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("dedup_key", sa.String(length=500), nullable=False),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "event_type IN ("
            "'new_referral', 'records_surge', 'became_warm', 'went_quiet', "
            "'first_interaction', 'new_decision_maker', 'vendor_detected', "
            "'vendor_changed', 'link_opened', 'link_clicked', 'job_posting', "
            "'pe_backed', 'new_office', 'news_mention')",
            name="ck_firm_event_type",
        ),
        sa.CheckConstraint(
            "source IN ('precise_stream', 'engagement') OR source LIKE 'external:%'",
            name="ck_firm_event_source",
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["pif_info.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedup_key", name="uq_firm_event_dedup_key"),
    )
    op.create_index(op.f("ix_firm_event_firm_id"), "firm_event", ["firm_id"], unique=False)
    op.create_index(op.f("ix_firm_event_event_type"), "firm_event", ["event_type"], unique=False)
    op.create_index(op.f("ix_firm_event_occurred_at"), "firm_event", ["occurred_at"], unique=False)
    op.create_index(op.f("ix_firm_event_source"), "firm_event", ["source"], unique=False)
    op.create_index(op.f("ix_firm_event_score"), "firm_event", ["score"], unique=False)
    op.create_index(op.f("ix_firm_event_dedup_key"), "firm_event", ["dedup_key"], unique=False)
    op.create_index(op.f("ix_firm_event_delivered_at"), "firm_event", ["delivered_at"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_firm_event_delivered_at"), table_name="firm_event")
    op.drop_index(op.f("ix_firm_event_dedup_key"), table_name="firm_event")
    op.drop_index(op.f("ix_firm_event_score"), table_name="firm_event")
    op.drop_index(op.f("ix_firm_event_source"), table_name="firm_event")
    op.drop_index(op.f("ix_firm_event_occurred_at"), table_name="firm_event")
    op.drop_index(op.f("ix_firm_event_event_type"), table_name="firm_event")
    op.drop_index(op.f("ix_firm_event_firm_id"), table_name="firm_event")
    op.drop_table("firm_event")
