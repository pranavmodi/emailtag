import asyncio
import uuid
from datetime import datetime
from types import SimpleNamespace

from app.api.api_v1.endpoints import bill_offers


def test_tagged_email_listing_endpoint(monkeypatch):
    email_id = uuid.uuid4()

    async def fake_list_tagged(db, skip, limit):
        email = SimpleNamespace(
            id=email_id,
            front_conversation_id="cnv_123",
            subject="Offer",
            sender="attorney@example.com",
            created_at=datetime(2026, 6, 1, 12, 0, 0),
        )
        return [{"email": email, "intake": None}], 1

    monkeypatch.setattr(bill_offers.crud, "list_tagged_bill_offer_emails", fake_list_tagged)

    response = asyncio.run(bill_offers.list_bill_offer_tagged_emails(db=None))

    assert response.total == 1
    assert response.items[0].front_conversation_id == "cnv_123"
    assert response.items[0].has_intake is False
    assert response.items[0].tags == ["Bill Offer"]


def test_conversation_log_endpoint(monkeypatch):
    log_id = uuid.uuid4()

    async def fake_list_logs(db, front_conversation_id, skip, limit):
        return [
            SimpleNamespace(
                id=log_id,
                front_conversation_id=front_conversation_id,
                email_id=None,
                intake_id=None,
                run_id="run-1",
                step_name="thread_loaded",
                step_status="completed",
                input_snapshot=None,
                output_snapshot={"thread_chars": 100},
                message=None,
                error=None,
                created_at=datetime(2026, 6, 1, 12, 0, 0),
            )
        ], 1

    monkeypatch.setattr(bill_offers.crud, "list_logs_for_conversation", fake_list_logs)

    response = asyncio.run(bill_offers.list_bill_offer_logs("cnv_123", db=None))

    assert response.total == 1
    assert response.items[0].step_name == "thread_loaded"
    assert response.items[0].output_snapshot == {"thread_chars": 100}


def test_manual_agent_trigger_endpoint(monkeypatch):
    email_id = uuid.uuid4()
    intake_id = uuid.uuid4()

    async def fake_get_email(db, front_conversation_id):
        return SimpleNamespace(
            id=email_id,
            front_conversation_id=front_conversation_id,
            subject="Offer",
            sender="attorney@example.com",
            content_text="We offer $500 toward Precise Imaging.",
            content_html=None,
            extracted_patient_ids=["PRE123456"],
            ocr_results=None,
            raw_data={},
        )

    async def fake_handle(**kwargs):
        return {
            "run_id": "run-1",
            "details": {"status": "pending_details"},
        }

    async def fake_get_intake(db, front_conversation_id):
        return SimpleNamespace(
            id=intake_id,
            front_conversation_id=front_conversation_id,
            email_id=email_id,
            status="pending_details",
            patient_id="PRE123456",
            patient_match={},
            patient_data={},
            extracted_facts={},
            corrected_facts={},
            missing_fields=["settlement_amount"],
            confidence={},
            original_sender_email="attorney@example.com",
            last_agent_action="drafted",
            last_run_id="run-1",
            last_agent_run_status="completed",
            reply_draft="Draft",
            reply_sent_at=None,
            reviewed_by=None,
            reviewed_at=None,
            created_at=datetime(2026, 6, 1, 12, 0, 0),
            updated_at=datetime(2026, 6, 1, 12, 0, 0),
        )

    monkeypatch.setattr(bill_offers.crud, "get_latest_bill_offer_email_for_conversation", fake_get_email)
    monkeypatch.setattr(bill_offers, "get_conversation_text", lambda conversation_id: {"_structured_messages": []})
    monkeypatch.setattr(bill_offers, "handle_bill_offer_request", fake_handle)
    monkeypatch.setattr(bill_offers.crud, "get_intake_by_conversation", fake_get_intake)

    response = asyncio.run(
        bill_offers.run_bill_offer_agent_for_conversation(
            "cnv_123",
            bill_offers.BillOfferRunAgentRequest(reviewed_by="Test", send_reply=False),
            db=None,
        )
    )

    assert response.run_id == "run-1"
    assert response.intake.front_conversation_id == "cnv_123"
    assert response.intake.last_agent_run_status == "completed"
