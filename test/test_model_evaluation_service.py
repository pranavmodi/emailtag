"""Focused tests for the model-evaluation pilot."""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.model_evaluation_service import (
    configured_benchmark_tags,
    derive_actions,
    is_single_inbound_message,
)
from app.services.vision_evaluation_service import (
    build_vision_rankings,
    classify_vision_objective,
    field_accuracy,
    rx_output_needs_schema_refresh,
)


def test_configured_benchmark_tags_include_outputs_not_hierarchy_headings():
    hierarchy = {
        "Scheduling": {"RX": ["Order Pending", "RX"]},
        "Accounts Receivable": {
            "Liens": {
                "PSL": ["Rad Lien", "Tech Lien"],
                "ASL": ["Rad Lien", "Tech Lien"],
            },
            "Billing": "Bill or balance Request",
        },
        "No Tag": "No Tag",
    }
    assert configured_benchmark_tags(hierarchy) == [
        "Order Pending",
        "RX",
        "PSL",
        "Rad Lien",
        "Tech Lien",
        "ASL",
        "Bill or balance Request",
        "No Tag",
    ]


def test_single_message_filter_requires_exactly_one_inbound_message():
    assert is_single_inbound_message([{"is_inbound": True}]) is True
    assert is_single_inbound_message([{"is_inbound": False}]) is False
    assert is_single_inbound_message([]) is False
    assert (
        is_single_inbound_message([{"is_inbound": True}, {"is_inbound": False}])
        is False
    )


def test_derive_actions_combines_front_trace_and_autorespond_history():
    messages = [
        {
            "id": "msg_in",
            "is_inbound": True,
            "created_at": "2026-01-01T10:00:00+00:00",
        },
        {
            "id": "msg_out",
            "is_inbound": False,
            "created_at": "2026-01-01T10:03:00+00:00",
        },
    ]
    trace = SimpleNamespace(
        step_name="agent_selected",
        status="completed",
        input_data={"applied_tags": ["Apt status req"]},
        output_data={"agent": "apt_status_req", "full_prompt": "must stay hidden"},
        error_data=None,
        started_at=datetime(2026, 1, 1, 10, 1, tzinfo=timezone.utc),
        completed_at=datetime(2026, 1, 1, 10, 2, tzinfo=timezone.utc),
        created_at=datetime(2026, 1, 1, 10, 1, tzinfo=timezone.utc),
    )
    event = SimpleNamespace(
        response_sent=True,
        created_at=datetime(2026, 1, 1, 10, 4, tzinfo=timezone.utc),
        agent_type="apt_status_req",
        tags=["Apt status req"],
        test_mode=False,
    )

    actions = derive_actions(messages, [trace], [event])

    assert [action["action_type"] for action in actions] == [
        "agent_selected",
        "outbound_reply",
        "autorespond_sent",
    ]
    assert actions[0]["details"]["agent"] == "apt_status_req"
    assert actions[0]["details"]["applied_tags"] == ["Apt status req"]
    assert "full_prompt" not in actions[0]["details"]


def test_derive_actions_ignores_non_action_processing_steps():
    trace = SimpleNamespace(
        step_name="content_extracted",
        status="completed",
        input_data={"raw_email": "sensitive"},
        output_data={"content": "sensitive"},
        error_data=None,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )

    assert derive_actions([], [trace], []) == []


def test_vision_objective_classification_includes_only_structured_documents():
    assert (
        classify_vision_objective(
            {
                "document_analysis": {"data": {"document_type": "RX"}},
                "extracted_text": "handwritten order",
            }
        )
        == "rx"
    )
    assert (
        classify_vision_objective(
            {
                "document_type": "lien",
                "extracted_text": "patient lien",
            }
        )
        == "lien"
    )
    assert classify_vision_objective({"extracted_text": "scanned text"}) is None
    assert classify_vision_objective({"filename": "empty.pdf"}) is None


def test_field_accuracy_counts_missing_rx_diagnosis_codes():
    reference = {"patient": {"name": "Jane Doe"}, "diagnosis_codes": ["M54.2"]}
    candidate = {"patient": {"name": "Jane Doe"}}

    assert field_accuracy(reference, candidate) == 50.0


def test_legacy_rx_schema_detection_requires_diagnosis_codes_and_patient_address():
    assert rx_output_needs_schema_refresh({"patient": {"name": "Jane"}}) is True
    assert (
        rx_output_needs_schema_refresh(
            {"patient": {"name": "Jane", "address": {}}, "diagnosis_codes": []}
        )
        is False
    )
    assert rx_output_needs_schema_refresh(None) is False


def test_vision_rankings_are_split_by_rx_and_lien():
    def run(objective, model_key, output, cost, pages=1):
        provider, model = model_key.split(":", 1)
        return SimpleNamespace(
            objective=objective,
            provider=provider,
            model=model,
            status="completed",
            output=output,
            cost_usd=cost,
            request_metadata={"pages_sent": pages},
        )

    latest = {
        ("rx-case", "vendor:cheap"): run(
            "rx", "vendor:cheap", {"patient": {"name": "Jane"}, "diagnosis_codes": []}, 0.002
        ),
        ("rx-case", "vendor:accurate"): run(
            "rx", "vendor:accurate", {"patient": {"name": "Jane"}, "diagnosis_codes": ["M54.2"]}, 0.009, 3
        ),
        ("lien-case", "vendor:cheap"): run(
            "lien", "vendor:cheap", {"patient_id": "123"}, 0.001
        ),
    }
    references = {
        "rx-case": {"patient": {"name": "Jane"}, "diagnosis_codes": ["M54.2"]},
        "lien-case": {"patient_id": "123"},
    }

    rankings = build_vision_rankings(
        latest,
        references,
        {"rx-case": "rx", "lien-case": "lien"},
    )

    assert [row["model_key"] for row in rankings["rx"]] == [
        "vendor:accurate",
        "vendor:cheap",
    ]
    assert rankings["rx"][0]["average_accuracy"] == 100.0
    assert rankings["rx"][0]["average_cost_per_page_usd"] == 0.003
    assert rankings["rx"][1]["average_accuracy"] == 50.0
    assert [row["model_key"] for row in rankings["lien"]] == ["vendor:cheap"]
