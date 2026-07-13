"""add firm email monthly volume cache

Revision ID: a1b2c3d4e5f7
Revises: 9b0c1d2e3f4a
Create Date: 2026-07-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a1b2c3d4e5f7"
down_revision = "9b0c1d2e3f4a"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "firm_email_monthly_volume",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "month",
            sa.Date(),
            nullable=False,
            comment="First day of the UTC calendar month",
        ),
        sa.Column("email_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["firm_id"], ["pif_info.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("firm_id", "month", name="uq_firm_email_monthly_volume_firm_month"),
    )
    op.create_index(
        op.f("ix_firm_email_monthly_volume_firm_id"),
        "firm_email_monthly_volume",
        ["firm_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_firm_email_monthly_volume_month"),
        "firm_email_monthly_volume",
        ["month"],
        unique=False,
    )

    op.execute(
        """
        INSERT INTO firm_email_monthly_volume (
            id,
            firm_id,
            month,
            email_count,
            created_at,
            updated_at
        )
        SELECT
            gen_random_uuid(),
            p.id AS firm_id,
            date_trunc(
                'month',
                COALESCE(
                    CASE
                        WHEN e.raw_data #>> '{target,data,created_at}' ~ '^[0-9]+(\\.[0-9]+)?$'
                        THEN to_timestamp(
                            (e.raw_data #>> '{target,data,created_at}')::double precision
                        ) AT TIME ZONE 'UTC'
                        ELSE NULL
                    END,
                    e.created_at
                )
            )::date AS month,
            count(*) AS email_count,
            now() AT TIME ZONE 'UTC',
            now() AT TIME ZONE 'UTC'
        FROM pif_info p
        JOIN LATERAL unnest(p.conversation_ids) AS cid(conversation_id) ON TRUE
        JOIN email e ON e.front_conversation_id = cid.conversation_id
        WHERE p.conversation_ids IS NOT NULL
          AND cardinality(p.conversation_ids) > 0
        GROUP BY p.id, month
        ON CONFLICT (firm_id, month) DO UPDATE
        SET email_count = EXCLUDED.email_count,
            updated_at = EXCLUDED.updated_at
        """
    )


def downgrade():
    op.drop_index(
        op.f("ix_firm_email_monthly_volume_month"),
        table_name="firm_email_monthly_volume",
    )
    op.drop_index(
        op.f("ix_firm_email_monthly_volume_firm_id"),
        table_name="firm_email_monthly_volume",
    )
    op.drop_table("firm_email_monthly_volume")
