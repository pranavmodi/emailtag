import json
from datetime import date

from pifstats.src import firm_researcher


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_recent_job_postings_are_date_filtered_and_deduplicated(monkeypatch):
    postings = [
        {
            "title": "Intake Specialist",
            "location": "Los Angeles, CA",
            "employment_type": "Full-time",
            "posted_date": "2026-08-15",
            "description_summary": "Handles new client intake.",
            "responsibilities": ["Answer prospective-client calls"],
            "qualifications": ["One year of intake experience"],
            "source_name": "Firm careers page",
            "source_url": "https://examplefirm.com/careers/intake-specialist",
        },
        {
            "title": "Intake Specialist",
            "location": "Los Angeles, CA",
            "employment_type": "Full-time",
            "posted_date": "2026-08-15",
            "description_summary": "Duplicate result.",
            "responsibilities": [],
            "qualifications": [],
            "source_name": "Firm careers page",
            "source_url": "https://examplefirm.com/careers/intake-specialist",
        },
        {
            "title": "Old Attorney Opening",
            "location": None,
            "employment_type": None,
            "posted_date": "2026-06-01",
            "description_summary": "Outside the requested window.",
            "responsibilities": [],
            "qualifications": [],
            "source_name": "Job board",
            "source_url": "https://jobs.example.com/old-opening",
        },
    ]
    response_payload = {
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": json.dumps({"postings": postings})}
                ],
            }
        ]
    }
    captured = {}

    def fake_post(client, url, headers, payload):
        captured["payload"] = payload
        return FakeResponse(response_payload)

    monkeypatch.setattr(firm_researcher.httpx, "Client", FakeClient)
    monkeypatch.setattr(firm_researcher, "_post_openai_with_retry", fake_post)

    result = firm_researcher.research_recent_job_postings(
        "Example Injury Law",
        "examplefirm.com",
        as_of_date=date(2026, 8, 22),
    )

    assert result is not None
    assert result["window_start"] == "2026-07-24"
    assert result["window_end"] == "2026-08-22"
    assert result["has_recent_openings"] is True
    assert [posting["title"] for posting in result["postings"]] == ["Intake Specialist"]
    assert "2026-07-24" in captured["payload"]["input"][1]["content"]


def test_recent_job_postings_store_a_negative_result(monkeypatch):
    response_payload = {
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": json.dumps({"postings": []})}
                ],
            }
        ]
    }

    monkeypatch.setattr(firm_researcher.httpx, "Client", FakeClient)
    monkeypatch.setattr(
        firm_researcher,
        "_post_openai_with_retry",
        lambda client, url, headers, payload: FakeResponse(response_payload),
    )

    result = firm_researcher.research_recent_job_postings(
        "No Jobs Firm",
        as_of_date=date(2026, 8, 22),
    )

    assert result is not None
    assert result["has_recent_openings"] is False
    assert result["postings"] == []
