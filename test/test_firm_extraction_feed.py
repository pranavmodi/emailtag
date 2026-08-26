import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.api_v2.endpoints.firm_intel import (
    _decode_extraction_cursor,
    _encode_extraction_cursor,
    _firm_extraction,
    list_firm_extractions,
)


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
        contacts=[
            {
                "name": "Alex",
                "email": "alex@examplelaw.com",
                "patient_name": "Must Not Cross Boundary",
            }
        ],
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
    assert extraction["contacts"] == [{"name": "Alex", "email": "alex@examplelaw.com"}]
    assert extraction["extraction_notes"] is None
    assert "canonical_website" not in extraction
    assert "research_data" not in extraction
    assert "leadership" not in extraction
    assert "vendor_stack" not in extraction


def test_extraction_cursor_round_trip_and_rejects_invalid_values():
    updated_at = datetime(2026, 8, 26, 9, 30, 15)
    firm_id = uuid4()

    cursor = _encode_extraction_cursor(updated_at, firm_id)

    assert _decode_extraction_cursor(cursor) == (updated_at, firm_id, 0)
    assert _decode_extraction_cursor("25") == (None, None, 25)
    with pytest.raises(HTTPException):
        _decode_extraction_cursor("not-a-valid-cursor")


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class _RowsResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class _FakeDb:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        if len(self.statements) == 1:
            return _ScalarResult(len(self.rows))
        return _RowsResult(self.rows)


def _extracted_firm(updated_at):
    return SimpleNamespace(
        id=uuid4(),
        firm_name="Cursor Firm",
        entity_type="pi_law_firm",
        website=None,
        emails=[],
        phones=[],
        fax=None,
        addresses=[],
        contacts=[],
        conversation_ids=["cnv_cursor"],
        extraction_notes=None,
        first_contacted_precise_at=None,
        merge_status="active",
        merged_into=None,
        created_at=updated_at,
        updated_at=updated_at,
    )


def test_extraction_feed_filters_to_conversation_backed_rows_and_emits_keyset_cursor():
    first = _extracted_firm(datetime(2026, 8, 26, 9, 0))
    second = _extracted_firm(first.updated_at + timedelta(minutes=1))
    db = _FakeDb([first, second])

    response = asyncio.run(
        list_firm_extractions(updated_since=None, cursor=None, limit=1, db=db)
    )

    assert [item.extraction_id for item in response.items] == [first.id]
    assert _decode_extraction_cursor(response.next_cursor) == (first.updated_at, first.id, 0)
    assert "cardinality(pif_info.conversation_ids)" in str(db.statements[0])
