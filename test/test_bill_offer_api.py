import asyncio
import uuid
from datetime import datetime
from types import SimpleNamespace

from app.api.api_v1.endpoints import bill_offers
from app.agents.bill_offer_agent import resolve_patient


class DummyRunLogger:
    def __init__(self):
        self.logs = []

    async def log(self, *args, **kwargs):
        self.logs.append((args, kwargs))


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


def test_tagged_email_listing_resolves_document_source_names(monkeypatch):
    email_id = uuid.uuid4()
    intake_id = uuid.uuid4()

    async def fake_list_tagged(db, skip, limit):
        email = SimpleNamespace(
            id=email_id,
            front_conversation_id="cnv_123",
            subject="Offer",
            sender="attorney@example.com",
            created_at=datetime(2026, 6, 1, 12, 0, 0),
        )
        intake = SimpleNamespace(
            id=intake_id,
            front_conversation_id="cnv_123",
            email_id=email_id,
            status="pending_details",
            patient_id="PRE123456",
            patient_match={},
            patient_data={},
            extracted_facts={
                "precise_offer_amount": {
                    "value": 1817.95,
                    "source": "attachment_document",
                    "source_id": "ocr_1",
                    "confidence": 0.95,
                    "evidence": "REDUCTION LETTER (ocr_1) supports this. ocr_2 confirms.",
                    "ambiguity_notes": "",
                },
                "_document_facts": [
                    {
                        "document_id": "ocr_1",
                        "filename": "REDUCTION LETTER.docx",
                        "extracted_fields": [],
                    },
                    {
                        "document_id": "ocr_2",
                        "filename": "Yield Calculator.pdf",
                        "extracted_fields": [],
                    },
                ],
                "_conflicts": [
                    {
                        "field": "settlement_amount",
                        "description": "ocr_1 conflicts with ocr_2",
                        "sources": ["ocr_1", "ocr_2"],
                    }
                ],
                "_meta": {"summary": "Found in ocr_1 and ocr_2"},
            },
            corrected_facts={},
            missing_fields=["medpay_status"],
            confidence={},
            original_sender_email="attorney@example.com",
            last_agent_action="drafted",
            last_run_id="run-1",
            last_agent_run_status="completed",
            reply_draft=None,
            reply_sent_at=None,
            reviewed_by=None,
            reviewed_at=None,
            created_at=datetime(2026, 6, 1, 12, 0, 0),
            updated_at=datetime(2026, 6, 1, 12, 0, 0),
        )
        return [{"email": email, "intake": intake}], 1

    monkeypatch.setattr(bill_offers.crud, "list_tagged_bill_offer_emails", fake_list_tagged)

    response = asyncio.run(bill_offers.list_bill_offer_tagged_emails(db=None))

    facts = response.items[0].intake.extracted_facts
    assert facts["precise_offer_amount"]["source_id"] == "REDUCTION LETTER.docx"
    assert "REDUCTION LETTER.docx" in facts["precise_offer_amount"]["evidence"]
    assert "Yield Calculator.pdf" in facts["precise_offer_amount"]["evidence"]
    assert facts["_conflicts"][0]["sources"] == ["REDUCTION LETTER.docx", "Yield Calculator.pdf"]
    assert facts["_meta"]["summary"] == "Found in REDUCTION LETTER.docx and Yield Calculator.pdf"


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
    queued = {}

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

    async def fake_upsert(db, front_conversation_id, values):
        queued["upsert"] = values
        return SimpleNamespace(
            id=intake_id,
            front_conversation_id=front_conversation_id,
            email_id=email_id,
            status="pending_patient",
            patient_id=None,
            patient_match={},
            patient_data={},
            extracted_facts={},
            corrected_facts={},
            missing_fields=[],
            confidence={},
            original_sender_email="attorney@example.com",
            last_agent_action="queued",
            last_run_id=values["last_run_id"],
            last_agent_run_status="queued",
            reply_draft=None,
            reply_sent_at=None,
            reviewed_by=None,
            reviewed_at=None,
            created_at=datetime(2026, 6, 1, 12, 0, 0),
            updated_at=datetime(2026, 6, 1, 12, 0, 0),
        )

    async def fake_create_log(db, obj_in):
        queued["log"] = obj_in
        return SimpleNamespace(id=uuid.uuid4(), **obj_in.model_dump(), created_at=datetime.utcnow())

    async def fake_get_intake(db, front_conversation_id):
        return SimpleNamespace(
            id=intake_id,
            front_conversation_id=front_conversation_id,
            email_id=email_id,
            status="pending_patient",
            patient_id=None,
            patient_match={},
            patient_data={},
            extracted_facts={},
            corrected_facts={},
            missing_fields=[],
            confidence={},
            original_sender_email="attorney@example.com",
            last_agent_action="queued",
            last_run_id=queued["upsert"]["last_run_id"],
            last_agent_run_status="queued",
            reply_draft=None,
            reply_sent_at=None,
            reviewed_by=None,
            reviewed_at=None,
            created_at=datetime(2026, 6, 1, 12, 0, 0),
            updated_at=datetime(2026, 6, 1, 12, 0, 0),
        )

    class FakeTask:
        id = "celery-task-1"

    def fake_apply_async(**kwargs):
        queued["task"] = kwargs
        return FakeTask()

    monkeypatch.setattr(bill_offers.crud, "get_latest_bill_offer_email_for_conversation", fake_get_email)
    monkeypatch.setattr(bill_offers.crud, "upsert_intake_for_conversation", fake_upsert)
    monkeypatch.setattr(bill_offers.crud, "create_log", fake_create_log)
    monkeypatch.setattr(bill_offers.crud, "get_intake_by_conversation", fake_get_intake)
    monkeypatch.setattr(bill_offers.run_bill_offer_agent_task, "apply_async", fake_apply_async)

    response = asyncio.run(
        bill_offers.run_bill_offer_agent_for_conversation(
            "cnv_123",
            bill_offers.BillOfferRunAgentRequest(reviewed_by="Test", send_reply=False),
            db=None,
        )
    )

    assert response.status == "queued"
    assert response.details == {"task_id": "celery-task-1", "queued": True}
    assert response.intake.front_conversation_id == "cnv_123"
    assert response.intake.last_agent_run_status == "queued"
    assert queued["task"]["queue"] == "processing"
    assert queued["task"]["kwargs"]["email_id"] == str(email_id)
    assert queued["task"]["kwargs"]["run_id"] == response.run_id
    assert queued["log"].step_name == "manual_run_queued"


