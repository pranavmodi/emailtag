from types import SimpleNamespace

from app.models.pif_info import PifInfo
from app.services.website_resolution import (
    apply_website_resolution,
    resolve_firm_website,
    verify_firm_website,
)


def _response(url, text, status_code=200):
    return SimpleNamespace(url=url, text=text, status_code=status_code)


def test_website_resolver_uses_verified_firm_website_seed_without_search():
    firm = PifInfo(
        firm_name="Smith Injury Law",
        website="https://www.smithlaw.com/about",
        emails=["intake@gmail.com"],
        phones=[],
        addresses=[],
        contacts=[],
        conversation_ids=[],
    )
    search_calls = []

    result = resolve_firm_website(
        firm,
        http_get=lambda url: _response(url, "<title>Smith Injury Law</title>"),
        search=lambda firm_name, location: search_calls.append((firm_name, location)),
    )

    assert result.website_status == "resolved"
    assert result.website_source == "email_verified"
    assert result.canonical_website == "smithlaw.com"
    assert search_calls == []


def test_website_resolver_uses_email_domain_then_search_fallback():
    firm = PifInfo(
        firm_name="Garcia Trial Lawyers",
        website=None,
        emails=["intake@garciatrial.com"],
        phones=[],
        addresses=["Los Angeles, CA"],
        contacts=[],
        conversation_ids=[],
    )

    def http_get(url):
        if "garciatrial.com" in url:
            return _response(url, "domain for sale")
        return _response(url, "Garcia Trial Lawyers official site")

    result = resolve_firm_website(
        firm,
        http_get=http_get,
        search=lambda firm_name, location: "https://www.garcialaw.com",
    )

    assert result.website_status == "resolved"
    assert result.website_source == "web_search"
    assert result.canonical_website == "garcialaw.com"


def test_website_resolver_queues_human_review_stub_for_ambiguous_results():
    firm = PifInfo(
        firm_name="Common Name Law",
        website=None,
        emails=["owner@gmail.com"],
        phones=[],
        addresses=[],
        contacts=[],
        conversation_ids=[],
    )

    result = resolve_firm_website(
        firm,
        http_get=lambda url: _response(url, "Directory result"),
        search=lambda firm_name, location: None,
    )

    assert result.website_status == "pending"
    assert result.website_source == "human"
    assert result.canonical_website is None
    assert result.review_reason == "no_search_result"


def test_verify_firm_website_rejects_portals_and_parked_pages():
    assert verify_firm_website(
        "smithlaw.filevineapp.com",
        "Smith Law",
        http_get=lambda url: _response(url, "Smith Law"),
    ) is None
    assert verify_firm_website(
        "smithlaw.com",
        "Smith Law",
        http_get=lambda url: _response(url, "Buy this domain"),
    ) is None


def test_apply_website_resolution_updates_pif_fields():
    firm = PifInfo(
        firm_name="Smith Law",
        website=None,
        emails=[],
        phones=[],
        addresses=[],
        contacts=[],
        conversation_ids=[],
    )
    result = resolve_firm_website(
        firm,
        http_get=lambda url: _response(url, "Smith Law"),
        search=lambda firm_name, location: "https://smithlaw.com",
    )

    apply_website_resolution(firm, result)

    assert firm.canonical_website == "smithlaw.com"
    assert firm.website_status == "resolved"
    assert firm.website_source == "web_search"
    assert firm.website_confidence == 0.78
