"""seed_rx_credential_settings

Revision ID: b3e7f2a91c45
Revises: a8f3d7c1e9b2
Create Date: 2026-02-11 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import uuid
import json
from datetime import datetime


# revision identifiers, used by Alembic.
revision = 'b3e7f2a91c45'
down_revision = 'a8f3d7c1e9b2'
branch_labels = None
depends_on = None


def upgrade():
    # Insert RX credential screening settings into tag_settings table.
    settings_json = json.dumps({
        "credential_screening_enabled": True,
        "allowed_credentials": [
            "MD", "DO", "MBBS", "MBChB",
            "NP", "PA", "APRN", "ARNP", "CRNP", "FNP", "AGNP", "PMHNP",
            "DC", "DPM", "DDS", "DMD", "OD", "ND", "CNM", "CNS",
        ],
        "disallowed_credentials": [
            "PT", "DPT", "OCS", "SCS", "NCS", "GCS", "WCS", "PCS",
            "OT", "OTA",
            "SLP",
            "ATC", "LAC",
            "PHD", "PSYD",
            "RN", "LVN", "LPN", "MA", "EMT", "PARAMEDIC",
            "LCSW", "LMFT", "LPC", "LMHC",
            "AUD", "RRT", "PTA", "LMT", "PHARMD",
        ],
    })

    op.execute(
        sa.text(
            """
            INSERT INTO tag_settings (id, tag_name, settings, created_at, updated_at, updated_by)
            VALUES (
                :id,
                'RX',
                CAST(:settings AS jsonb),
                :now,
                :now,
                'migration'
            )
            ON CONFLICT (tag_name) DO UPDATE
            SET settings = tag_settings.settings || CAST(:settings AS jsonb),
                updated_at = :now,
                updated_by = 'migration'
            """
        ).bindparams(
            id=str(uuid.uuid4()),
            settings=settings_json,
            now=datetime.utcnow(),
        )
    )


def downgrade():
    # Remove the credential screening keys from RX tag_settings.
    # We only remove the keys we added, not the entire row (in case other settings exist).
    op.execute(
        sa.text(
            """
            UPDATE tag_settings
            SET settings = settings - 'credential_screening_enabled'
                                    - 'allowed_credentials'
                                    - 'disallowed_credentials',
                updated_at = :now,
                updated_by = 'migration_downgrade'
            WHERE tag_name = 'RX'
            """
        ).bindparams(now=datetime.utcnow())
    )
