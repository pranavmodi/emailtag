"""Dataset-wide scoring against EmailTag's stored production classifications."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.classification_trace import ClassificationTrace
from app.models.model_evaluation_run import ModelEvaluationRun


def _tags_for_path(path: Sequence[str]) -> List[str]:
    if not path:
        return []
    tags = [path[-1]]
    if len(path) >= 4 and path[1] == "Liens" and path[2] in {"PSL", "ASL"}:
        tags.insert(0, path[2])
    return tags


def latest_production_trace_sequences(
    traces: Iterable[ClassificationTrace],
) -> Dict[str, List[ClassificationTrace]]:
    """Return the latest recorded production hierarchy traversal per conversation."""
    grouped: Dict[str, List[ClassificationTrace]] = defaultdict(list)
    for trace in traces:
        grouped[trace.front_conversation_id].append(trace)

    def trace_path(trace: ClassificationTrace) -> List[str]:
        return [
            part.strip()
            for part in str(trace.classification_path or "").split("→")
            if part.strip()
        ]

    def reaches_leaf(path: Sequence[str]) -> bool:
        node: Any = settings.EMAIL_CATEGORIES
        for choice in path:
            if isinstance(node, dict) and choice in node:
                node = node[choice]
            elif isinstance(node, list) and choice in node:
                node = choice
            else:
                return False
        return not isinstance(node, (dict, list))

    latest: Dict[str, List[ClassificationTrace]] = {}
    for conversation_id, conversation_traces in grouped.items():
        starts = sorted(
            (trace for trace in conversation_traces if trace.step_order == 0),
            key=lambda trace: trace.created_at,
            reverse=True,
        )
        candidates: List[tuple[bool, Any, List[ClassificationTrace]]] = []
        for start in starts:
            ordered = [start]
            path = [str(start.chosen_option)] if start.chosen_option else []
            while path:
                next_steps = [
                    trace
                    for trace in conversation_traces
                    if trace.step_order == len(path)
                    and trace_path(trace) == path
                    and trace.created_at >= start.created_at
                ]
                if not next_steps:
                    break
                next_trace = max(next_steps, key=lambda trace: trace.created_at)
                ordered.append(next_trace)
                if not next_trace.chosen_option:
                    break
                path.append(str(next_trace.chosen_option))
            candidates.append((reaches_leaf(path), start.created_at, ordered))

        complete = [item for item in candidates if item[0]]
        pool = complete or candidates
        if pool:
            latest[conversation_id] = max(pool, key=lambda item: item[1])[2]

    return latest


def latest_production_references(
    traces: Iterable[ClassificationTrace],
) -> Dict[str, Dict[str, Any]]:
    """Build one reference from the latest step-order sequence per conversation."""
    references: Dict[str, Dict[str, Any]] = {}
    for conversation_id, ordered in latest_production_trace_sequences(traces).items():
        path = [str(trace.chosen_option) for trace in ordered if trace.chosen_option]
        if not path:
            continue
        references[conversation_id] = {
            "tags": _tags_for_path(path),
            "classification_path": path,
            "production_model": next(
                (str(trace.llm_model) for trace in reversed(ordered) if trace.llm_model),
                None,
            ),
            "classified_at": max(trace.created_at for trace in ordered),
        }
    return references


async def get_production_classification_references(
    db: AsyncSession,
    conversation_ids: Sequence[str],
) -> Dict[str, Dict[str, Any]]:
    if not conversation_ids:
        return {}
    result = await db.execute(
        select(ClassificationTrace)
        .where(ClassificationTrace.front_conversation_id.in_(conversation_ids))
        .order_by(
            ClassificationTrace.front_conversation_id,
            ClassificationTrace.created_at.asc(),
            ClassificationTrace.step_order.asc(),
        )
    )
    return latest_production_references(result.scalars().all())


def build_classification_rankings(
    runs: Iterable[ModelEvaluationRun],
    references: Dict[str, Dict[str, Any]],
    allowed_model_keys: Optional[set[str]] = None,
) -> List[Dict[str, Any]]:
    """Aggregate exact production-path matches and cost for each model."""
    latest: Dict[tuple[str, str], ModelEvaluationRun] = {}
    for run in runs:
        if allowed_model_keys is not None and run.model_key not in allowed_model_keys:
            continue
        output = run.output if isinstance(run.output, dict) else {}
        metadata = getattr(run, "request_metadata", None) or {}
        if (
            output.get("evaluation_mode") != "exact_production_trace_replay"
            and metadata.get("evaluation_mode") != "exact_production_trace_replay"
        ):
            continue
        latest.setdefault((run.case_id, run.model_key), run)

    buckets: Dict[str, Dict[str, Any]] = {}
    for (case_id, model_key), run in latest.items():
        # Rankings are meaningful only for emails with a stored production path.
        if case_id not in references:
            continue
        bucket = buckets.setdefault(
            model_key,
            {
                "model_key": model_key,
                "provider": run.provider,
                "model": run.model,
                "attempted_cases": 0,
                "completed_cases": 0,
                "scored_cases": 0,
                "exact_matches": 0,
                "classification_mismatches": 0,
                "execution_errors": 0,
                "final_tag_matches": 0,
                "total_cost_usd": 0.0,
                "total_tokens": 0,
                "tag_totals": defaultdict(int),
                "tag_matches": defaultdict(int),
            },
        )
        bucket["attempted_cases"] += 1
        bucket["total_cost_usd"] += float(run.cost_usd or 0)
        bucket["total_tokens"] += int(run.total_tokens or 0)
        output = run.output if isinstance(run.output, dict) else None
        if run.status != "completed" or not output or output.get("parse_error"):
            bucket["execution_errors"] += 1
            continue
        bucket["completed_cases"] += 1
        bucket["scored_cases"] += 1
        exact = output.get("production_match") is True
        final_match = exact
        bucket["exact_matches"] += int(exact)
        bucket["classification_mismatches"] += int(not exact)
        bucket["final_tag_matches"] += int(final_match)

    rankings: List[Dict[str, Any]] = []
    for bucket in buckets.values():
        attempted = bucket.pop("attempted_cases")
        completed = bucket.pop("completed_cases")
        scored = bucket.pop("scored_cases")
        exact_matches = bucket.pop("exact_matches")
        classification_mismatches = bucket.pop("classification_mismatches")
        execution_errors = bucket.pop("execution_errors")
        final_tag_matches = bucket.pop("final_tag_matches")
        total_cost = bucket.pop("total_cost_usd")
        total_tokens = bucket.pop("total_tokens")
        tag_totals = bucket.pop("tag_totals")
        tag_matches = bucket.pop("tag_matches")
        rankings.append(
            {
                **bucket,
                "attempted_cases": attempted,
                "completed_cases": completed,
                "scored_cases": scored,
                "exact_matches": exact_matches,
                "classification_mismatches": classification_mismatches,
                "execution_errors": execution_errors,
                "final_tag_matches": final_tag_matches,
                # Provider/format failures count against end-to-end success. A model
                # is useful only if it both returns a valid result and matches the
                # complete production hierarchy.
                "accuracy": round(exact_matches / attempted * 100, 2) if attempted else None,
                "final_tag_accuracy": (
                    round(final_tag_matches / attempted * 100, 2) if attempted else None
                ),
                "average_cost_usd": round(total_cost / attempted, 8) if attempted else None,
                "total_cost_usd": round(total_cost, 8),
                "average_tokens": round(total_tokens / attempted) if attempted else 0,
                "completion_rate": round(completed / attempted * 100, 2) if attempted else 0,
                "tag_accuracy": {},
            }
        )
    rankings.sort(
        key=lambda row: (
            -(row["accuracy"] if row["accuracy"] is not None else -1),
            row["average_cost_usd"] if row["average_cost_usd"] is not None else float("inf"),
        )
    )
    return rankings


async def get_classification_rankings(
    db: AsyncSession,
    conversation_ids: Sequence[str],
    allowed_model_keys: Optional[set[str]] = None,
) -> Dict[str, Any]:
    unique_ids = list(dict.fromkeys(conversation_ids))
    references = await get_production_classification_references(db, unique_ids)
    if not unique_ids:
        return {"shortlisted_cases": 0, "reference_cases": 0, "rankings": []}
    result = await db.execute(
        select(ModelEvaluationRun)
        .where(
            ModelEvaluationRun.case_type == "classification",
            ModelEvaluationRun.case_id.in_(unique_ids),
        )
        .order_by(ModelEvaluationRun.created_at.desc())
    )
    return {
        "shortlisted_cases": len(unique_ids),
        "reference_cases": len(references),
        "rankings": build_classification_rankings(
            result.scalars().all(),
            references,
            allowed_model_keys,
        ),
    }
