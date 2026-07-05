"""add firm outcome attribution

Revision ID: 2d3e4f5a6b7c
Revises: 1c2d3e4f5a6b
Create Date: 2026-06-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "2d3e4f5a6b7c"
down_revision = "1c2d3e4f5a6b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("firm_event", sa.Column("converted_at", sa.DateTime(), nullable=True))
    op.create_index(
        op.f("ix_firm_event_converted_at"),
        "firm_event",
        ["converted_at"],
        unique=False,
    )

    op.create_table(
        "firm_outcome",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("firm_id", sa.UUID(), nullable=False),
        sa.Column("event", sa.String(length=50), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=False),
        sa.Column("firm_event_id", sa.UUID(), nullable=True),
        sa.Column("attribution_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "event IN ("
            "'contacted', 'replied', 'booked', 'qualified', 'won', "
            "'lost', 'unsubscribed')",
            name="ck_firm_outcome_event",
        ),
        sa.CheckConstraint(
            "channel IN ('email', 'call')",
            name="ck_firm_outcome_channel",
        ),
        sa.ForeignKeyConstraint(["firm_event_id"], ["firm_event.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["firm_id"], ["pif_info.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_firm_outcome_idempotency_key"),
    )
    op.create_index(op.f("ix_firm_outcome_firm_id"), "firm_outcome", ["firm_id"], unique=False)
    op.create_index(op.f("ix_firm_outcome_event"), "firm_outcome", ["event"], unique=False)
    op.create_index(
        op.f("ix_firm_outcome_occurred_at"),
        "firm_outcome",
        ["occurred_at"],
        unique=False,
    )
    op.create_index(op.f("ix_firm_outcome_channel"), "firm_outcome", ["channel"], unique=False)
    op.create_index(
        op.f("ix_firm_outcome_firm_event_id"),
        "firm_outcome",
        ["firm_event_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_firm_outcome_idempotency_key"),
        "firm_outcome",
        ["idempotency_key"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_firm_outcome_idempotency_key"), table_name="firm_outcome")
    op.drop_index(op.f("ix_firm_outcome_firm_event_id"), table_name="firm_outcome")
    op.drop_index(op.f("ix_firm_outcome_channel"), table_name="firm_outcome")
    op.drop_index(op.f("ix_firm_outcome_occurred_at"), table_name="firm_outcome")
    op.drop_index(op.f("ix_firm_outcome_event"), table_name="firm_outcome")
    op.drop_index(op.f("ix_firm_outcome_firm_id"), table_name="firm_outcome")
    op.drop_table("firm_outcome")

    op.drop_index(op.f("ix_firm_event_converted_at"), table_name="firm_event")
    op.drop_column("firm_event", "converted_at")
