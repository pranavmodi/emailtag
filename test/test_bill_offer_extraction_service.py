from app.services.bill_offer_extraction_service import (
    build_bill_offer_context,
    compute_missing_fields,
    extract_bill_offer_facts,
    extract_bill_offer_facts_structured,
    merge_effective_facts,
    _normalize_llm_response,
)


def test_extracts_required_bill_offer_facts():
    text = """
    Patient: Jane Doe DOB 06/12/1985.
    Settlement is $30,000. Total medical bills across all providers are $45,000.
    No med-pay coverage is available. We offer $500 toward Precise Imaging's lien.
    """

    facts = extract_bill_offer_facts(text)

    assert facts["settlement_amount"]["value"] == 30000
    assert facts["total_medical_bills"]["value"] == 45000
    assert "No med-pay" in facts["medpay_status"]["value"]
    assert facts["precise_offer_amount"]["value"] == 500
    assert compute_missing_fields(facts) == []


def test_missing_precise_offer_is_prioritized():
    facts = extract_bill_offer_facts(
        "Settlement is $30,000. Total medical bills are $45,000. No med-pay."
    )

    assert compute_missing_fields(facts) == ["precise_offer_amount"]


def test_corrected_facts_override_extracted_facts():
    extracted = {
        "settlement_amount": {"value": 30000, "confidence": 0.7},
        "total_medical_bills": {"value": 45000, "confidence": 0.7},
        "medpay_status": {"value": "Unknown med-pay", "confidence": 0.5},
    }
    corrected = {
        "precise_offer_amount": {"value": 500, "source": "user_correction"},
        "settlement_amount": {"value": 35000, "source": "user_correction"},
    }

    effective = merge_effective_facts(extracted, corrected)

    assert effective["settlement_amount"]["value"] == 35000
    assert effective["precise_offer_amount"]["value"] == 500
    assert compute_missing_fields(effective) == []


def test_normalizes_llm_response_with_document_facts():
    facts = _normalize_llm_response(
        {
            "facts": {
                "settlement_amount": {
                    "value": "$30,000",
                    "evidence": "Settlement is $30,000",
                    "source": "email_body",
                    "source_id": "msg_1",
                    "confidence": 0.91,
                    "is_ambiguous": False,
                    "ambiguity_notes": "",
                },
                "total_medical_bills": {
                    "value": 45000,
                    "evidence": "Medical bills are $45,000",
                    "source": "attachment_document",
                    "source_id": "att_1",
                    "confidence": 0.88,
                    "is_ambiguous": False,
                    "ambiguity_notes": "",
                },
                "medpay_status": {
                    "value": "No med-pay available",
                    "evidence": "No med-pay available",
                    "source": "ocr_text",
                    "source_id": "ocr_1",
                    "confidence": 0.86,
                    "is_ambiguous": False,
                    "ambiguity_notes": "",
                },
                "precise_offer_amount": {
                    "value": "$500",
                    "evidence": "Offer $500 toward Precise Imaging",
                    "source": "prior_thread_message",
                    "source_id": "msg_2",
                    "confidence": 0.96,
                    "is_ambiguous": False,
                    "ambiguity_notes": "",
                },
            },
            "document_facts": [
                {
                    "document_id": "ocr_1",
                    "filename": "offer.pdf",
                    "document_type": "offer",
                    "page": 1,
                    "extracted_fields": [],
                    "patient_identifiers": ["PRE123456"],
                    "notes": "contains offer details",
                }
            ],
            "conflicts": [],
            "summary": "Complete offer.",
        }
    )

    assert facts["settlement_amount"]["value"] == 30000
    assert facts["precise_offer_amount"]["source_id"] == "msg_2"
    assert facts["_document_facts"][0]["filename"] == "offer.pdf"
    assert compute_missing_fields(facts) == []


def test_ambiguous_precise_offer_counts_as_missing():
    facts = {
        "settlement_amount": {"value": 30000},
        "total_medical_bills": {"value": 45000},
        "medpay_status": {"value": "No med-pay"},
        "precise_offer_amount": {
            "value": 500,
            "is_ambiguous": True,
            "ambiguity_notes": "Amount may refer to a different provider",
        },
    }

    assert compute_missing_fields(facts) == ["precise_offer_amount"]


def test_structured_extraction_falls_back_when_llm_fails(monkeypatch):
    def fake_call(_context):
        raise RuntimeError("bad response")

    monkeypatch.setattr(
        "app.services.bill_offer_extraction_service.call_llm_for_bill_offer_extraction",
        fake_call,
    )
    context = build_bill_offer_context(
        front_conversation_id="cnv_123",
        current_email_content=(
            "Settlement is $30,000. Total medical bills are $45,000. "
            "No med-pay. We offer $500 toward Precise Imaging's lien."
        ),
        structured_history_messages=[],
        ocr_results=None,
        raw_data={},
        email_subject="Offer",
        email_sender="attorney@example.com",
        extracted_patient_ids=[],
    )

    facts = extract_bill_offer_facts_structured(context)

    assert facts["precise_offer_amount"]["value"] == 500
    assert facts["_meta"]["fallback_used"] is True


def test_context_includes_prior_messages_and_ocr_documents():
    context = build_bill_offer_context(
        front_conversation_id="cnv_123",
        current_email_content="Current reply",
        structured_history_messages=[
            {
                "id": "msg_old",
                "author_email": "attorney@example.com",
                "created_at": "2026-06-01",
                "body": "Patient PRE123456",
            }
        ],
        ocr_results=[
            {
                "id": "doc_1",
                "filename": "offer.pdf",
                "text": "Total medical bills across all providers are $45,000.",
            }
        ],
        raw_data={"attachments": [{"id": "att_1", "filename": "offer.pdf"}]},
        email_subject="Offer",
        email_sender="attorney@example.com",
        extracted_patient_ids=["PRE123456"],
    )

    assert context["messages"][0]["source"] == "prior_thread_message"
    assert "PRE123456" in context["thread_text"]
    assert context["documents"][0]["filename"] == "offer.pdf"
    assert context["attachments"][0]["id"] == "att_1"
