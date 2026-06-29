import uuid

from app.models.pif_info import PifInfo
from app.services.firm_dedup import cluster_firms_for_review


def _firm(name, website=None, canonical_website=None, emails=None):
    firm = PifInfo(
        firm_name=name,
        website=website,
        canonical_website=canonical_website,
        emails=emails or [],
        phones=[],
        addresses=[],
        contacts=[],
        conversation_ids=[],
    )
    firm.id = uuid.uuid4()
    return firm


def test_dedup_clusters_duplicate_canonical_domains_for_review_only():
    firms = [
        _firm("Smith Law", canonical_website="smithlaw.com"),
        _firm("Smith Injury", website="https://www.smithlaw.com/about"),
        _firm("Garcia Law", emails=["hello@garcialaw.com"]),
    ]

    clusters = cluster_firms_for_review(firms)

    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster.cluster_key == "smithlaw.com"
    assert cluster.review_required is True
    assert cluster.action == "review_only"
    assert set(cluster.firm_names) == {"Smith Law", "Smith Injury"}


def test_dedup_ignores_shared_email_domains_when_no_website_domain():
    firms = [
        _firm("One Law", emails=["one@sbcglobal.net"]),
        _firm("Two Medical", emails=["two@sbcglobal.net"]),
        _firm("BellMed", emails=["roberttmbell-gmail.com@shared1.ccsend.com"]),
        _firm("Bell Medical", emails=["roberttmbell-gmail.com@shared1.ccsend.com"]),
    ]

    clusters = cluster_firms_for_review(firms)

    assert clusters == []
