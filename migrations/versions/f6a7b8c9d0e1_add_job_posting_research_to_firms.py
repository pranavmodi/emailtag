"""add job posting research to firms

Revision ID: f6a7b8c9d0e1
Revises: a1b2c3d4e5f7
Create Date: 2026-08-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "f6a7b8c9d0e1"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "pif_info",
        sa.Column(
            "job_postings",
            JSONB,
            nullable=True,
            comment="Recent job-posting research snapshot with source-backed posting details",
        ),
    )
    op.add_column(
        "pif_info",
        sa.Column(
            "job_postings_research_status",
            sa.String(length=50),
            nullable=True,
            comment="Job-posting research status: queued, in_progress, completed, failed",
        ),
    )
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
    op.drop_column("pif_info", "last_job_postings_researched_at")
    op.drop_column("pif_info", "job_postings_research_status")
    op.drop_column("pif_info", "job_postings")