def test_correction_audit_endpoint(monkeypatch):
    audit_id = uuid.uuid4()
    intake_id = uuid.uuid4()

    async def fake_list_audits(db, front_conversation_id, skip, limit):
        return [
            SimpleNamespace(
                id=audit_id,
                front_conversation_id=front_conversation_id,
                intake_id=intake_id,
                field_name="precise_offer_amount",
                previous_value={"value": 400},
                new_value={"value": 500},
                changed_by="Settings2",
                created_at=datetime(2026, 6, 1, 12, 0, 0),
            )
        ], 1

    monkeypatch.setattr(bill_offers.crud, "list_correction_audits_for_conversation", fake_list_audits)

    response = asyncio.run(bill_offers.list_bill_offer_correction_audits("cnv_123", db=None))

    assert response.total == 1
    assert response.items[0].field_name == "precise_offer_amount"
    assert response.items[0].new_value == {"value": 500}


def test_bill_offer_review_required_settings_endpoint(monkeypatch):
    async def fake_get_setting(db, setting_key, default):
        assert setting_key == "autorespond_bill_offer_review_required"
        return False

    monkeypatch.setattr(bill_offers.system_settings_crud, "get_setting_value", fake_get_setting)

    response = asyncio.run(bill_offers.get_bill_offer_settings(db=None))

    assert response.review_required is False


def test_patient_lookup_uses_prior_thread_text_patient_id():
    patient_id, match = asyncio.run(
        resolve_patient(
            thread_text="Prior message: Patient PRE123456. Current message: please review offer.",
            extracted_patient_ids=[],
            run_logger=DummyRunLogger(),
        )
    )

    assert patient_id == "PRE123456"
    assert match["method"] == "thread_text_patient_id"


def test_patient_lookup_uses_document_fact_name_and_dob(monkeypatch):
    calls = []

    async def fake_call_mcp_tool(tool_name, arguments):
        calls.append((tool_name, arguments))
        return {
            "patients": [
                {"patient_id": "PRE999111", "first_name": "Maira", "last_name": "Romo"}
            ]
        }

    monkeypatch.setattr("app.agents.bill_offer_agent.call_mcp_tool", fake_call_mcp_tool)

    patient_id, match = asyncio.run(
        resolve_patient(
            thread_text="Current email asks for lien reduction without patient demographics.",
            extracted_patient_ids=[],
            extracted_facts={
                "_document_facts": [
                    {
                        "document_id": "ocr_1",
                        "filename": "Maira Romo - Precise.pdf",
                        "extracted_fields": [
                            {"field": "patient_name", "value": "Maira Romo"},
                            {"field": "patient_dob", "value": "03/29/1993"},
                            {"field": "date_of_loss", "value": "05/31/2021"},
                        ],
                        "patient_identifiers": [
                            "Maira Romo",
                            "DOB: 03/29/1993",
                            "DOL: 05/31/2021",
                        ],
                    }
                ]
            },
            run_logger=DummyRunLogger(),
        )
    )

    assert patient_id == "PRE999111"
    assert match["method"] == "document_fact_name_dob"
    assert calls[0] == (
        "fetch_patient_by_name_and_dob",
        {"firstName": "Maira", "lastName": "Romo", "dob": "1993-03-29"},
    )
