"""add model evaluation reviews

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-18 18:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "model_evaluation_runs", sa.Column("human_rating", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "model_evaluation_runs", sa.Column("human_notes", sa.Text(), nullable=True)
    )
    op.add_column(
        "model_evaluation_runs",
        sa.Column("is_preferred", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "model_evaluation_runs", sa.Column("reviewed_by", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "model_evaluation_runs", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.create_table(
        "model_evaluation_case_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_type", sa.String(length=32), nullable=False),
        sa.Column("case_id", sa.String(length=255), nullable=False),
        sa.Column("reference_output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reference_text", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_type", "case_id", name="uq_model_eval_case_review"),
    )
    op.create_index(
        "ix_model_evaluation_case_reviews_case_type",
        "model_evaluation_case_reviews",
        ["case_type"],
    )
    op.create_index(
        "ix_model_evaluation_case_reviews_case_id",
        "model_evaluation_case_reviews",
        ["case_id"],
    )


def downgrade():
    op.drop_index(
        "ix_model_evaluation_case_reviews_case_id",
        table_name="model_evaluation_case_reviews",
    )
    op.drop_index(
        "ix_model_evaluation_case_reviews_case_type",
        table_name="model_evaluation_case_reviews",
    )
    op.drop_table("model_evaluation_case_reviews")
    op.drop_column("model_evaluation_runs", "reviewed_at")
    op.drop_column("model_evaluation_runs", "reviewed_by")
    op.drop_column("model_evaluation_runs", "is_preferred")
    op.drop_column("model_evaluation_runs", "human_notes")
    op.drop_column("model_evaluation_runs", "human_rating")
