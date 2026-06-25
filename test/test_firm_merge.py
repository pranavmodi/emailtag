from datetime import datetime, timedelta
import uuid

from app.models.firm_alias import FirmAlias
from app.models.pif_info import PifInfo
from app.services.firm_merge import (
    apply_merge_plan_to_firms,
    build_firm_merge_report,
    format_merge_report,
    restore_merge_from_payload,
)


def _firm(
    name,
    *,
    website=None,
    canonical_website=None,
    emails=None,
    phones=None,
    contacts=None,
    conversation_ids=None,
    leadership=None,
    behavioral_data=None,
    research_data=None,
    updated_at=None,
):
    firm = PifInfo(
        firm_name=name,
        website=website,
        canonical_website=canonical_website,
        emails=emails or [],
        phones=phones or [],
        addresses=[],
        contacts=contacts or [],
        conversation_ids=conversation_ids or [],
        leadership=leadership,
        behavioral_data=behavioral_data,
        research_data=research_data,
        merge_status="active",
    )
    firm.id = uuid.uuid4()
    firm.updated_at = updated_at or datetime(2026, 1, 1)
    return firm


def test_high_confidence_cluster_merges_and_records_legacy_aliases():
    survivor = _firm(
        "Yagman & Yagman APC",
        website="https://www.yaglaw.com",
        canonical_website="yaglaw.com",
        emails=["intake@yaglaw.com"],
        conversation_ids=["cnv_1", "cnv_2"],
        leadership=[{"name": "Stephen Yagman", "title": "Partner"}],
        behavioral_data={"primary_pain_point": "records"},
        updated_at=datetime(2026, 1, 2),
    )
    loser = _firm(
        "Yagman Law",
        website="https://yaglaw.com/contact",
        emails=["records@yaglaw.com"],
        phones=["555-0100"],
        contacts=[{"name": "Intake Desk", "email": "intake@yaglaw.com"}],
        conversation_ids=["cnv_2", "cnv_3"],
        research_data={"practice_areas": ["personal injury"]},
        updated_at=datetime(2026, 1, 1),
    )

    report = build_firm_merge_report([survivor, loser])
    plan = report.plans[0]
    aliases = []
    payload = apply_merge_plan_to_firms(plan, [survivor, loser], aliases=aliases)

    assert plan.auto_merge is True
    assert plan.survivor_id == str(survivor.id)
    assert set(survivor.emails) == {"intake@yaglaw.com", "records@yaglaw.com"}
    assert set(survivor.conversation_ids) == {"cnv_1", "cnv_2", "cnv_3"}
    assert survivor.phones == ["555-0100"]
    assert survivor.research_data == {"practice_areas": ["personal injury"]}
    assert loser.merged_into == survivor.id
    assert loser.merge_status == "merged"
    assert aliases[0].alias_type == "legacy_pif_id"
    assert aliases[0].alias_value == str(loser.id)
    assert aliases[0].firm_id == survivor.id
    assert aliases[0].source == "merge"
    assert survivor.merged_from[0]["firm_id"] == str(loser.id)
    assert payload["before_state"]["losers"][0]["merge_status"] == "active"


def test_junk_domain_with_dissimilar_names_routes_to_review():
    firms = [
        _firm("Alpha Injury Law", canonical_website="google.com"),
        _firm("Beta Records Group", canonical_website="https://www.google.com/a/b"),
        _firm("Central Imaging", emails=["ops@google.com"]),
    ]

    report = build_firm_merge_report(firms)

    assert len(report.plans) == 1
    plan = report.plans[0]
    assert plan.auto_merge is False
    assert "shared_or_junk_domain" in plan.review_reasons
    assert "dissimilar_firm_names" in plan.review_reasons
    assert plan.survivor_id is None
    assert plan.loser_ids == []


def test_undo_restores_pre_merge_state_and_aliases():
    survivor = _firm(
        "Yagman & Yagman",
        canonical_website="yaglaw.com",
        emails=["a@yaglaw.com"],
        conversation_ids=["cnv_1"],
        updated_at=datetime(2026, 1, 2),
    )
    loser = _firm(
        "Yagman Law",
        canonical_website="yaglaw.com",
        emails=["b@yaglaw.com"],
        conversation_ids=["cnv_2"],
        updated_at=datetime(2026, 1, 1),
    )
    original_alias = FirmAlias(
        alias_type="legacy_pif_id",
        alias_value=str(loser.id),
        firm_id=loser.id,
        confidence=1.0,
        source="backfill",
    )
    original_alias.id = uuid.uuid4()
    original_alias.created_at = datetime(2026, 1, 1)
    aliases = [original_alias]
    plan = build_firm_merge_report([survivor, loser]).plans[0]

    payload = apply_merge_plan_to_firms(plan, [survivor, loser], aliases=aliases)
    assert aliases[0].firm_id == survivor.id
    assert loser.merge_status == "merged"

    restore_merge_from_payload(payload, [survivor, loser], aliases)

    assert survivor.emails == ["a@yaglaw.com"]
    assert survivor.conversation_ids == ["cnv_1"]
    assert survivor.merged_from is None
    assert loser.emails == ["b@yaglaw.com"]
    assert loser.conversation_ids == ["cnv_2"]
    assert loser.merged_into is None
    assert loser.merge_status == "active"
    assert aliases[0].firm_id == loser.id
    assert aliases[0].source == "backfill"


def test_dry_run_fixture_report_is_readable_and_does_not_mutate_records():
    newer = datetime(2026, 1, 2)
    older = newer - timedelta(days=1)
    first = _firm(
        "Yagman & Yagman",
        canonical_website="yaglaw.com",
        emails=["a@yaglaw.com"],
        conversation_ids=["cnv_1"],
        updated_at=newer,
    )
    second = _firm(
        "Yagman Law",
        canonical_website="yaglaw.com",
        emails=["b@yaglaw.com"],
        conversation_ids=["cnv_2"],
        updated_at=older,
    )

    report = build_firm_merge_report([first, second], dry_run=True)
    rendered = format_merge_report(report)

    assert "Firm merge DRY RUN" in rendered
    assert "Auto-merge candidates: 1" in rendered
    assert "[auto_merge] yaglaw.com" in rendered
    assert first.emails == ["a@yaglaw.com"]
    assert second.emails == ["b@yaglaw.com"]
    assert second.merged_into is None
    assert second.merge_status == "active"

