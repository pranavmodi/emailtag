import asyncio

from app.agents import agent_helpers


def test_known_global_contact_without_patient_participant_is_not_authorized(monkeypatch):
    async def fake_compile_study_participants(patient_id, studies):
        return {
            "success": True,
            "total_participants": 1,
            "participants": [
                {
                    "email": "medical.management@example.com",
                    "domain": "example.com",
                    "role": "case manager",
                    "type": "case manager",
                }
            ],
            "studies_with_participants": 1,
            "studies_without_participants": 0,
        }

    async def global_lookup_must_not_run(sender_email):
        raise AssertionError("Global contact lookup must not authorize patient access")

    monkeypatch.setattr(agent_helpers, "compile_study_participants", fake_compile_study_participants)
    monkeypatch.setattr(agent_helpers, "verify_sender_via_radflow_contacts", global_lookup_must_not_run)

    result = asyncio.run(
        agent_helpers.verify_sender_for_patient_access(
            "PRE1244712", "amanda@newflexgroup.org", studies=[{"id": "study-1"}]
        )
    )

    assert result["authorized"] is False
    assert result["verification_status"] == "unverified"


def test_patient_participant_is_authorized_without_global_contact_lookup(monkeypatch):
    async def fake_compile_study_participants(patient_id, studies):
        return {
            "success": True,
            "total_participants": 1,
            "participants": [
                {
                    "email": "case.manager@medical.example",
                    "domain": "medical.example",
                    "role": "case manager",
                    "type": "case manager",
                    "accession_number": "1174833",
                }
            ],
            "studies_with_participants": 1,
            "studies_without_participants": 0,
        }

    async def global_lookup_must_not_run(sender_email):
        raise AssertionError("Global contact lookup must not be part of authorization")

    monkeypatch.setattr(agent_helpers, "compile_study_participants", fake_compile_study_participants)
    monkeypatch.setattr(agent_helpers, "verify_sender_via_radflow_contacts", global_lookup_must_not_run)

    result = asyncio.run(
        agent_helpers.verify_sender_for_patient_access(
            "PRE1244712", "case.manager@medical.example", studies=[{"id": "study-1"}]
        )
    )

    assert result["authorized"] is True
    assert result["verification_status"] == "verified"
    assert result["role"] == "case_manager_on_file"


def test_same_domain_without_exact_participant_email_is_not_authorized(monkeypatch):
    async def fake_compile_study_participants(patient_id, studies):
        return {
            "success": True,
            "total_participants": 1,
            "participants": [
                {
                    "email": "assigned@medical.example",
                    "domain": "medical.example",
                    "role": "case manager",
                    "type": "case manager",
                }
            ],
            "studies_with_participants": 1,
            "studies_without_participants": 0,
        }

    monkeypatch.setattr(agent_helpers, "compile_study_participants", fake_compile_study_participants)

    result = asyncio.run(
        agent_helpers.verify_sender_for_patient_access(
            "PRE1244712", "unassigned@medical.example", studies=[{"id": "study-1"}]
        )
    )

    assert result["authorized"] is False
    assert result["verification_status"] == "unverified"
