"""Focused tests for dataset-wide production classification scoring."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.classification_evaluation_service import (
    build_classification_rankings,
    latest_production_references,
)


def _trace(
    conversation_id,
    step_order,
    choice,
    created_at,
    model="production-model",
    classification_path=None,
):
    return SimpleNamespace(
        front_conversation_id=conversation_id,
        step_order=step_order,
        chosen_option=choice,
        llm_model=model,
        created_at=created_at,
        classification_path=classification_path,
    )


def test_latest_production_reference_uses_latest_complete_step_sequence():
    started = datetime(2026, 8, 1, tzinfo=timezone.utc)
    traces = [
        _trace("cnv_1", 0, "Scheduling", started),
        _trace("cnv_1", 1, "RX", started + timedelta(seconds=1), classification_path="Scheduling"),
        _trace("cnv_1", 2, "RX", started + timedelta(seconds=2), classification_path="Scheduling → RX"),
        _trace("cnv_1", 0, "Accounts Receivable", started + timedelta(days=1)),
        _trace("cnv_1", 1, "Negotiations", started + timedelta(days=1, seconds=1), classification_path="Accounts Receivable"),
        _trace("cnv_1", 2, "Bill Offer", started + timedelta(days=1, seconds=2), classification_path="Accounts Receivable → Negotiations"),
    ]

    reference = latest_production_references(traces)["cnv_1"]

    assert reference["classification_path"] == [
        "Accounts Receivable",
        "Negotiations",
        "Bill Offer",
    ]
    assert reference["tags"] == ["Bill Offer"]


def test_latest_production_reference_handles_interleaved_duplicate_runs():
    started = datetime(2026, 8, 1, tzinfo=timezone.utc)
    traces = [
        _trace("cnv_1", 0, "Accounts Receivable", started),
        _trace("cnv_1", 0, "Accounts Receivable", started + timedelta(milliseconds=100)),
        _trace(
            "cnv_1",
            1,
            "Collections",
            started + timedelta(milliseconds=200),
            classification_path="Accounts Receivable",
        ),
        _trace(
            "cnv_1",
            1,
            "Billing",
            started + timedelta(milliseconds=300),
            classification_path="Accounts Receivable",
        ),
    ]

    reference = latest_production_references(traces)["cnv_1"]

    assert reference["classification_path"] == ["Accounts Receivable", "Billing"]


def test_classification_ranking_scores_only_exact_production_replay():
    def run(model_key, production_match, cost, case_id="cnv_1", status="completed"):
        provider, model = model_key.split(":", 1)
        return SimpleNamespace(
            case_id=case_id,
            model_key=model_key,
            provider=provider,
            model=model,
            status=status,
            output={
                "evaluation_mode": "exact_production_trace_replay",
                "production_match": production_match,
            },
            request_metadata={"evaluation_mode": "exact_production_trace_replay"},
            cost_usd=cost,
            total_tokens=100,
        )

    references = {
        "cnv_1": {
            "classification_path": ["Accounts Receivable", "Negotiations", "Bill Offer"],
            "tags": ["Bill Offer"],
        },
        "cnv_2": {
            "classification_path": ["Scheduling", "RX"],
            "tags": ["RX"],
        },
    }
    rankings = build_classification_rankings(
        [
            run("vendor:exact", True, 0.01),
            run("vendor:diverged", False, 0.001),
            run("vendor:flaky", True, 0.002),
            run("vendor:flaky", False, 0.003, case_id="cnv_2", status="error"),
        ],
        references,
    )

    assert [row["model_key"] for row in rankings] == [
        "vendor:exact",
        "vendor:flaky",
        "vendor:diverged",
    ]
    assert rankings[0]["accuracy"] == 100.0
    assert rankings[1]["accuracy"] == 50.0
    assert rankings[1]["exact_matches"] == 1
    assert rankings[1]["classification_mismatches"] == 0
    assert rankings[1]["execution_errors"] == 1
    assert rankings[1]["completion_rate"] == 50.0
    assert rankings[2]["accuracy"] == 0.0
    assert rankings[2]["classification_mismatches"] == 1
    assert rankings[2]["final_tag_accuracy"] == 0.0
    assert rankings[2]["average_cost_usd"] == 0.001
