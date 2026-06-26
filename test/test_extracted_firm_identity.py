from app.models.pif_info import PifInfo
from app.services.extracted_firm_identity import (
    extracted_identity_domains,
    merge_extracted_firm_data,
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
