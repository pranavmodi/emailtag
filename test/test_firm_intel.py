from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.api_v2.endpoints import firm_intel as firm_intel_endpoint
from app.db.session import get_db
from app.main import app
from app.models.email import Email
from app.models.firm_alias import FirmAlias
from app.models.pif_info import PifInfo
from app.services.firm_intel import build_firm_profile, serialize_pif_source_record


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
        first_contacted_precise_at=now - timedelta(days=12),
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
            "founded_year": 1998,
            "firm_size": "5-30",
            "office_locations": [
                {"city": "Los Angeles", "state": "CA", "metro": "los-angeles"}
            ],
            "notable_cases": ["Doe v. Delivery Co."],
            "awards_recognition": ["Top PI Firm"],
            "bar_associations": ["CA Bar"],
            "social_media": {"linkedin": "https://linkedin.example/smithlaw"},
            "case_mix": {"auto": 1},
            "value_tier": "mid",
            "volume_proxy": 16,
            "patient_dob": "1970-01-01",
        },
        research_status="completed",
        last_researched_at=now - timedelta(days=4),
        job_postings={
            "has_recent_openings": True,
            "window_days": 30,
            "window_start": "2026-07-24",
            "window_end": "2026-08-22",
            "researched_at": "2026-08-22T04:00:00+00:00",
            "postings": [
                {
                    "title": "Intake Specialist",
                    "location": "Los Angeles, CA",
                    "employment_type": "Full-time",
                    "posted_date": "2026-08-15",
                    "description_summary": "Handles prospective-client intake.",
                    "responsibilities": ["Answer prospective-client calls"],
                    "qualifications": ["One year of intake experience"],
                    "source_name": "Firm careers page",
                    "source_url": "https://smithlaw.com/careers/intake-specialist",
                }
            ],
        },
        job_postings_research_status="completed",
        last_job_postings_researched_at=now - timedelta(hours=1),
        leadership=[
            {
                "name": "Jane Smith",
                "title": "Managing Partner",
                "email": "jane@smithlaw.com",
                "linkedin": "https://linkedin.example/jane",
                "bio": "Founder and managing partner.",
                "publications": ["PI intake guide"],
                "cases_handled": ["Auto collision"],
                "bar_admissions": ["California"],
            }
        ],
        staff=[],
        icp_score=77,
        icp_tier="A",
        score_breakdown={"total": 77},
        icp_scored_at=now,
        merge_status="active",
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
    assert payload["identity"]["metro"] == "los-angeles"
    assert payload["identity"]["city"] == "Los Angeles"
    assert payload["identity"]["state"] == "CA"
    assert payload["research"]["founded_year"] == 1998
    assert payload["research"]["firm_size"] == "5-30"
    assert payload["research"]["office_locations"][0]["city"] == "Los Angeles"
    assert payload["research"]["notable_cases"] == ["Doe v. Delivery Co."]
    assert payload["research"]["awards_recognition"] == ["Top PI Firm"]
    assert payload["research"]["bar_associations"] == ["CA Bar"]
    assert payload["research"]["social_media"]["linkedin"] == "https://linkedin.example/smithlaw"
    assert payload["research"]["job_postings_research_status"] == "completed"
    assert payload["research"]["last_job_postings_researched_at"]
    assert payload["research"]["job_postings"]["has_recent_openings"] is True
    assert payload["research"]["job_postings"]["postings"][0]["title"] == "Intake Specialist"
    assert payload["research"]["job_postings"]["postings"][0]["source_url"] == "https://smithlaw.com/careers/intake-specialist"
    assert payload["people"][0]["linkedin"] == "https://linkedin.example/jane"
    assert payload["people"][0]["bio"] == "Founder and managing partner."
    assert payload["people"][0]["publications"] == ["PI intake guide"]
    assert payload["people"][0]["cases_handled"] == ["Auto collision"]
    assert payload["people"][0]["bar_admissions"] == ["California"]

    curated_payload = {key: value for key, value in payload.items() if key != "source_record"}
    serialized = str(curated_payload)
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


def test_firm_profile_includes_complete_source_record_for_mirror():
    firm = _firm()
    payload = build_firm_profile(firm).model_dump(mode="json")
    source_record = payload["source_record"]

    assert set(source_record) == {column.key for column in PifInfo.__mapper__.columns}
    assert source_record["id"] == str(firm.id)
    assert source_record["firm_name"] == "Smith Injury Law"
    assert source_record["first_contacted_precise_at"] == firm.first_contacted_precise_at.isoformat()
    assert source_record["canonical_website"] == "smithlaw.com"
    assert source_record["merge_status"] == "active"
    assert source_record["conversation_ids"] == ["cnv_1"]
    assert source_record["research_data"]["summary"] == "Personal injury firm in Los Angeles."


