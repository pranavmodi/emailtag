from datetime import datetime

from pifstats.src import email_analyzer


def test_contact_profiles_preserve_firm_sender_identity_and_exclude_consumers(monkeypatch):
    def fake_classify(snippets, include_persona=False):
        assert include_persona is True
        return [
            {"category": "records_request", "sender_persona": "records"},
            {"category": "status_update_request", "sender_persona": "case_manager"},
            {"category": "billing_dispute", "sender_persona": "unknown"},
        ]

    monkeypatch.setattr(email_analyzer, "classify_emails_batch", fake_classify)

    result = email_analyzer.analyze_firm_emails(
        [
            {
                "subject": "Records request",
                "content_text": "Please send records.",
                "sender": "Maria Records <maria@firm-example.com>",
                "created_at": datetime(2026, 6, 1, 10, 0, 0),
            },
            {
                "subject": "Case status",
                "content_text": "Any update?",
                "sender": "Sam Case <sam@firm-example.com>",
                "created_at": datetime(2026, 6, 2, 19, 0, 0),
            },
            {
                "subject": "My appointment",
                "content_text": "This is about my case.",
                "sender": "Patient Person <patient@gmail.com>",
                "created_at": datetime(2026, 6, 3, 11, 0, 0),
            },
        ]
    )

    profiles = result["contact_profiles"]
    assert set(profiles) == {"maria@firm-example.com", "sam@firm-example.com"}
    assert profiles["maria@firm-example.com"]["name"] == "Maria Records"
    assert profiles["maria@firm-example.com"]["role"] == "records"
    assert profiles["maria@firm-example.com"]["topic_mix"] == {"records_request": 1}
    assert profiles["sam@firm-example.com"]["after_hours_ratio"] == 1.0
    assert "patient@gmail.com" not in profiles
    assert result["sender_roles"]["records"] == 1
    assert result["sender_roles"]["case_manager"] == 1


def test_persona_fallback_mapping_uses_autocaller_taxonomy():
    assert email_analyzer.detect_sender_role("", "Jamie Founder, Owner") == "founder_owner"
    assert email_analyzer.detect_sender_role("", "Alex, Managing Partner") == "managing_partner"
    assert email_analyzer.detect_sender_role("", "Riley, Intake Coordinator") == "intake"
    assert email_analyzer.detect_sender_role("", "Taylor Esq.") == "attorney"
    assert email_analyzer.normalize_sender_persona("medical_records") == "records"
    assert email_analyzer.normalize_sender_persona("legal_assistant") == "case_manager"
