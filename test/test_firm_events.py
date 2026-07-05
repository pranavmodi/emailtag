from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.api_v2.endpoints import firm_intel as firm_intel_endpoint
from app.db.session import get_db
from app.main import app
from app.models.firm_alias import FirmAlias
from app.models.firm_event import FirmEvent
from app.models.pif_info import PifInfo
from app.services import firm_events as firm_event_service
from app.services.firm_event_detectors import detect_went_quiet
from app.services.firm_event_sensors import FirmEventSensorAdapter, StubFirmEventSensorAdapter


AUTH_HEADERS = {"X-PIFStats-Auth-Token": "test-pifstats-token"}


@pytest.fixture
def client():
    async def override_db():
        yield None

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _event(firm_id, event_type="job_posting") -> FirmEvent:
    event = FirmEvent(
        firm_id=firm_id,
        event_type=event_type,
        occurred_at=datetime.utcnow(),
        source="external:stub" if event_type == "job_posting" else "precise_stream",
        detail={"source": "test"},
        score=70.0,
        dedup_key=f"test:{event_type}:{firm_id}",
        created_at=datetime.utcnow(),
    )
    event.id = uuid4()
    return event


def test_went_quiet_detector_is_idempotent_by_dedup_key(monkeypatch):
    now = datetime(2026, 6, 29, 12, 0, 0)
    firm = PifInfo(
        firm_name="Quiet Injury Law",
        entity_type="pi_law_firm",
        emails=["ops@quietlaw.com"],
        phones=[],
        addresses=[],
        contacts=[],
        conversation_ids=["cnv_quiet"],
        behavioral_data={
            "total_email_count": 12,
            "last_contact_date": (now - timedelta(days=61)).isoformat(),
        },
        created_at=now - timedelta(days=120),
        updated_at=now - timedelta(days=61),
    )
    firm.id = uuid4()

    candidate = detect_went_quiet(firm, now=now, quiet_days=45)
    assert candidate is not None
    assert candidate.event_type == "went_quiet"

    stored = {}

    class FakeDb:
        def add(self, event):
            event.id = event.id or uuid4()
            event.created_at = event.created_at or now
            stored[event.dedup_key] = event

        def commit(self):
            return None

        def refresh(self, event):
            return None

    def fake_get_event_by_dedup_key_sync(db, dedup_key):
        return stored.get(dedup_key)

    monkeypatch.setattr(
        firm_event_service,
        "get_event_by_dedup_key_sync",
        fake_get_event_by_dedup_key_sync,
    )

    first_event, first_created = firm_event_service.create_firm_event_sync(FakeDb(), candidate)
    second_event, second_created = firm_event_service.create_firm_event_sync(FakeDb(), candidate)

    assert first_created is True
    assert second_created is False
    assert second_event is first_event
    assert len(stored) == 1


