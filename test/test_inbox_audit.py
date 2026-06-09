from app.crud.inbox_audit import build_miss_tag_counts
from app.tasks.inbox_audit import _classify_audit_conversations


def test_build_miss_tag_counts_counts_distinct_open_conversations_by_tag():
    result = build_miss_tag_counts(
        ["cnv_1", "cnv_2", "cnv_3"],
        [
            ("cnv_1", "Bill Offer"),
            ("cnv_1", "Ready"),
            ("cnv_2", "Bill Offer"),
        ],
    )

    assert result == [
        {"tag": "Bill Offer", "count": 2},
        {"tag": "No local tags", "count": 1},
        {"tag": "Ready", "count": 1},
    ]


def test_audit_labels_webhook_only_conversation_as_received_but_failed():
    result = _classify_audit_conversations(
        ["cnv_trace_only"],
        stored_conversations=set(),
        seen_conversations={"cnv_trace_only"},
        processed_conversations=set(),
    )

    assert result["never_received"] == []
    assert result["received_but_failed"] == ["cnv_trace_only"]
    assert result["processed"] == []


def test_audit_labels_no_trace_no_email_as_never_received():
    result = _classify_audit_conversations(
        ["cnv_missing"],
        stored_conversations=set(),
        seen_conversations=set(),
        processed_conversations=set(),
    )

    assert result["never_received"] == ["cnv_missing"]
    assert result["received_but_failed"] == []
    assert result["processed"] == []


def test_audit_requires_stored_email_for_processed_status():
    result = _classify_audit_conversations(
        ["cnv_trace_only", "cnv_done"],
        stored_conversations={"cnv_done"},
        seen_conversations={"cnv_trace_only", "cnv_done"},
        processed_conversations={"cnv_trace_only", "cnv_done"},
    )

    assert result["processed"] == ["cnv_done"]
    assert result["received_but_failed"] == ["cnv_trace_only"]
    assert result["never_received"] == []
