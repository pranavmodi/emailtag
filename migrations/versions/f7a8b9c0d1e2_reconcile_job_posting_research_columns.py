"""reconcile job posting research columns

Revision ID: f7a8b9c0d1e2
Revises: e5f6a7b8c9d0
Create Date: 2026-08-22 00:00:00.000000

The production database reached e5 before f6 was inserted into the canonical
migration chain. Add the f6 columns conditionally so both that database and
clean installs converge on the same schema.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "f7a8b9c0d1e2"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade():
    existing_columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("pif_info")
    }

    if "job_postings" not in existing_columns:
        op.add_column(
            "pif_info",
            sa.Column(
                "job_postings",
                JSONB,
                nullable=True,
                comment="Recent job-posting research snapshot with source-backed posting details",
            ),
        )
    if "job_postings_research_status" not in existing_columns:
        op.add_column(
            "pif_info",
            sa.Column(
                "job_postings_research_status",
                sa.String(length=50),
                nullable=True,
                comment="Job-posting research status: queued, in_progress, completed, failed",
            ),
        )
    if "last_job_postings_researched_at" not in existing_columns:
        op.add_column(
            "pif_info",
            sa.Column(
                "last_job_postings_researched_at",
                sa.DateTime(),
                nullable=True,
                comment="Timestamp of the last recent job-posting search",
            ),
        )


def downgrade():
    # f6 owns these columns in the canonical history. A no-op downgrade avoids
    # removing them from clean databases that applied f6 before this migration.
    pass