def test_external_job_posting_ingest_resolves_alias_and_creates_event(client, monkeypatch):
    firm_id = uuid4()
    observed = {}

    async def fake_find_alias_by_values(db, alias_types, alias_value):
        observed["alias_types"] = alias_types
        observed["alias_value"] = alias_value
        return FirmAlias(
            alias_type=alias_types[0],
            alias_value=alias_value,
            firm_id=firm_id,
            confidence=0.95,
            source="test",
        )

    async def fake_create_firm_event(db, candidate):
        observed["candidate"] = candidate
        event = FirmEvent(
            firm_id=candidate.firm_id,
            event_type=candidate.event_type,
            occurred_at=candidate.occurred_at,
            source=candidate.source,
            detail=candidate.detail,
            score=candidate.score,
            dedup_key=candidate.dedup_key,
            created_at=datetime.utcnow(),
        )
        event.id = uuid4()
        return event, True

    monkeypatch.setattr(firm_intel_endpoint, "find_alias_by_values", fake_find_alias_by_values)
    monkeypatch.setattr(firm_intel_endpoint, "create_firm_event", fake_create_firm_event)

    response = client.post(
        "/api/v2/firm-intel/events/external",
        headers=AUTH_HEADERS,
        json={
            "vendor": "job_board_stub",
            "signal_type": "job_posting",
            "alias_type": "domain",
            "alias_value": "smithlaw.com",
            "score": 72,
            "detail": {
                "posting_url": "https://jobs.example.test/smithlaw/intake-coordinator",
                "title": "Intake Coordinator",
            },
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["created"] is True
    assert payload["matched_by"] == "domain"
    assert payload["matched_value"] == "smithlaw.com"
    assert payload["event"]["event_type"] == "job_posting"
    assert payload["event"]["source"] == "external:job_board_stub"
    assert observed["alias_types"] == ["domain"]
    assert observed["candidate"].dedup_key.startswith(
        f"external:job_board_stub:job_posting:{firm_id}:"
    )


def test_external_report_viewed_ingest_resolves_alias_and_creates_event(client, monkeypatch):
    firm_id = uuid4()
    observed = {}

    async def fake_find_alias_by_values(db, alias_types, alias_value):
        return FirmAlias(
            alias_type=alias_types[0],
            alias_value=alias_value,
            firm_id=firm_id,
            confidence=0.95,
            source="test",
        )

    async def fake_create_firm_event(db, candidate):
        observed["candidate"] = candidate
        event = FirmEvent(
            firm_id=candidate.firm_id,
            event_type=candidate.event_type,
            occurred_at=candidate.occurred_at,
            source=candidate.source,
            detail=candidate.detail,
            score=candidate.score,
            dedup_key=candidate.dedup_key,
            created_at=datetime.utcnow(),
        )
        event.id = uuid4()
        return event, True

    monkeypatch.setattr(firm_intel_endpoint, "find_alias_by_values", fake_find_alias_by_values)
    monkeypatch.setattr(firm_intel_endpoint, "create_firm_event", fake_create_firm_event)

    response = client.post(
        "/api/v2/firm-intel/events/external",
        headers=AUTH_HEADERS,
        json={
            "vendor": "lexvisibility",
            "signal_type": "report_viewed",
            "domain": "smithlaw.com",
            "score": 88,
            "detail": {"sensor_event_id": "view_123", "report_id": "rpt_123"},
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["created"] is True
    assert payload["event"]["event_type"] == "report_viewed"
    assert payload["event"]["source"] == "external:lexvisibility"
    assert payload["event"]["detail"]["vendor"] == "lexvisibility"
    assert observed["candidate"].event_type == "report_viewed"
    assert observed["candidate"].source == "external:lexvisibility"
    assert observed["candidate"].dedup_key.startswith(
        f"external:lexvisibility:report_viewed:{firm_id}:"
    )


def test_event_catalog_lists_report_engagement_events(client):
    response = client.get("/api/v2/firm-intel/events/catalog", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert "report_viewed" in response.json()["event_types"]
    assert "report_engaged" in response.json()["event_types"]


def test_get_firm_events_returns_read_only_events(client, monkeypatch):
    firm_id = uuid4()
    event = _event(firm_id, event_type="went_quiet")

    async def fake_get_firm_by_id(db, requested_firm_id):
        firm = PifInfo(
            firm_name="Smith Injury Law",
            entity_type="pi_law_firm",
            emails=[],
            phones=[],
            addresses=[],
            contacts=[],
            conversation_ids=[],
        )
        firm.id = requested_firm_id
        return firm

    async def fake_list_recent_events_for_firm(db, requested_firm_id, *, limit, mark_delivered):
        assert requested_firm_id == firm_id
        assert limit == 25
        assert mark_delivered is True
        return [event]

    monkeypatch.setattr(firm_intel_endpoint, "get_firm_by_id", fake_get_firm_by_id)
    monkeypatch.setattr(
        firm_intel_endpoint,
        "list_recent_events_for_firm",
        fake_list_recent_events_for_firm,
    )

    response = client.get(
        f"/api/v2/firm-intel/firms/{firm_id}/events?limit=25",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["firm_id"] == str(firm_id)
    assert payload["total"] == 1
    assert payload["items"][0]["event_type"] == "went_quiet"


def test_stub_sensor_adapter_documents_normalized_contract():
    adapter: FirmEventSensorAdapter = StubFirmEventSensorAdapter()

    normalized = adapter.normalize(
        {
            "signal_type": "job_posting",
            "domain": "smithlaw.com",
            "detail": {"posting_url": "https://jobs.example.test/1"},
        }
    )

    assert normalized["vendor"] == "stub"
    assert normalized["signal_type"] == "job_posting"
    assert normalized["domain"] == "smithlaw.com"
    assert normalized["detail"]["posting_url"] == "https://jobs.example.test/1"
