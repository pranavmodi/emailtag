from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

from app.api.api_v2.endpoints.firm_intel import _firm_extraction


def test_firm_extraction_contains_source_facts_only():
    firm_id = uuid4()
    firm = SimpleNamespace(
        id=firm_id,
        firm_name="Example Injury Law",
        entity_type="pi_law_firm",
        website="https://examplelaw.com/contact",
        emails=["intake@examplelaw.com"],
        phones=["+13105551212"],
        fax=None,
        addresses=["Los Angeles, CA"],
        contacts=[{"name": "Alex", "email": "alex@examplelaw.com"}],
        conversation_ids=["cnv_1"],
        extraction_notes="Extracted from signature",
        first_contacted_precise_at=datetime(2026, 8, 25, 12, 0),
        merge_status="active",
        merged_into=None,
        created_at=datetime(2026, 8, 25, 12, 0),
        updated_at=datetime(2026, 8, 26, 9, 0),
        canonical_website="should-not-leak.example",
        research_data={"summary": "should not leak"},
        leadership=[{"name": "Should Not Leak"}],
        vendor_stack={"case_mgmt": "filevine"},
    )

    extraction = _firm_extraction(firm).model_dump()

    assert extraction["extraction_id"] == firm_id
    assert extraction["observed_website"] == "https://examplelaw.com/contact"
    assert extraction["emails"] == ["intake@examplelaw.com"]
    assert "canonical_website" not in extraction
    assert "research_data" not in extraction
    assert "leadership" not in extraction
    assert "vendor_stack" not in extraction
