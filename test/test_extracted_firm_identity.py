from datetime import datetime, timedelta
from uuid import uuid4

from app.models.pif_info import PifInfo
from app.services.extracted_firm_identity import (
    extracted_identity_domains,
    merge_extracted_firm_data,
    resolve_extracted_firm_identity,
)
from app.services.website_resolution import WebsiteResolutionResult
from app.tasks.pif_extraction import (
    queue_full_firm_enrichment,
    queue_job_postings_research,
    should_queue_full_enrichment,
    should_queue_job_postings_research,
)


def test_extracted_identity_domains_prefers_website_and_rejects_consumer_domains():
    domains = extracted_identity_domains(
        website="https://www.smithlaw.com/contact",
        emails=["case.manager@gmail.com", "intake@smithlaw.com"],
        contacts=[
            {"name": "Maria", "email": "maria@smithlaw.com"},
            {"name": "Alex", "email": "alex@filevineapp.com"},
        ],
    )

    assert domains == ["smithlaw.com"]


def test_downstream_queue_helpers_are_noops_when_disabled(monkeypatch):
    import app.tasks.pif_extraction as pif_extraction

    class FailDb:
        def add(self, obj):
            raise AssertionError("disabled queue helper must not update the database")

        def commit(self):
            raise AssertionError("disabled queue helper must not commit")

    firm = PifInfo(
        id=uuid4(),
        firm_name="Smith Law",
        entity_type="pi_law_firm",
        emails=[],
        phones=[],
        addresses=[],
        contacts=[],
        conversation_ids=["cnv_1"],
        merge_status="active",
    )
    monkeypatch.setattr(
        pif_extraction.settings,
        "PIF_DOWNSTREAM_ENRICHMENT_ENABLED",
        False,
    )

    assert queue_job_postings_research(FailDb(), firm) is None
    assert queue_full_firm_enrichment(FailDb(), firm) is None


def test_merge_extracted_firm_data_merges_without_duplicate_values():
    firm = PifInfo(
        firm_name="Smith Law",
        entity_type="pi_law_firm",
        website=None,
        emails=["intake@smithlaw.com"],
        phones=["555-0100"],
        addresses=[],
        contacts=[],
        conversation_ids=["cnv_1"],
        merge_status="active",
    )

    merge_extracted_firm_data(
        firm,
        firm_name="Smith Law",
        website="https://smithlaw.com",
        emails=["intake@smithlaw.com", "records@smithlaw.com"],
        phones=["555-0100", "555-0101"],
        fax="555-0199",
        addresses=["100 Main St"],
        contacts=[],
        conversation_id="cnv_2",
        extraction_notes="Signature block",
    )

    assert firm.website == "https://smithlaw.com"
    assert firm.emails == ["intake@smithlaw.com", "records@smithlaw.com"]
    assert firm.phones == ["555-0100", "555-0101"]
    assert firm.fax == "555-0199"
    assert firm.addresses == ["100 Main St"]
    assert firm.conversation_ids == ["cnv_1", "cnv_2"]
    assert firm.extraction_notes == "Signature block"


def test_merge_extracted_firm_data_merges_contacts_by_email():
    firm = PifInfo(
        firm_name="Smith Law",
        entity_type="pi_law_firm",
        emails=[],
        phones=[],
        addresses=[],
        contacts=[
            {
                "name": "Maria Lopez",
                "title": "",
                "email": "maria@smithlaw.com",
                "phone": "",
            }
        ],
        conversation_ids=[],
        merge_status="active",
    )

    merge_extracted_firm_data(
        firm,
        firm_name="Smith Law",
        website=None,
        emails=[],
        phones=[],
        fax=None,
        addresses=[],
        contacts=[
            {
                "name": "Maria Lopez",
                "title": "Case Manager",
                "email": "maria@smithlaw.com",
                "phone": "555-0100",
            }
        ],
        conversation_id="cnv_1",
    )

    assert firm.contacts == [
        {
            "name": "Maria Lopez",
            "title": "Case Manager",
            "email": "maria@smithlaw.com",
            "phone": "555-0100",
        }
    ]


def test_resolved_website_is_used_before_name_fallback(monkeypatch):
    firm = PifInfo(
        id=uuid4(),
        firm_name="Resolved Injury Law",
        entity_type="pi_law_firm",
        canonical_website="resolvedlaw.com",
        emails=[],
        phones=[],
        addresses=[],
        contacts=[],
        conversation_ids=[],
        merge_status="active",
    )

    class FakeDb:
        def add(self, obj):
            pass

        def flush(self):
            pass

    def fake_resolve_website(probe, **kwargs):
        return WebsiteResolutionResult(
            canonical_website="resolvedlaw.com",
            website_status="resolved",
            website_source="web_search",
            website_confidence=0.78,
        )

    def fake_find_existing(db, *, firm_name, domains):
        assert domains[0] == "resolvedlaw.com"
        return firm, "canonical_website"

    monkeypatch.setattr(
        "app.services.extracted_firm_identity.resolve_firm_website",
        fake_resolve_website,
    )
    monkeypatch.setattr(
        "app.services.extracted_firm_identity._find_existing_firm",
        fake_find_existing,
    )
    monkeypatch.setattr(
        "app.services.extracted_firm_identity.persist_aliases_for_firm",
        lambda db, pif: None,
    )
    monkeypatch.setattr(
        "app.services.extracted_firm_identity.refresh_first_contacted_precise_at_sync",
        lambda db, pif: None,
    )

    result = resolve_extracted_firm_identity(
        FakeDb(),
        firm_name="Resolved Injury Law",
        website=None,
        emails=[],
        phones=[],
        fax=None,
        addresses=[],
        contacts=[],
        conversation_id="cnv_1",
    )

    assert result.pif is firm
    assert result.mapped_via == "canonical_website"