def test_source_record_serializer_tracks_all_pif_info_columns():
    firm = _firm()

    source_record = serialize_pif_source_record(firm)

    assert set(source_record) == {column.key for column in PifInfo.__mapper__.columns}


def test_sparse_firm_profile_includes_empty_optional_research_and_people_fields():
    firm = PifInfo(
        firm_name="Sparse Injury Law",
        entity_type="pi_law_firm",
        emails=[],
        phones=[],
        addresses=[],
        contacts=[],
        conversation_ids=[],
    )
    firm.id = uuid4()

    payload = build_firm_profile(firm).model_dump(mode="json")

    assert payload["research"]["founded_year"] is None
    assert payload["research"]["firm_size"] is None
    assert payload["research"]["office_locations"] == []
    assert payload["research"]["notable_cases"] == []
    assert payload["research"]["awards_recognition"] == []
    assert payload["research"]["bar_associations"] == []
    assert payload["research"]["social_media"] == {}
    assert payload["people"] == []


def test_updated_since_normalizes_aware_datetime_to_db_naive_utc():
    aware = datetime(2026, 7, 5, 2, 12, 26, 967126, tzinfo=timezone.utc)

    normalized = firm_intel_endpoint._as_db_naive_utc(aware)

    assert normalized == datetime(2026, 7, 5, 2, 12, 26, 967126)
    assert normalized.tzinfo is None


def test_updated_since_normalizes_non_utc_offset_to_db_naive_utc():
    aware = datetime.fromisoformat("2026-07-04T19:12:26.967126-07:00")

    normalized = firm_intel_endpoint._as_db_naive_utc(aware)

    assert normalized == datetime(2026, 7, 5, 2, 12, 26, 967126)
    assert normalized.tzinfo is None


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


