from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.models.pif_info import PifInfo
from app.services.firm_enrichment import (
    compute_profile_completeness,
    enrich_firm_profile,
    run_external_pass,
)


class FakeDb:
    def __init__(self):
        self.added = []
        self.commits = 0
        self.refreshes = 0

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        self.refreshes += 1


def _firm(**overrides):
    base = {
        "id": uuid4(),
        "firm_name": "Smith Injury Law",
        "entity_type": "pi_law_firm",
        "website": None,
        "canonical_website": None,
        "website_status": None,
        "website_source": None,
        "website_confidence": None,
        "emails": ["owner@smithlaw.com"],
        "phones": ["555-111-2222"],
        "addresses": ["Los Angeles, CA"],
        "contacts": [],
        "conversation_ids": ["cnv_1"],
        "leadership": None,
        "research_data": None,
        "research_status": None,
        "staff": None,
        "behavioral_data": None,
        "icp_score": None,
        "icp_tier": None,
        "score_breakdown": None,
        "vendor_stack": None,
        "profile_completeness": None,
        "outreach_ready": False,
        "merge_status": "active",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    base.update(overrides)
    return PifInfo(**base)


def test_enrich_internal_pass_uses_single_corpus_parse_for_behavior_people_and_icp():
    calls = {"corpus": 0, "analyze": 0, "signature": 0, "score": 0, "research": 0}
    pif = _firm()
    corpus = [
        {
            "subject": "Status",
            "content_text": "Please send status.\n\nAlex Smith\nOwner",
            "sender": "Alex Smith <owner@smithlaw.com>",
            "created_at": datetime.utcnow() - timedelta(days=2),
        }
    ]

    def corpus_loader(db, firm):
        calls["corpus"] += 1
        return corpus

    def analyze_emails(emails):
        calls["analyze"] += 1
        assert emails is corpus
        return {
            "total_email_count": 1,
            "monthly_email_volume": [0, 0, 1],
            "last_contact_date": corpus[0]["created_at"].isoformat(),
            "days_since_last_contact": 2,
            "topic_distribution": {"status_update_request": 1},
            "primary_pain_point": "status_update_request",
            "sender_roles": {"unknown": 1},
            "peak_contact_days": ["Monday"],
            "after_hours_ratio": 0.0,
            "contact_profiles": {
                "owner@smithlaw.com": {
                    "name": "Alex Smith",
                    "persona": "unknown",
                    "role": "unknown",
                    "message_count": 1,
                }
            },
        }

    def extract_signature(sender, bodies):
        calls["signature"] += 1
        assert sender == "Alex Smith <owner@smithlaw.com>"
        return {
            "name": "Alex Smith",
            "title": "Owner",
            "direct_phone": "555-111-2222",
            "persona": "founder_owner",
        }

    def score_firm(payload):
        calls["score"] += 1
        assert payload["behavioral_data"]["contact_profiles"]["owner@smithlaw.com"]["signature"]
        assert payload["leadership"][0]["email"] == "owner@smithlaw.com"
        return {"icp_score": 82, "icp_tier": "A", "score_breakdown": {"total": 82}}

    def research_firm_profile(**kwargs):
        calls["research"] += 1
        return SimpleNamespace(
            canonical_website="https://smithlaw.com",
            website_confidence=0.91,
            firmographics={"size_hint": "5-30", "practice_areas": ["personal injury"]},
            leadership=[],
            vendor_stack={"case_mgmt": "filevine", "other": {}, "evidence": []},
            competitive_context={"summary": "Regional PI firm"},
            sources=["https://smithlaw.com"],
        )

    result = enrich_firm_profile(
        FakeDb(),
        pif,
        apply=True,
        corpus_loader=corpus_loader,
        analyze_emails=analyze_emails,
        extract_signature=extract_signature,
        score_firm=score_firm,
        research_firm_profile=research_firm_profile,
    )

    assert result.status == "completed"
    assert calls == {"corpus": 1, "analyze": 1, "signature": 1, "score": 1, "research": 1}
    assert pif.behavioral_data["primary_pain_point"] == "status_update_request"
    assert pif.leadership[0]["persona"] == "founder_owner"
    assert pif.icp_score == 82
    assert pif.icp_tier == "A"


def test_external_vendor_enrich_pass_is_one_web_search_and_returns_combined_profile():
    calls = {"search": 0}
    pif = _firm(canonical_website=None)

    def research_firm_profile(**kwargs):
        calls["search"] += 1
        assert kwargs["firm_name"] == "Smith Injury Law"
        return SimpleNamespace(
            canonical_website="https://www.smithlaw.com/about",
            website_confidence=0.88,
            firmographics={
                "size_hint": "10-20 attorneys",
                "practice_areas": ["personal injury", "wrongful death"],
                "case_mix": {"pi": 0.9},
                "metro": "los-angeles",
                "city": "Los Angeles",
                "state": "CA",
                "office_locations": ["Los Angeles"],
                "value_tier": "mid-market",
            },
            leadership=[
                SimpleNamespace(
                    model_dump=lambda: {
                        "name": "Alex Smith",
                        "title": "Managing Partner",
                        "email": "alex@smithlaw.com",
                        "phone": None,
                        "linkedin": None,
                        "bio": None,
                        "image_url": None,
                    }
                )
            ],
            vendor_stack={
                "case_mgmt": "casepeer",
                "other": {"intake": "evenup"},
                "evidence": [{"signal": "job posting mentions CASEpeer", "confidence": 0.8}],
            },
            competitive_context={"summary": "Competes with local PI boutiques"},
            sources=["https://smithlaw.com"],
        )

    updates = run_external_pass(pif, research_firm_profile=research_firm_profile)

    assert calls["search"] == 1
    assert updates["canonical_website"] == "smithlaw.com"
    assert updates["research_data"]["practice_areas"] == ["personal injury", "wrongful death"]
    assert updates["vendor_stack"]["case_mgmt"] == "casepeer"
    assert updates["leadership"][0]["email"] == "alex@smithlaw.com"
    assert updates["research_data"]["competitive_context"]["summary"]


def test_completeness_vendor_gate_requires_all_must_have_fields():
    pif = _firm(
        canonical_website="smithlaw.com",
        leadership=[
            {
                "name": "Alex Smith",
                "title": "Owner",
                "email": "alex@smithlaw.com",
                "persona": "founder_owner",
                "is_decision_maker": True,
            }
        ],
        behavioral_data={
            "total_email_count": 10,
            "monthly_email_volume": [2, 3, 5],
            "last_contact_date": datetime.utcnow().isoformat(),
            "days_since_last_contact": 3,
            "topic_distribution": {"records_request": 6, "status_update_request": 4},
            "primary_pain_point": "records_request",
            "sender_roles": {"founder_owner": 2, "records": 8},
            "contact_profiles": {"alex@smithlaw.com": {"persona": "founder_owner"}},
        },
        icp_tier="A",
        research_data={"size_hint": "5-30", "practice_areas": ["personal injury"]},
        vendor_stack={"case_mgmt": "filevine", "other": {}, "evidence": []},
    )

    complete = compute_profile_completeness(pif)
    assert complete.profile_completeness >= 8
    assert complete.outreach_ready is True

    pif.canonical_website = None
    incomplete = compute_profile_completeness(pif)
    assert "canonical_website" in incomplete.missing_must_have
    assert incomplete.outreach_ready is False
