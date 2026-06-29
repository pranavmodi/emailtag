import json
from datetime import datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.api_v2.endpoints import firm_intel as firm_intel_endpoint
from app.db.session import get_db
from app.main import app
from app.models.firm_event import FirmEvent
from app.models.firm_outcome import FirmOutcome
from app.models.pif_info import PifInfo
from app.services.firm_intel import build_firm_profile
from app.services.firm_outcomes import apply_positive_outcome_to_scorer_input


AUTH_HEADERS = {"X-PIFStats-Auth-Token": "test-pifstats-token"}


class FakeDb:
    def __init__(self):
        self.commits = 0
        self.refreshed = []

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        self.refreshed.append(obj)


@pytest.fixture
def fake_db():
    return FakeDb()


@pytest.fixture
def client(fake_db):
    async def override_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _firm(firm_id=None) -> PifInfo:
    firm = PifInfo(
        firm_name="Smith Injury Law",
        entity_type="pi_law_firm",
        website="https://smithlaw.com",
        canonical_website="smithlaw.com",
        website_status="resolved",
        emails=["jane@smithlaw.com"],
        phones=["555-0100"],
        addresses=["Los Angeles, CA"],
        contacts=[],
        conversation_ids=["cnv_1"],
        behavioral_data={
            "warm_score": 42,
            "monthly_email_volume": [5, 7, 8],
            "total_email_count": 20,
            "primary_pain_point": "records",
        },
        research_data={
            "metro": "los-angeles",
            "state": "CA",
            "firm_size": "10-30",
            "practice_areas": ["Personal Injury"],
        },
        leadership=[{"name": "Jane Smith", "title": "Managing Partner"}],
        staff=[],
        icp_score=34,
        icp_tier="C",
        score_breakdown={"total": 34},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    firm.id = firm_id or uuid4()
    return firm


def _event(firm_id, event_type="job_posting") -> FirmEvent:
    event = FirmEvent(
        firm_id=firm_id,
        event_type=event_type,
        occurred_at=datetime(2026, 6, 29, 12, 0, 0),
        source="external:job_board",
        detail={"title": "Intake Coordinator"},
        score=80,
        dedup_key=f"external:job_board:{firm_id}:1",
        created_at=datetime.utcnow(),
    )
    event.id = uuid4()
    return event


def _outcome(*, firm_id, event, firm_event_id=None, idempotency_key="outcome-1") -> FirmOutcome:
    outcome = FirmOutcome(
        firm_id=firm_id,
        event=event,
        occurred_at=datetime(2026, 6, 29, 13, 0, 0),
        channel="email",
        detail={"source": "possibleos"},
        firm_event_id=firm_event_id,
        attribution_snapshot={"relationship": {"total_email_count": 20}},
        idempotency_key=idempotency_key,
        created_at=datetime.utcnow(),
    )
    outcome.id = uuid4()
    return outcome


def _facts_json(firm: PifInfo) -> str:
    payload = build_firm_profile(firm).model_dump(mode="json")
    facts = {
        key: payload[key]
        for key in (
            "firm_id",
            "canonical_website",
            "website_status",
            "firm_name",
            "aliases",
            "identity",
            "people",
            "relationship",
            "behavior",
            "vendor_stack",
            "research",
        )
    }
    return json.dumps(facts, sort_keys=True)


def test_post_booked_outcome_persists_links_event_and_resolves_alias(client, monkeypatch, fake_db):
    firm_id = uuid4()
    linked_event = _event(firm_id)
    persisted = {}

    async def fake_resolve_outcome_firm(db, payload):
        assert payload.alias_type == "domain"
        assert payload.alias_value == "smithlaw.com"
        return firm_id, "domain", "smithlaw.com"

    async def fake_get_firm_event_by_id(db, event_id):
        assert event_id == linked_event.id
        return linked_event

    async def fake_create_firm_outcome(db, **kwargs):
        outcome = _outcome(
            firm_id=kwargs["firm_id"],
            event=kwargs["event"],
            firm_event_id=kwargs["firm_event_id"],
            idempotency_key=kwargs["idempotency_key"],
        )
        persisted["outcome"] = outcome
        return outcome, True

    async def fake_get_firm_by_id(db, requested_firm_id):
        return _firm(requested_firm_id)

    monkeypatch.setattr(firm_intel_endpoint, "resolve_outcome_firm", fake_resolve_outcome_firm)
    monkeypatch.setattr(firm_intel_endpoint, "get_firm_event_by_id", fake_get_firm_event_by_id)
    monkeypatch.setattr(firm_intel_endpoint, "create_firm_outcome", fake_create_firm_outcome)
    monkeypatch.setattr(firm_intel_endpoint, "get_firm_by_id", fake_get_firm_by_id)

    response = client.post(
        "/api/v2/firm-intel/outcomes",
        headers=AUTH_HEADERS,
        json={
            "idempotency_key": "possibleos-booked-1",
            "event": "booked",
            "channel": "email",
            "firm_event_id": str(linked_event.id),
            "alias_type": "domain",
            "alias_value": "smithlaw.com",
            "attribution_snapshot": {"relationship": {"total_email_count": 20}},
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["created"] is True
    assert payload["matched_by"] == "domain"
    assert payload["outcome"]["firm_id"] == str(firm_id)
    assert payload["outcome"]["firm_event_id"] == str(linked_event.id)
    assert persisted["outcome"].event == "booked"
    assert linked_event.delivered_at == persisted["outcome"].occurred_at
    assert linked_event.converted_at == persisted["outcome"].occurred_at
    assert fake_db.commits == 1


def test_won_outcome_updates_scorer_input_without_changing_published_facts():
    firm = _firm()
    before_facts = _facts_json(firm)
    outcome = _outcome(firm_id=firm.id, event="won", idempotency_key="won-1")

    changed = apply_positive_outcome_to_scorer_input(firm, outcome)

    assert changed is True
    assert firm.behavioral_data["positive_outcomes"]["event_counts"]["won"] == 1
    assert firm.score_breakdown["outcome_supervision_score"] == 4
    assert _facts_json(firm) == before_facts

    serialized_profile = build_firm_profile(firm).model_dump_json()
    assert "positive_outcomes" not in serialized_profile
    assert "outcome_supervision" not in serialized_profile


def test_get_attribution_groups_booked_rate_by_trigger_and_field_presence(client, monkeypatch):
    firm_id = uuid4()
    job_event = _event(firm_id, event_type="job_posting")
    quiet_event = _event(firm_id, event_type="went_quiet")
    rows = [
        (
            _outcome(
                firm_id=firm_id,
                event="booked",
                firm_event_id=job_event.id,
                idempotency_key="1",
            ),
            job_event,
        ),
        (
            FirmOutcome(
                id=uuid4(),
                firm_id=firm_id,
                event="lost",
                occurred_at=datetime(2026, 6, 29, 14, 0, 0),
                channel="email",
                detail={},
                firm_event_id=job_event.id,
                attribution_snapshot={"relationship": {"total_email_count": 10}},
                idempotency_key="2",
                created_at=datetime.utcnow(),
            ),
            job_event,
        ),
        (
            FirmOutcome(
                id=uuid4(),
                firm_id=firm_id,
                event="qualified",
                occurred_at=datetime(2026, 6, 29, 15, 0, 0),
                channel="call",
                detail={},
                firm_event_id=quiet_event.id,
                attribution_snapshot={"behavior": {"primary_pain_point": "records"}},
                idempotency_key="3",
                created_at=datetime.utcnow(),
            ),
            quiet_event,
        ),
    ]

    async def fake_load_outcomes_for_attribution(db):
        return rows

    monkeypatch.setattr(
        firm_intel_endpoint,
        "load_outcomes_for_attribution",
        fake_load_outcomes_for_attribution,
    )

    response = client.get("/api/v2/firm-intel/attribution", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    trigger_rates = {
        item["trigger_type"]: item["booked_or_qualified_rate"]
        for item in payload["by_trigger_type"]
    }
    assert trigger_rates == {"job_posting": 0.5, "went_quiet": 1.0}

    fields = {item["field"]: item for item in payload["by_core_field_presence"]}
    assert fields["total_email_count"]["present"] == {
        "total_count": 2,
        "booked_or_qualified_count": 1,
        "booked_or_qualified_rate": 0.5,
    }
    assert fields["primary_pain_point"]["present"] == {
        "total_count": 1,
        "booked_or_qualified_count": 1,
        "booked_or_qualified_rate": 1.0,
    }
