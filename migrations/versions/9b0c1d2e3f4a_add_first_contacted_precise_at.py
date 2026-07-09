"""add first contacted precise timestamp to pif_info

Revision ID: 9b0c1d2e3f4a
Revises: 8a9b0c1d2e3f
Create Date: 2026-07-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "9b0c1d2e3f4a"
down_revision = "8a9b0c1d2e3f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "pif_info",
        sa.Column(
            "first_contacted_precise_at",
            sa.DateTime(),
            nullable=True,
            comment="Earliest linked email timestamp from a non-internal sender",
        ),
    )

    op.execute(
        """
        WITH firm_first_contact AS (
            SELECT
                p.id,
                MIN(e.created_at) AS first_contacted_precise_at
            FROM pif_info p
            JOIN LATERAL unnest(p.conversation_ids) AS cid(conversation_id) ON TRUE
            JOIN email e ON e.front_conversation_id = cid.conversation_id
            WHERE p.conversation_ids IS NOT NULL
              AND cardinality(p.conversation_ids) > 0
              AND e.sender IS NOT NULL
              AND lower(e.sender) NOT LIKE '%@precisemri.com%'
              AND lower(e.sender) NOT LIKE '%@mediflow360.com%'
              AND lower(e.sender) NOT LIKE '%@radflow360.com%'
            GROUP BY p.id
        )
        UPDATE pif_info p
        SET first_contacted_precise_at = f.first_contacted_precise_at
        FROM firm_first_contact f
        WHERE p.id = f.id
        """
    )

    op.create_index(
        "ix_pif_info_first_contacted_precise_at",
        "pif_info",
        ["first_contacted_precise_at"],
    )


def downgrade():
    op.drop_index("ix_pif_info_first_contacted_precise_at", table_name="pif_info")
    op.drop_column("pif_info", "first_contacted_precise_at")
