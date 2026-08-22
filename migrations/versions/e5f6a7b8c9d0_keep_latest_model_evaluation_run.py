"""keep only the latest model evaluation run

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-19 20:00:00.000000
"""

from alembic import op


revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    # Preserve model-level provenance while clearing references to duplicate run rows.
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY case_type, case_id, model_key
                       ORDER BY created_at DESC, id DESC
                   ) AS position
            FROM model_evaluation_runs
        )
        UPDATE model_evaluation_case_reviews
        SET seed_run_id = NULL
        WHERE seed_run_id IN (SELECT id FROM ranked WHERE position > 1)
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY case_type, case_id, model_key
                       ORDER BY created_at DESC, id DESC
                   ) AS position
            FROM model_evaluation_runs
        )
        DELETE FROM model_evaluation_runs
        WHERE id IN (SELECT id FROM ranked WHERE position > 1)
        """
    )
    op.create_unique_constraint(
        "uq_model_eval_run_case_model",
        "model_evaluation_runs",
        ["case_type", "case_id", "model_key"],
    )


def downgrade():
    op.drop_constraint(
        "uq_model_eval_run_case_model",
        "model_evaluation_runs",
        type_="unique",
    )
