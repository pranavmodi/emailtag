from app.services.bill_offer_extraction_service import (
    compute_missing_fields,
    extract_bill_offer_facts,
    merge_effective_facts,
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
