"""add evaluation provenance and model settings

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-19 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "model_evaluation_case_reviews",
        sa.Column("reference_source", sa.String(length=32), server_default="unknown", nullable=False),
    )
    op.add_column(
        "model_evaluation_case_reviews",
        sa.Column("seed_model_key", sa.String(length=320), nullable=True),
    )
    op.add_column(
        "model_evaluation_case_reviews",
        sa.Column("seed_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_table(
        "model_evaluation_model_settings",
        sa.Column("model_key", sa.String(length=320), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("model_key"),
    )


def downgrade():
    op.drop_table("model_evaluation_model_settings")
    op.drop_column("model_evaluation_case_reviews", "seed_run_id")
    op.drop_column("model_evaluation_case_reviews", "seed_model_key")
    op.drop_column("model_evaluation_case_reviews", "reference_source")