def test_website_owned_by_other_active_firm_is_not_reassigned(monkeypatch):
    selected = PifInfo(
        id=uuid4(),
        firm_name="BD&J",
        entity_type="pi_law_firm",
        website=None,
        canonical_website="bdj.com",
        emails=[],
        phones=[],
        addresses=[],
        contacts=[],
        conversation_ids=[],
        merge_status="active",
    )
    website_owner = PifInfo(
        id=uuid4(),
        firm_name="BD&J, PC",
        entity_type="pi_law_firm",
        website="www.bdj.com",
        canonical_website="precisemri.com",
        emails=[],
        phones=[],
        addresses=[],
        contacts=[],
        conversation_ids=[],
        merge_status="active",
    )

    class FakeDb:
        def add(self, obj):
            pass

        def flush(self):
            pass

    def fake_resolve_website(probe, **kwargs):
        return WebsiteResolutionResult(
            canonical_website="bdj.com",
            website_status="resolved",
            website_source="email_verified",
            website_confidence=0.9,
        )

    def fake_find_existing(db, *, firm_name, domains):
        assert domains[0] == "bdj.com"
        return selected, "canonical_website"

    def fake_find_website_owner(db, website, *, exclude_id=None):
        assert website == "www.bdj.com"
        if exclude_id == selected.id:
            return website_owner
        return website_owner

    monkeypatch.setattr(
        "app.services.extracted_firm_identity.resolve_firm_website",
        fake_resolve_website,
    )
    monkeypatch.setattr(
        "app.services.extracted_firm_identity._find_existing_firm",
        fake_find_existing,
    )
    monkeypatch.setattr(
        "app.services.extracted_firm_identity._find_website_owner",
        fake_find_website_owner,
    )
    monkeypatch.setattr(
        "app.services.extracted_firm_identity.persist_aliases_for_firm",
        lambda db, pif: None,
    )
    monkeypatch.setattr(
        "app.services.extracted_firm_identity.refresh_first_contacted_precise_at_sync",
        lambda db, pif: None,
    )

    result = resolve_extracted_firm_identity(
        FakeDb(),
        firm_name="BD&J",
        website="www.bdj.com",
        emails=["case@bdj.com"],
        phones=[],
        fax=None,
        addresses=[],
        contacts=[],
        conversation_id="cnv_new",
    )

    assert result.pif is selected
    assert result.mapped_via == "canonical_website"
    assert selected.website is None
    assert selected.emails == ["case@bdj.com"]
    assert selected.conversation_ids == ["cnv_new"]


def test_full_enrichment_needed_for_missing_or_stale_research():
    fresh = PifInfo(
        firm_name="Fresh Firm",
        entity_type="pi_law_firm",
        research_status="completed",
        research_data={"sources": ["example"]},
        last_researched_at=datetime.utcnow() - timedelta(days=4),
    )
    stale = PifInfo(
        firm_name="Stale Firm",
        entity_type="pi_law_firm",
        research_status="completed",
        research_data={"sources": ["example"]},
        last_researched_at=datetime.utcnow() - timedelta(days=31),
    )
    missing = PifInfo(
        firm_name="Missing Firm",
        entity_type="pi_law_firm",
        research_status=None,
        research_data=None,
    )
    running = PifInfo(
        firm_name="Running Firm",
        entity_type="pi_law_firm",
        research_status="queued",
        research_data=None,
    )

    assert should_queue_full_enrichment(fresh) is False
    assert should_queue_full_enrichment(stale) is True
    assert should_queue_full_enrichment(missing) is True
    assert should_queue_full_enrichment(running) is False


def test_job_posting_research_has_independent_daily_freshness():
    now = datetime.utcnow()
    firm = PifInfo(
        firm_name="Fresh Firm",
        entity_type="pi_law_firm",
        research_status="completed",
        research_data={"sources": ["example"]},
        last_researched_at=now - timedelta(days=4),
    )

    assert should_queue_full_enrichment(firm, now=now) is False
    assert should_queue_job_postings_research(firm, now=now) is True

    firm.job_postings_research_status = "completed"
    firm.last_job_postings_researched_at = now - timedelta(hours=12)
    assert should_queue_job_postings_research(firm, now=now) is False

    firm.last_job_postings_researched_at = now - timedelta(days=1)
    assert should_queue_job_postings_research(firm, now=now) is True

    firm.job_postings_research_status = "queued"
    assert should_queue_job_postings_research(firm, now=now) is False
