"""add model evaluation runs

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f7
Create Date: 2026-08-18 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "b2c3d4e5f6a7"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "model_evaluation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_type", sa.String(length=32), nullable=False),
        sa.Column("case_id", sa.String(length=255), nullable=False),
        sa.Column("conversation_id", sa.String(length=255), nullable=True),
        sa.Column("email_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("result_index", sa.Integer(), nullable=True),
        sa.Column("objective", sa.String(length=32), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("model_key", sa.String(length=320), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "request_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=14, scale=8), nullable=False),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_model_evaluation_runs_case_type",
        "model_evaluation_runs",
        ["case_type"],
    )
    op.create_index(
        "ix_model_evaluation_runs_case_id",
        "model_evaluation_runs",
        ["case_id"],
    )
    op.create_index(
        "ix_model_evaluation_runs_status",
        "model_evaluation_runs",
        ["status"],
    )
    op.create_index(
        "ix_model_evaluation_runs_created_at",
        "model_evaluation_runs",
        ["created_at"],
    )


def downgrade():
    op.drop_index(
        "ix_model_evaluation_runs_created_at", table_name="model_evaluation_runs"
    )
    op.drop_index(
        "ix_model_evaluation_runs_status", table_name="model_evaluation_runs"
    )
    op.drop_index(
        "ix_model_evaluation_runs_case_id", table_name="model_evaluation_runs"
    )
    op.drop_index(
        "ix_model_evaluation_runs_case_type", table_name="model_evaluation_runs"
    )
    op.drop_table("model_evaluation_runs")
