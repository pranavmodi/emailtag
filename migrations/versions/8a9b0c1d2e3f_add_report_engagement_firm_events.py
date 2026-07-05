"""add report engagement firm events

Revision ID: 8a9b0c1d2e3f
Revises: 7f8a9b0c1d2e
Create Date: 2026-07-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "8a9b0c1d2e3f"
down_revision = "7f8a9b0c1d2e"
branch_labels = None
depends_on = None


UPGRADED_TYPES = (
    "'new_referral', 'records_surge', 'became_warm', 'went_quiet', "
    "'first_interaction', 'new_decision_maker', 'vendor_detected', "
    "'vendor_changed', 'link_opened', 'link_clicked', 'job_posting', "
    "'pe_backed', 'new_office', 'news_mention', 'report_viewed', "
    "'report_engaged'"
)

DOWNGRADED_TYPES = (
    "'new_referral', 'records_surge', 'became_warm', 'went_quiet', "
    "'first_interaction', 'new_decision_maker', 'vendor_detected', "
    "'vendor_changed', 'link_opened', 'link_clicked', 'job_posting', "
    "'pe_backed', 'new_office', 'news_mention'"
)


def upgrade():
    op.drop_constraint("ck_firm_event_type", "firm_event", type_="check")
    op.create_check_constraint(
        "ck_firm_event_type",
        "firm_event",
        sa.text(f"event_type IN ({UPGRADED_TYPES})"),
    )


def downgrade():
    op.drop_constraint("ck_firm_event_type", "firm_event", type_="check")
    op.create_check_constraint(
        "ck_firm_event_type",
        "firm_event",
        sa.text(f"event_type IN ({DOWNGRADED_TYPES})"),
    )
