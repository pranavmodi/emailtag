from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.api_v2.endpoints import firm_intel as firm_intel_endpoint
from app.db.session import get_db
from app.main import app
from app.models.email import Email
from app.models.firm_alias import FirmAlias
from app.models.pif_info import PifInfo
from app.services.firm_intel import build_firm_profile


AUTH_HEADERS = {"X-PIFStats-Auth-Token": "test-pifstats-token"}


def _firm() -> PifInfo:
    now = datetime.utcnow()
    firm = PifInfo(
        firm_name="Smith Injury Law",
        entity_type="pi_law_firm",
        website="https://www.smithlaw.com",
        canonical_website="smithlaw.com",
        website_status="resolved",
        website_source="email_verified",
        website_confidence=0.95,
        emails=["jane@smithlaw.com"],
        phones=["555-0100"],
        addresses=["Los Angeles, CA"],
        contacts=[
            {
                "name": "Jane Smith",
                "title": "Managing Partner",
                "email": "jane@smithlaw.com",
                "phone": "555-0100",
                "patient_name": "John Patient",
            }
        ],
        conversation_ids=["cnv_1"],
        behavioral_data={
            "warm_score": 42,
            "trajectory": "heating",
            "last_referral_at": (now - timedelta(days=3)).isoformat(),
            "last_records_at": (now - timedelta(days=2)).isoformat(),
            "last_contact_date": (now - timedelta(days=1)).isoformat(),
            "monthly_email_volume": [3, 5, 8],
            "total_email_count": 16,
            "inbox_breakdown": {
                "inb_qfq9": {
                    "total_email_count": 10,
                    "last_seen_at": (now - timedelta(days=3)).isoformat(),
                    "message_body": "Please schedule John Patient for MRI",
                }
            },
            "primary_pain_point": "records",
            "topic_distribution": {"records": 5},
            "sender_roles": {"owner": 2, "records": 3},
            "after_hours_ratio": 0.25,
            "peak_contact_days": ["Monday"],
            "tech_signals": {
                "case_mgmt": "filevine",
                "evidence": [{"signal": "domain:smithlaw.filevineapp.com", "confidence": 0.9}],
            },
            "patient_name": "John Patient",
            "dob": "1970-01-01",
            "medical_details": "MRI lumbar spine",
            "content_text": "Raw conversation body",
        },
        research_data={
            "summary": "Personal injury firm in Los Angeles.",
            "practice_areas": ["Personal Injury"],
            "sources": [{"url": "https://smithlaw.com/about"}],
            "city": "Los Angeles",
            "state": "CA",
            "metro": "los-angeles",
            "firm_size": "5-30",
            "case_mix": {"auto": 1},
            "value_tier": "mid",
            "volume_proxy": 16,
            "patient_dob": "1970-01-01",
        },
        research_status="completed",
        last_researched_at=now - timedelta(days=4),
        leadership=[
            {
                "name": "Jane Smith",
                "title": "Managing Partner",
                "email": "jane@smithlaw.com",
            }
        ],
        staff=[],
        icp_score=77,
        icp_tier="A",
        score_breakdown={"total": 77},
        icp_scored_at=now,
        created_at=now - timedelta(days=30),
        updated_at=now,
    )
    firm.id = uuid4()
    return firm


def _profile():
    firm = _firm()
    alias = FirmAlias(
        alias_type="vanity_domain",
        alias_value="smithlaw.filevineapp.com",
        firm_id=firm.id,
        confidence=0.9,
        source="test",
    )
    email = Email(
        front_conversation_id="cnv_1",
        subject="Referral",
        sender="Jane Smith <jane@smithlaw.com>",
        recipients=["intake@precisemri.com"],
        content_text="Do not emit this body",
        content_html="<p>Do not emit this body</p>",
        raw_data={"target": {"data": {"inbox": {"id": "inb_rcld"}}}},
        created_at=datetime.utcnow() - timedelta(hours=2),
    )
    email.id = uuid4()
    return build_firm_profile(firm, aliases=[alias], emails=[email], autorespond_count=1)


def test_firm_profile_contract_mapping_and_phi_boundary():
    payload = _profile().model_dump(mode="json")

    assert payload["relationship"]["warm_score_neutral"] == 42
    assert "after_hours_ratio" in payload["behavior"]
    assert "primary_pain_point" in payload["behavior"]
    assert "sender_roles" in payload["behavior"]
    assert "inbox_breakdown" in payload["relationship"]
    assert "last_referral_at" in payload["relationship"]
    assert "last_records_at" in payload["relationship"]
    assert "last_seen_at" in payload["relationship"]
    assert "total_email_count" in payload["relationship"]
    assert "case_mgmt" in payload["vendor_stack"]
    assert payload["people"]
    assert "metro" in payload["identity"]
    assert "city" in payload["identity"]
    assert "state" in payload["identity"]
    assert "size_hint" in payload["identity"]
    assert "case_mix" in payload["identity"]
    assert "value_tier" in payload["identity"]
    assert "volume_proxy" in payload["identity"]

    serialized = str(payload)
    for forbidden in [
        "patient_name",
        "patient_dob",
        "dob",
        "medical_details",
        "message_body",
        "content_text",
        "content_html",
        "raw_data",
        "John Patient",
        "1970-01-01",
        "MRI lumbar",
        "Raw conversation body",
    ]:
        assert forbidden not in serialized


@pytest.fixture
def client():
    async def override_db():
        yield None

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_get_firm_and_people_routes_return_read_contract(client, monkeypatch):
    profile = _profile()

    async def fake_get_firm_by_id(db, firm_id):
        firm = _firm()
        firm.id = firm_id
        return firm

    async def fake_build_profile_for_firm(db, firm):
        return profile

    monkeypatch.setattr(firm_intel_endpoint, "get_firm_by_id", fake_get_firm_by_id)
    monkeypatch.setattr(
        firm_intel_endpoint,
        "build_profile_for_firm",
        fake_build_profile_for_firm,
    )

    profile_response = client.get(
        f"/api/v2/firm-intel/firms/{profile.firm_id}",
        headers=AUTH_HEADERS,
    )
    assert profile_response.status_code == 200
    assert profile_response.json()["firm_id"] == str(profile.firm_id)

    people_response = client.get(
        f"/api/v2/firm-intel/firms/{profile.firm_id}/people",
        headers=AUTH_HEADERS,
    )
    assert people_response.status_code == 200
    assert people_response.json()["people"][0]["email"] == "jane@smithlaw.com"


def test_resolve_email_uses_canonical_domain_and_firm_alias(client, monkeypatch):
    firm_id = uuid4()
    observed = {}

    async def fake_find_alias_by_values(db, alias_types, alias_value):
        observed["alias_types"] = alias_types
        observed["alias_value"] = alias_value
        return FirmAlias(
            alias_type="email_domain",
            alias_value=alias_value,
            firm_id=firm_id,
            confidence=1.0,
            source="test",
        )

    monkeypatch.setattr(firm_intel_endpoint, "find_alias_by_values", fake_find_alias_by_values)

    response = client.get(
        "/api/v2/firm-intel/firms/resolve?email=jane@smithlaw.com",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.json() == {
        "firm_id": str(firm_id),
        "matched_by": "canonical_domain",
        "matched_value": "smithlaw.com",
    }
    assert observed == {
        "alias_types": ["domain", "email_domain", "alt_domain"],
        "alias_value": "smithlaw.com",
    }
