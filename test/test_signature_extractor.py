from pifstats.src.signature_extractor import (
    contains_patient_context,
    filter_signature_payload,
)


def test_signature_post_filter_drops_patient_context_values():
    filtered = filter_signature_payload(
        {
            "name": "Jordan Records",
            "title": "Records Coordinator, DOB 01/01/1980",
            "direct_phone": "Claim # ABC123",
            "persona": "medical_records",
        }
    )

    assert filtered["name"] == "Jordan Records"
    assert filtered["title"] == ""
    assert filtered["direct_phone"] == ""
    assert filtered["persona"] == "records"
    assert contains_patient_context("DOL 06/01/2026") is True
