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
                    "referrer_id": "200",
                }
            ],
            "studies_with_participants": 1,
            "studies_without_participants": 0,
        }

    async def fake_contact_lookup(sender_email):
        return {
            "found": True,
            "email": sender_email,
            "referrer_ids": ["100"],
            "player_type_names": ["Attorney"],
            "error": None,
        }

    monkeypatch.setattr(agent_helpers, "compile_study_participants", fake_compile_study_participants)
    monkeypatch.setattr(agent_helpers, "verify_sender_via_radflow_contacts", fake_contact_lookup)

    result = asyncio.run(
        agent_helpers.verify_sender_for_patient_access(
            "PRE1244712", "amanda@newflexgroup.org", studies=[{"id": "study-1"}]
        )
    )

    assert result["authorized"] is False
    assert result["verification_status"] == "unverified"


def test_contact_is_authorized_when_referrer_matches_exam_participant(monkeypatch):
    async def fake_compile_study_participants(patient_id, studies):
        return {
            "success": True,
            "total_participants": 1,
            "participants": [
                {
                    "email": "bms@bellmedicalsolutions.com",
                    "domain": "bellmedicalsolutions.com",
                    "role": "broker",
                    "type": "doctor",
                    "referrer_id": "17090",
                    "accession_number": "1186212",
                }
            ],
            "studies_with_participants": 1,
            "studies_without_participants": 0,
        }

    async def fake_contact_lookup(sender_email):
        return {
            "found": True,
            "email": "btrejocmc@gmail.com",
            "referrer_ids": ["17090"],
            "player_type_names": ["Broker"],
            "error": None,
        }

    monkeypatch.setattr(agent_helpers, "compile_study_participants", fake_compile_study_participants)
    monkeypatch.setattr(agent_helpers, "verify_sender_via_radflow_contacts", fake_contact_lookup)

    result = asyncio.run(
        agent_helpers.verify_sender_for_patient_access(
            "PRE1258156", "btrejocmc@gmail.com", studies=[{"id": "study-1"}]
        )
    )

    assert result["authorized"] is True
    assert result["verification_status"] == "referrer_verified"
    assert result["role"] == "broker_contact_on_file"
    assert result["player_info"]["referrer_id"] == "17090"


def test_legacy_contact_response_without_referrer_id_is_not_authorized(monkeypatch):
    async def fake_compile_study_participants(patient_id, studies):
        return {
            "success": True,
            "total_participants": 1,
            "participants": [
                {
                    "email": "bms@bellmedicalsolutions.com",
                    "domain": "bellmedicalsolutions.com",
                    "role": "broker",
                    "type": "doctor",
                    "referrer_id": "17090",
                }
            ],
            "studies_with_participants": 1,
            "studies_without_participants": 0,
        }

    async def fake_contact_lookup(sender_email):
        return {
            "found": True,
            "email": sender_email,
            "referrer_ids": [],
            "player_type_names": [],
            "error": None,
        }

    monkeypatch.setattr(agent_helpers, "compile_study_participants", fake_compile_study_participants)
    monkeypatch.setattr(agent_helpers, "verify_sender_via_radflow_contacts", fake_contact_lookup)

    result = asyncio.run(
        agent_helpers.verify_sender_for_patient_access(
            "PRE1258156", "btrejocmc@gmail.com", studies=[{"id": "study-1"}]
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


def test_same_non_public_domain_is_authorized(monkeypatch):
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

    assert result["authorized"] is True
    assert result["verification_status"] == "domain_verified"
    assert result["role"] == "case_manager_domain_match"


def test_same_public_domain_without_exact_email_is_not_authorized(monkeypatch):
    async def fake_compile_study_participants(patient_id, studies):
        return {
            "success": True,
            "total_participants": 1,
            "participants": [
                {
                    "email": "assigned@gmail.com",
                    "domain": "gmail.com",
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
            "PRE1244712", "unassigned@gmail.com", studies=[{"id": "study-1"}]
        )
    )

    assert result["authorized"] is False
    assert result["verification_status"] == "unverified"