def test_create_candidate_firm_with_unknown_domain_persists_firm_and_aliases(client, monkeypatch):
    observed = {}

    async def fake_resolve_domain_identity(db, normalized_domain):
        observed["resolved_domain"] = normalized_domain
        return None

    async def fake_insert_candidate_firm(db, candidate, *, canonical_website, domain_aliases):
        firm = PifInfo(
            firm_name=candidate.firm_name,
            entity_type="pi_law_firm",
            canonical_website=canonical_website,
            emails=[],
            phones=[],
            addresses=[],
            contacts=[],
            conversation_ids=[],
            extraction_notes=f"candidate created via {candidate.source}",
        )
        firm.id = uuid4()
        aliases = [
            FirmAlias(
                alias_type=alias_type,
                alias_value=alias_value,
                firm_id=firm.id,
                confidence=1.0,
                source=candidate.source,
            )
            for alias_type, alias_value in domain_aliases
        ]
        observed["firm"] = firm
        observed["aliases"] = aliases
        return firm

    monkeypatch.setattr(firm_intel_endpoint, "resolve_domain_identity", fake_resolve_domain_identity)
    monkeypatch.setattr(firm_intel_endpoint, "insert_candidate_firm", fake_insert_candidate_firm)

    response = client.post(
        "/api/v2/firm-intel/firms",
        headers=AUTH_HEADERS,
        json={
            "firm_name": "New Trial Lawyers",
            "website": "https://www.newtriallaw.com/contact",
            "email": "hello@newtriallaw.com",
            "source": "LexVisibility",
            "detail": {"scan_id": "scan_123"},
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["created"] is True
    assert payload["matched_by"] == "none"
    assert payload["canonical_website"] == "newtriallaw.com"
    assert payload["firm_id"] == str(observed["firm"].id)
    assert observed["resolved_domain"] == "newtriallaw.com"
    assert observed["firm"].firm_name == "New Trial Lawyers"
    assert observed["firm"].entity_type == "pi_law_firm"
    assert observed["firm"].emails == []
    assert observed["firm"].contacts == []
    assert observed["firm"].extraction_notes == "candidate created via lexvisibility"
    assert {(alias.alias_type, alias.alias_value) for alias in observed["aliases"]} == {
        ("domain", "newtriallaw.com"),
        ("email_domain", "newtriallaw.com"),
    }


def test_create_candidate_firm_is_idempotent_for_same_domain(client, monkeypatch):
    firm_id = uuid4()

    async def fake_resolve_domain_identity(db, normalized_domain):
        assert normalized_domain == "smithlaw.com"
        return firm_id, "canonical_domain", normalized_domain

    monkeypatch.setattr(firm_intel_endpoint, "resolve_domain_identity", fake_resolve_domain_identity)

    response = client.post(
        "/api/v2/firm-intel/firms",
        headers=AUTH_HEADERS,
        json={
            "firm_name": "Smith Law",
            "domain": "smithlaw.com",
            "source": "lexvisibility",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "firm_id": str(firm_id),
        "created": False,
        "matched_by": "alias",
        "canonical_website": "smithlaw.com",
    }


def test_create_candidate_firm_matches_by_canonical_website(client, monkeypatch):
    firm_id = uuid4()

    async def fake_resolve_domain_identity(db, normalized_domain):
        return firm_id, "canonical_website", normalized_domain

    monkeypatch.setattr(firm_intel_endpoint, "resolve_domain_identity", fake_resolve_domain_identity)

    response = client.post(
        "/api/v2/firm-intel/firms",
        headers=AUTH_HEADERS,
        json={
            "firm_name": "Smith Law",
            "website": "https://smithlaw.com",
            "source": "lexvisibility",
        },
    )

    assert response.status_code == 200
    assert response.json()["matched_by"] == "domain"
    assert response.json()["firm_id"] == str(firm_id)


def test_create_candidate_firm_name_only_create_and_exact_name_match(client, monkeypatch):
    created_firm_id = uuid4()
    existing_firm_id = uuid4()
    observed = {"name_lookups": 0}

    async def fake_find_active_firm_by_exact_name(db, firm_name):
        observed["name_lookups"] += 1
        if observed["name_lookups"] == 1:
            return None
        firm = PifInfo(
            firm_name=firm_name,
            entity_type="pi_law_firm",
            emails=[],
            phones=[],
            addresses=[],
            contacts=[],
            conversation_ids=[],
        )
        firm.id = existing_firm_id
        return firm

    async def fake_insert_candidate_firm(db, candidate, *, canonical_website, domain_aliases):
        assert canonical_website is None
        assert domain_aliases == []
        firm = PifInfo(
            firm_name=candidate.firm_name,
            entity_type="pi_law_firm",
            emails=[],
            phones=[],
            addresses=[],
            contacts=[],
            conversation_ids=[],
        )
        firm.id = created_firm_id
        return firm

    monkeypatch.setattr(
        firm_intel_endpoint,
        "find_active_firm_by_exact_name",
        fake_find_active_firm_by_exact_name,
    )
    monkeypatch.setattr(firm_intel_endpoint, "insert_candidate_firm", fake_insert_candidate_firm)

    create_response = client.post(
        "/api/v2/firm-intel/firms",
        headers=AUTH_HEADERS,
        json={"firm_name": "Name Only Law", "source": "lexvisibility"},
    )
    match_response = client.post(
        "/api/v2/firm-intel/firms",
        headers=AUTH_HEADERS,
        json={"firm_name": "Name Only Law", "source": "lexvisibility"},
    )

    assert create_response.status_code == 201
    assert create_response.json()["firm_id"] == str(created_firm_id)
    assert match_response.status_code == 200
    assert match_response.json()["created"] is False
    assert match_response.json()["matched_by"] == "name"
    assert match_response.json()["firm_id"] == str(existing_firm_id)


def test_create_candidate_firm_skips_vendor_and_consumer_domains_for_identity(
    client,
    monkeypatch,
):
    observed = {}

    async def fake_find_active_firm_by_exact_name(db, firm_name):
        observed["name_lookup"] = firm_name
        return None

    async def fake_insert_candidate_firm(db, candidate, *, canonical_website, domain_aliases):
        observed["canonical_website"] = canonical_website
        observed["domain_aliases"] = domain_aliases
        firm = PifInfo(
            firm_name=candidate.firm_name,
            entity_type="pi_law_firm",
            emails=[],
            phones=[],
            addresses=[],
            contacts=[],
            conversation_ids=[],
        )
        firm.id = uuid4()
        return firm

    monkeypatch.setattr(
        firm_intel_endpoint,
        "find_active_firm_by_exact_name",
        fake_find_active_firm_by_exact_name,
    )
    monkeypatch.setattr(firm_intel_endpoint, "insert_candidate_firm", fake_insert_candidate_firm)

    response = client.post(
        "/api/v2/firm-intel/firms",
        headers=AUTH_HEADERS,
        json={
            "firm_name": "Portal Only Law",
            "domain": "smithlaw.filevineapp.com",
            "email": "owner@gmail.com",
            "source": "lexvisibility",
        },
    )

    assert response.status_code == 201
    assert observed["name_lookup"] == "Portal Only Law"
    assert observed["canonical_website"] is None
    assert observed["domain_aliases"] == []
