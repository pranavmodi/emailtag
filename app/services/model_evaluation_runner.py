"""Manual, evaluation-only execution across hosted language and vision models.

This module intentionally has no imports from Celery tasks or production processing
entry points. It reads an existing case and writes only ModelEvaluationRun rows.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional, Sequence
from uuid import UUID

import httpx
from PIL import Image, ImageSequence
from pdf2image import convert_from_bytes
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.email import Email
from app.models.classification_trace import ClassificationTrace
from app.models.model_evaluation_run import (
    ModelEvaluationCaseReview,
    ModelEvaluationModelSetting,
    ModelEvaluationRun,
)
from app.schemas.model_evaluation import ModelEvaluationRunRequest
from app.services.classification_evaluation_service import latest_production_trace_sequences
from app.services.vision_evaluation_service import get_vision_document


@dataclass(frozen=True)
class ModelSpec:
    key: str
    provider: str
    model: str
    display_name: str
    case_types: tuple[str, ...]
    input_rate: Decimal
    output_rate: Decimal
    cached_input_rate: Optional[Decimal] = None
    cache_write_rate: Optional[Decimal] = None


def _spec(
    provider: str,
    model: str,
    display_name: str,
    case_types: Sequence[str],
    input_rate: str,
    output_rate: str,
    *,
    cached_input_rate: Optional[str] = None,
    cache_write_rate: Optional[str] = None,
) -> ModelSpec:
    return ModelSpec(
        key=f"{provider}:{model}",
        provider=provider,
        model=model,
        display_name=display_name,
        case_types=tuple(case_types),
        input_rate=Decimal(input_rate),
        output_rate=Decimal(output_rate),
        cached_input_rate=Decimal(cached_input_rate) if cached_input_rate else None,
        cache_write_rate=Decimal(cache_write_rate) if cache_write_rate else None,
    )


# USD per million tokens. This rate card is captured with every result so historic
# calculations remain explainable when vendor prices change.
MODEL_CATALOG: tuple[ModelSpec, ...] = (
    _spec("openai", "gpt-5-mini", "GPT-5 Mini (production)", ("classification",), "0.25", "2", cached_input_rate="0.025"),
    _spec("openai", "gpt-5.5", "GPT-5.5", ("classification", "vision"), "5", "30", cached_input_rate="0.5"),
    _spec("openai", "gpt-5.6-luna", "GPT-5.6 Luna", ("classification", "vision"), "0.2", "1.2", cached_input_rate="0.02", cache_write_rate="0.25"),
    _spec("openai", "gpt-5.6-terra", "GPT-5.6 Terra", ("classification", "vision"), "2", "12", cached_input_rate="0.2", cache_write_rate="2.5"),
    _spec("openai", "gpt-5.6-sol", "GPT-5.6 Sol (baseline)", ("classification", "vision"), "5", "30", cached_input_rate="0.5", cache_write_rate="6.25"),
    _spec("gemini", "gemini-3.5-flash-lite", "Gemini 3.5 Flash Lite", ("classification", "vision"), "0.3", "2.5", cached_input_rate="0.03"),
    _spec("gemini", "gemini-3.6-flash", "Gemini 3.6 Flash", ("classification", "vision"), "1.5", "7.5"),
    _spec("gemini", "gemini-3.7-flash", "Gemini 3.7 Flash", ("classification", "vision"), "0.75", "3.75", cached_input_rate="0.075"),
    _spec("xai", "grok-4.3", "Grok 4.3", ("classification",), "1.25", "2.5", cached_input_rate="0.2"),
    _spec("xai", "grok-4.5", "Grok 4.5", ("classification", "vision"), "2", "6", cached_input_rate="0.3"),
    _spec("xai", "grok-4.6", "Grok 4.6", ("classification", "vision"), "2", "6", cached_input_rate="0.5"),
    _spec("together", "openai/gpt-oss-20b", "GPT-OSS 20B", ("classification",), "0.05", "0.2"),
    _spec("together", "MiniMaxAI/MiniMax-M3", "MiniMax M3", ("classification", "vision"), "0.3", "1.2", cached_input_rate="0.06"),
    _spec("together", "google/gemma-4-31B-it", "Gemma 4 31B", ("classification", "vision"), "0.39", "0.97"),
    _spec("together", "deepseek-ai/DeepSeek-V4-Flash-0731", "DeepSeek V4 Flash", ("classification",), "0.14", "0.28", cached_input_rate="0.03"),
    _spec("together", "Qwen/Qwen3.8-2.4T-A95B", "Qwen 3.8 2.4T A95B", ("classification",), "2.5", "6.25", cached_input_rate="0.5"),
    _spec("fireworks", "accounts/fireworks/models/gpt-oss-20b", "GPT-OSS 20B", ("classification",), "0.07", "0.3"),
    _spec("fireworks", "accounts/fireworks/models/deepseek-v4-flash-0731", "DeepSeek V4 Flash", ("classification",), "0.14", "0.28"),
    _spec("fireworks", "accounts/fireworks/models/kimi-k2p6", "Kimi K2.6", ("classification", "vision"), "0.95", "4", cached_input_rate="0.16"),
    _spec("openrouter", "qwen/qwen3-vl-8b-instruct", "Qwen3 VL 8B (ZDR)", ("classification", "vision"), "0.25", "0.75"),
    _spec("openrouter", "qwen/qwen3.5-27b", "Qwen 3.5 27B (ZDR)", ("classification", "vision"), "0.25", "2"),
    _spec("openrouter", "z-ai/glm-4.5v", "GLM-4.5V (ZDR)", ("classification", "vision"), "0.6", "1.8"),
)

MODEL_BY_KEY = {item.key: item for item in MODEL_CATALOG}


@dataclass
class Usage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    provider_cost: Optional[Decimal] = None
    raw: Optional[Dict[str, Any]] = None

    def add(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.cached_input_tokens += other.cached_input_tokens
        self.cache_write_tokens += other.cache_write_tokens
        self.output_tokens += other.output_tokens
        if other.provider_cost is not None:
            self.provider_cost = (self.provider_cost or Decimal("0")) + other.provider_cost


@dataclass
class CallResult:
    output: Dict[str, Any]
    usage: Usage
    incomplete_reason: Optional[str] = None
    retry_count: int = 0


class EvaluationExecutionError(Exception):
    """An evaluation failed after possibly consuming provider tokens."""

    def __init__(
        self,
        message: str,
        usage: Optional[Usage] = None,
        output: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.usage = usage or Usage()
        self.output = output


@dataclass
class PreparedCase:
    case_type: str
    case_id: str
    conversation_id: Optional[str]
    email_id: Optional[UUID]
    result_index: Optional[int]
    objective: Optional[str]
    email_text: Optional[str] = None
    classification_steps: Optional[List[Dict[str, Any]]] = None
    images: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


def _provider_key(provider: str) -> Optional[str]:
    if provider == "openai":
        return os.getenv("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", None)
    setting_name = {
        "gemini": "MODEL_EVAL_GEMINI_API_KEY",
        "xai": "MODEL_EVAL_XAI_API_KEY",
        "together": "MODEL_EVAL_TOGETHER_API_KEY",
        "fireworks": "MODEL_EVAL_FIREWORKS_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }[provider]
    return os.getenv(setting_name) or getattr(settings, setting_name, None)


def get_model_catalog(
    case_type: Optional[str] = None,
    *,
    enabled_by_key: Optional[Dict[str, bool]] = None,
) -> List[Dict[str, Any]]:
    if case_type and case_type not in {"classification", "vision"}:
        raise ValueError("case_type must be classification or vision")
    return [
        {
            "key": spec.key,
            "provider": spec.provider,
            "model": spec.model,
            "display_name": spec.display_name,
            "case_types": list(spec.case_types),
            "input_price_per_million": float(spec.input_rate),
            "output_price_per_million": float(spec.output_rate),
            "available": bool(_provider_key(spec.provider)),
            "enabled": (enabled_by_key or {}).get(spec.key, True),
            "availability_note": (
                "OpenRouter requests are restricted to ZDR, no-data-collection routes."
                if spec.provider == "openrouter"
                else None
            ),
        }
        for spec in MODEL_CATALOG
        if not case_type or case_type in spec.case_types
    ]


async def get_model_settings(db: AsyncSession) -> Dict[str, bool]:
    result = await db.execute(select(ModelEvaluationModelSetting))
    return {row.model_key: row.enabled for row in result.scalars().all()}


async def save_model_setting(
    db: AsyncSession, *, model_key: str, enabled: bool, updated_by: str
) -> ModelEvaluationModelSetting:
    if model_key not in MODEL_BY_KEY:
        raise ValueError(f"Unknown evaluation model: {model_key}")
    row = await db.get(ModelEvaluationModelSetting, model_key)
    if row is None:
        row = ModelEvaluationModelSetting(model_key=model_key)
        db.add(row)
    row.enabled = enabled
    row.updated_by = updated_by
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


def calculate_cost(spec: ModelSpec, usage: Usage) -> Decimal:
    if usage.provider_cost is not None:
        return usage.provider_cost.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
    cached = min(max(usage.cached_input_tokens, 0), max(usage.input_tokens, 0))
    cache_write = min(
        max(usage.cache_write_tokens, 0), max(usage.input_tokens - cached, 0)
    )
    ordinary = max(usage.input_tokens - cached - cache_write, 0)
    cached_rate = spec.cached_input_rate or spec.input_rate
    write_rate = spec.cache_write_rate or spec.input_rate
    dollars = (
        Decimal(ordinary) * spec.input_rate
        + Decimal(cached) * cached_rate
        + Decimal(cache_write) * write_rate
        + Decimal(max(usage.output_tokens, 0)) * spec.output_rate
    ) / Decimal(1_000_000)
    return dollars.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)


def _rate_snapshot(spec: ModelSpec) -> Dict[str, Any]:
    return {
        "currency": "USD",
        "unit": "per_million_tokens",
        "input": str(spec.input_rate),
        "cached_input": str(spec.cached_input_rate or spec.input_rate),
        "cache_write": str(spec.cache_write_rate or spec.input_rate),
        "output": str(spec.output_rate),
        "captured_on": "2026-08-19",
    }


def _without_extracted_notes(value: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Remove the evaluation-only document catch-all while preserving stored history."""
    if value is None or "notes" not in value:
        return value
    return {key: child for key, child in value.items() if key != "notes"}


def _extract_json(text: str) -> Dict[str, Any]:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```$", "", value)
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        start, end = value.find("{"), value.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Model did not return a JSON object")
        parsed = json.loads(value[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Model response must be a JSON object")
    return parsed


def _openai_output_text(payload: Dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    pieces: List[str] = []
    for item in payload.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                pieces.append(str(content["text"]))
    return "\n".join(pieces)


def _parsed_or_raw(
    text: str, usage: Usage, incomplete_reason: Optional[str] = None
) -> CallResult:
    try:
        output = _extract_json(text)
    except (ValueError, json.JSONDecodeError) as exc:
        output = {"unparsed_text": text, "parse_error": str(exc)}
    return CallResult(output, usage, incomplete_reason)


def _usage_from_openai(payload: Dict[str, Any]) -> Usage:
    raw = payload.get("usage") or {}
    details = raw.get("input_tokens_details") or raw.get("prompt_tokens_details") or {}
    provider_cost = raw.get("cost")
    return Usage(
        input_tokens=int(raw.get("input_tokens") or raw.get("prompt_tokens") or 0),
        cached_input_tokens=int(details.get("cached_tokens") or 0),
        cache_write_tokens=int(details.get("cache_write_tokens") or 0),
        output_tokens=int(raw.get("output_tokens") or raw.get("completion_tokens") or 0),
        provider_cost=(Decimal(str(provider_cost)) if provider_cost is not None else None),
        raw=raw,
    )


def _schema_prompt(prompt: str, schema: Dict[str, Any]) -> str:
    return (
        f"{prompt}\n\nReturn only valid JSON matching this JSON Schema exactly. "
        f"Do not add markdown or commentary.\n{json.dumps(schema, separators=(',', ':'))}"
    )


RETRYABLE_PROVIDER_STATUSES = {408, 409, 429, 500, 502, 503, 504}
MAX_PROVIDER_RETRIES = 3


def _provider_retry_delay(response: Optional[httpx.Response], retry_number: int) -> float:
    """Honor a numeric Retry-After header, otherwise use bounded exponential backoff."""
    if response is not None:
        retry_after = response.headers.get("retry-after")
        if retry_after:
            try:
                return min(max(float(retry_after), 0.0), 30.0)
            except ValueError:
                pass
    return min(2 ** (retry_number - 1), 8)


async def _post_with_retries(
    client: httpx.AsyncClient,
    url: str,
    **kwargs: Any,
) -> tuple[httpx.Response, int]:
    """POST once plus three retries for transient transport and provider failures."""
    retry_count = 0
    while True:
        response: Optional[httpx.Response] = None
        try:
            response = await client.post(url, **kwargs)
        except httpx.TransportError:
            if retry_count >= MAX_PROVIDER_RETRIES:
                raise
        else:
            if response.status_code not in RETRYABLE_PROVIDER_STATUSES:
                response.raise_for_status()
                return response, retry_count
            if retry_count >= MAX_PROVIDER_RETRIES:
                response.raise_for_status()

        retry_count += 1
        await asyncio.sleep(_provider_retry_delay(response, retry_count))


async def _call_openai(
    spec: ModelSpec,
    prompt: str,
    schema: Dict[str, Any],
    images: Sequence[str],
    max_output_tokens: int,
    system_prompt: Optional[str] = None,
) -> CallResult:
    content: List[Dict[str, Any]] = [{"type": "input_text", "text": prompt}]
    content.extend({"type": "input_image", "image_url": image} for image in images)
    model_input: List[Dict[str, Any]] = []
    if system_prompt:
        model_input.append({"role": "system", "content": system_prompt})
    model_input.append({"role": "user", "content": content})
    payload = {
        "model": spec.model,
        "input": model_input,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "evaluation_result",
                "schema": schema,
                "strict": True,
            }
        },
        "max_output_tokens": max_output_tokens,
        "store": False,
    }
    async with httpx.AsyncClient(timeout=180.0) as client:
        response, retry_count = await _post_with_retries(
            client,
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {_provider_key('openai')}"},
            json=payload,
        )
    data = response.json()
    usage = _usage_from_openai(data)
    incomplete = None
    if data.get("status") == "incomplete":
        incomplete = str((data.get("incomplete_details") or {}).get("reason") or "incomplete")
    result = _parsed_or_raw(_openai_output_text(data), usage, incomplete)
    result.retry_count = retry_count
    return result


async def _call_openai_production_classification(
    spec: ModelSpec,
    prompt: str,
    schema: Dict[str, Any],
    system_prompt: Optional[str] = None,
) -> CallResult:
    """Call GPT-5 Mini with the same API surface and settings as production."""
    payload = {
        "model": spec.model,
        "messages": [
            {
                "role": "system",
                "content": system_prompt
                or (
                    "You are an expert email classifier. Follow the instructions in the "
                    "user message carefully and respond only with the chosen option name."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "classification_response",
                "strict": True,
                "schema": schema,
            },
        },
        "reasoning_effort": "medium",
        "max_completion_tokens": 16_000,
    }
    async with httpx.AsyncClient(timeout=180.0) as client:
        response, retry_count = await _post_with_retries(
            client,
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {_provider_key('openai')}"},
            json=payload,
        )
    data = response.json()
    message = ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
    if isinstance(message, list):
        message = "\n".join(str(item.get("text") or "") for item in message)
    finish_reason = str(((data.get("choices") or [{}])[0]).get("finish_reason") or "")
    incomplete = finish_reason if finish_reason and finish_reason not in {"stop", "completed"} else None
    result = _parsed_or_raw(str(message or ""), _usage_from_openai(data), incomplete)
    result.retry_count = retry_count
    return result


async def _call_gemini(
    spec: ModelSpec,
    prompt: str,
    schema: Dict[str, Any],
    images: Sequence[str],
    max_output_tokens: int,
    system_prompt: Optional[str] = None,
) -> CallResult:
    parts: List[Dict[str, Any]] = [{"text": prompt}]
    for image in images:
        header, encoded = image.split(",", 1)
        mime = header.split(";")[0].split(":", 1)[1]
        parts.append({"inlineData": {"mimeType": mime, "data": encoded}})
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseJsonSchema": schema,
            "maxOutputTokens": max_output_tokens,
        },
    }
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{spec.model}:generateContent"
    async with httpx.AsyncClient(timeout=180.0) as client:
        response, retry_count = await _post_with_retries(
            client, url, params={"key": _provider_key("gemini")}, json=payload
        )
    data = response.json()
    text = "\n".join(
        str(part.get("text"))
        for candidate in data.get("candidates") or []
        for part in (candidate.get("content") or {}).get("parts") or []
        if part.get("text")
    )
    raw = data.get("usageMetadata") or {}
    output_tokens = int(raw.get("candidatesTokenCount") or 0) + int(
        raw.get("thoughtsTokenCount") or 0
    )
    usage = Usage(
        input_tokens=int(raw.get("promptTokenCount") or 0),
        cached_input_tokens=int(raw.get("cachedContentTokenCount") or 0),
        output_tokens=output_tokens,
        raw=raw,
    )
    finish_reasons = [
        str(candidate.get("finishReason"))
        for candidate in data.get("candidates") or []
        if candidate.get("finishReason")
    ]
    incomplete = ", ".join(reason for reason in finish_reasons if reason != "STOP") or None
    result = _parsed_or_raw(text, usage, incomplete)
    result.retry_count = retry_count
    return result


async def _call_chat_compatible(
    spec: ModelSpec,
    prompt: str,
    schema: Dict[str, Any],
    images: Sequence[str],
    max_output_tokens: int,
    system_prompt: Optional[str] = None,
) -> CallResult:
    endpoints = {
        "xai": "https://api.x.ai/v1/chat/completions",
        "together": "https://api.together.xyz/v1/chat/completions",
        "fireworks": "https://api.fireworks.ai/inference/v1/chat/completions",
        "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    }
    user_content: Any = _schema_prompt(prompt, schema)
    if images:
        user_content = [{"type": "text", "text": user_content}] + [
            {"type": "image_url", "image_url": {"url": image}} for image in images
        ]
    payload = {
        "model": spec.model,
        "messages": [
            {
                "role": "system",
                "content": system_prompt
                or "You are an evaluation engine. Use only the supplied evidence and return JSON.",
            },
            {"role": "user", "content": user_content},
        ],
        "max_tokens": max_output_tokens,
        "temperature": 0,
    }
    if spec.provider == "openrouter":
        payload["provider"] = {
            "zdr": True,
            "data_collection": "deny",
            "allow_fallbacks": True,
        }
    async with httpx.AsyncClient(timeout=180.0) as client:
        response, retry_count = await _post_with_retries(
            client,
            endpoints[spec.provider],
            headers={"Authorization": f"Bearer {_provider_key(spec.provider)}"},
            json=payload,
        )
    data = response.json()
    message = ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
    if isinstance(message, list):
        message = "\n".join(str(item.get("text") or "") for item in message)
    usage = _usage_from_openai(data)
    finish_reason = str(((data.get("choices") or [{}])[0]).get("finish_reason") or "")
    incomplete = finish_reason if finish_reason and finish_reason not in {"stop", "completed"} else None
    result = _parsed_or_raw(str(message or ""), usage, incomplete)
    result.retry_count = retry_count
    return result


async def _call_model(
    spec: ModelSpec,
    prompt: str,
    schema: Dict[str, Any],
    images: Sequence[str] = (),
    max_output_tokens: int = 3000,
    system_prompt: Optional[str] = None,
) -> CallResult:
    if not _provider_key(spec.provider):
        raise ValueError(f"No evaluation API key is configured for {spec.provider}")
    if spec.key == "openai:gpt-5-mini":
        return await _call_openai_production_classification(
            spec,
            prompt,
            schema,
            system_prompt,
        )
    if spec.provider == "openai":
        return await _call_openai(spec, prompt, schema, images, max_output_tokens, system_prompt)
    if spec.provider == "gemini":
        return await _call_gemini(spec, prompt, schema, images, max_output_tokens, system_prompt)
    return await _call_chat_compatible(spec, prompt, schema, images, max_output_tokens, system_prompt)


def _sanitize_category_part(value: str) -> str:
    sanitized = str(value).upper().replace(" ", "_").replace("&", "AND")
    for character in "/-.":
        sanitized = sanitized.replace(character, "_")
    while "__" in sanitized:
        sanitized = sanitized.replace("__", "_")
    return sanitized.strip("_") or "INVALIDKEY"


def _rule_key(path: Sequence[str]) -> str:
    return "ROOT" + ("_" + "_".join(_sanitize_category_part(item) for item in path) if path else "")


async def _prepare_classification(db: AsyncSession, conversation_id: str) -> PreparedCase:
    result = await db.execute(
        select(Email)
        .where(Email.front_conversation_id == conversation_id)
        .order_by(Email.created_at.desc())
    )
    emails = list(result.scalars().all())
    if not emails:
        raise LookupError("Classification conversation not found")
    email = next((item for item in emails if item.content_text or item.content_html), emails[0])
    trace_result = await db.execute(
        select(ClassificationTrace)
        .where(ClassificationTrace.front_conversation_id == conversation_id)
        .order_by(ClassificationTrace.created_at.asc(), ClassificationTrace.step_order.asc())
    )
    trace_sequences = latest_production_trace_sequences(trace_result.scalars().all())
    production_traces = trace_sequences.get(conversation_id) or []
    if not production_traces:
        raise LookupError("No stored production classification trace is available")

    hierarchy: Any = settings.EMAIL_CATEGORIES
    production_path: List[str] = []
    production_tags: List[str] = []
    classification_steps: List[Dict[str, Any]] = []
    for index, trace in enumerate(production_traces):
        if isinstance(hierarchy, dict):
            options = [str(option) for option in hierarchy.keys()]
        elif isinstance(hierarchy, list):
            options = [str(option) for option in hierarchy if isinstance(option, str) and option]
        else:
            raise ValueError("Stored production trace continues beyond a hierarchy leaf")

        expected_choice = str(trace.chosen_option or "")
        if not expected_choice or expected_choice not in options:
            raise ValueError(
                f"Stored production choice {expected_choice!r} is invalid at step {index + 1}"
            )
        if not trace.full_prompt:
            raise ValueError(f"Stored production prompt is missing at step {index + 1}")

        classification_steps.append(
            {
                "step_order": index,
                "rule_key": _rule_key(production_path),
                "prompt": trace.full_prompt,
                "options": options,
                "expected_choice": expected_choice,
            }
        )
        production_path.append(expected_choice)

        if isinstance(hierarchy, dict):
            next_level = hierarchy[expected_choice]
            if isinstance(next_level, (dict, list)):
                hierarchy = next_level
            elif isinstance(next_level, str):
                production_tags = [next_level]
                if (
                    len(production_path) >= 3
                    and production_path[1] == "Liens"
                    and production_path[2] in {"PSL", "ASL"}
                ):
                    production_tags.insert(0, production_path[2])
                hierarchy = next_level
            else:
                raise ValueError("Unsupported production hierarchy value")
        else:
            production_tags = [expected_choice]
            if (
                len(production_path) >= 4
                and production_path[1] == "Liens"
                and production_path[2] in {"PSL", "ASL"}
            ):
                production_tags.insert(0, production_path[2])
            hierarchy = expected_choice

    if isinstance(hierarchy, (dict, list)):
        raise ValueError("Stored production trace ended before reaching a hierarchy leaf")

    return PreparedCase(
        case_type="classification",
        case_id=conversation_id,
        conversation_id=conversation_id,
        email_id=email.id,
        result_index=None,
        objective=None,
        classification_steps=classification_steps,
        metadata={
            "source_email_id": str(email.id),
            "message_count": production_traces[0].message_count or len(emails),
            "evaluation_mode": "exact_production_trace_replay",
            "production_model": production_traces[-1].llm_model,
            "production_path": production_path,
            "production_tags": production_tags,
            "production_classified_at": max(trace.created_at for trace in production_traces).isoformat(),
        },
    )


def _encode_jpeg(image: Image.Image) -> str:
    output = io.BytesIO()
    image.convert("RGB").save(output, format="JPEG", quality=88, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def _render_document(content: bytes, content_type: str, filename: str) -> tuple[List[str], bool]:
    maximum_pages = 12
    if content_type.startswith("application/pdf") or filename.lower().endswith(".pdf"):
        pages = convert_from_bytes(content, dpi=160, fmt="jpeg", first_page=1, last_page=maximum_pages + 1)
        return [_encode_jpeg(page) for page in pages[:maximum_pages]], len(pages) > maximum_pages
    with Image.open(io.BytesIO(content)) as source:
        frames = [frame.copy() for frame in ImageSequence.Iterator(source)]
    return [_encode_jpeg(frame) for frame in frames[:maximum_pages]], len(frames) > maximum_pages


async def _prepare_vision(
    db: AsyncSession, email_id: str, result_index: int, objective: str
) -> PreparedCase:
    if objective not in {"rx", "lien"}:
        raise ValueError("objective must be rx or lien")
    content, content_type, filename = await get_vision_document(
        db, email_id=email_id, result_index=result_index
    )
    images, truncated = await asyncio.to_thread(_render_document, content, content_type, filename)
    if not images:
        raise ValueError("The selected document has no renderable pages")
    email = await db.get(Email, UUID(email_id))
    return PreparedCase(
        case_type="vision",
        case_id=f"{email_id}:{result_index}",
        conversation_id=email.front_conversation_id if email else None,
        email_id=UUID(email_id),
        result_index=result_index,
        objective=objective,
        images=images,
        metadata={
            "filename": filename,
            "content_type": content_type,
            "pages_sent": len(images),
            "truncated": truncated,
        },
    )


VISION_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "rx": {
        "type": "object",
        "properties": {
            "document_style": {"type": "string", "enum": ["printed", "handwritten", "mixed", "unknown"]},
            "provider": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"}, "credentials": {"type": "array", "items": {"type": "string"}},
                    "phone": {"type": "string"}, "email": {"type": "string"},
                },
                "required": ["name", "credentials", "phone", "email"], "additionalProperties": False,
            },
            "patient": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"}, "sex": {"type": "string"}, "date_of_birth": {"type": "string"},
                    "date_of_injury": {"type": "string"}, "phone": {"type": "string"},
                    "address": {
                        "type": "object",
                        "properties": {
                            "line1": {"type": "string"}, "line2": {"type": "string"},
                            "city": {"type": "string"}, "state": {"type": "string"},
                            "postal_code": {"type": "string"},
                        },
                        "required": ["line1", "line2", "city", "state", "postal_code"],
                        "additionalProperties": False,
                    },
                },
                "required": ["name", "sex", "date_of_birth", "date_of_injury", "phone", "address"], "additionalProperties": False,
            },
            "attorney": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"}, "phone": {"type": "string"},
                    "email": {"type": "string"},
                },
                "required": ["name", "phone", "email"], "additionalProperties": False,
            },
            "exams": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "cpt_codes": {"type": "array", "items": {"type": "string"}},
                        "description": {"type": "string"}, "body_parts": {"type": "array", "items": {"type": "string"}},
                        "laterality": {"type": "string"}, "contrast": {"type": "string"},
                        "selected_checkboxes": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["cpt_codes", "description", "body_parts", "laterality", "contrast", "selected_checkboxes"],
                    "additionalProperties": False,
                },
            },
            "diagnosis_codes": {"type": "array", "items": {"type": "string"}},
            "signatures": {
                "type": "object",
                "properties": {
                    "patient_present": {"type": "boolean"},
                    "attorney_present": {"type": "boolean"},
                    "provider_present": {"type": "boolean"},
                },
                "required": ["patient_present", "attorney_present", "provider_present"],
                "additionalProperties": False,
            },
        },
        "required": ["document_style", "provider", "patient", "attorney", "exams", "diagnosis_codes", "signatures"],
        "additionalProperties": False,
    },
    "lien": {
        "type": "object",
        "properties": {
            "document_style": {"type": "string", "enum": ["printed", "handwritten", "mixed", "unknown"]},
            "patient_id": {"type": "string"},
            "lien_types": {"type": "array", "items": {"type": "string"}},
            "barcode_values": {"type": "array", "items": {"type": "string"}},
            "signatures": {
                "type": "object",
                "properties": {
                    "attorney_present": {"type": "boolean"},
                    "patient_present": {"type": "boolean"},
                    "both_present": {"type": "boolean"},
                },
                "required": ["attorney_present", "patient_present", "both_present"],
                "additionalProperties": False,
            },
            "modifications": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string"},
                        "original_value": {"type": "string"},
                        "new_value": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["field", "original_value", "new_value", "description"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["document_style", "patient_id", "lien_types", "barcode_values", "signatures", "modifications"],
        "additionalProperties": False,
    },
}


VISION_PROMPTS = {
    "rx": "Extract the requested RX fields from every page. Record only visible evidence. Use empty strings or arrays for absent or unreadable values. Diagnosis codes includes any visible ICD-10, DX, diagnosis, or reason-for-study codes. Include patient address, marked boxes, circled laterality, handwriting style, and visible signatures.",
    "lien": "Extract the requested lien fields, 1D/2D barcode values, signature presence, and visible modifications. Record only visible evidence and never invent obscured or missing values.",
}


async def _evaluate_classification(spec: ModelSpec, prepared: PreparedCase) -> tuple[Dict[str, Any], Usage, Dict[str, Any]]:
    production_steps = prepared.classification_steps or []
    if not production_steps:
        raise ValueError("No production classification steps are available for replay")

    path: List[str] = []
    steps: List[Dict[str, Any]] = []
    usage = Usage(raw={"steps": []})
    validation_retries = 0
    system_prompt = (
        "You are an expert email classifier. Follow the instructions in the user message "
        "carefully and respond only with the chosen option name."
    )

    for production_step in production_steps:
        options = production_step["options"]
        schema = {
            "type": "object",
            "properties": {
                "chosen_option": {"type": "string", "enum": options},
                "conversation_summary": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["chosen_option", "conversation_summary", "reason"],
            "additionalProperties": False,
        }
        call: Optional[CallResult] = None
        choice = ""
        for output_attempt in range(3):
            call = await _call_model(
                spec,
                production_step["prompt"],
                schema,
                max_output_tokens=3_000,
                system_prompt=system_prompt,
            )
            usage.add(call.usage)
            if usage.raw is not None:
                usage.raw["steps"].append(call.usage.raw or {})
            choice = str(call.output.get("chosen_option") or "")
            if choice in options:
                break
            if output_attempt < 2:
                validation_retries += 1
        if call is None or choice not in options:
            raise EvaluationExecutionError(
                f"Model returned invalid output for {production_step['rule_key']} after 3 attempts",
                usage,
                call.output if call else None,
            )

        expected_choice = production_step["expected_choice"]
        path.append(choice)
        matches = choice == expected_choice
        steps.append(
            {
                "rule_key": production_step["rule_key"],
                "expected_choice": expected_choice,
                "choice": choice,
                "matches_production": matches,
            }
        )
        if not matches:
            return (
                {
                    "evaluation_mode": "exact_production_trace_replay",
                    "production_match": False,
                    "classification_path": path,
                    "production_path": prepared.metadata.get("production_path", []),
                    "failed_at_step": len(steps),
                    "expected_choice": expected_choice,
                    "actual_choice": choice,
                    "steps": steps,
                },
                usage,
                {
                    "classification_steps": len(steps),
                    "validation_retries": validation_retries,
                    "production_match": False,
                },
            )

    return (
        {
            "evaluation_mode": "exact_production_trace_replay",
            "production_match": True,
            "classification_path": path,
            "production_path": prepared.metadata.get("production_path", []),
            "tags": prepared.metadata.get("production_tags", []),
            "failed_at_step": None,
            "steps": steps,
        },
        usage,
        {
            "classification_steps": len(steps),
            "validation_retries": validation_retries,
            "production_match": True,
        },
    )


async def _evaluate_one(spec: ModelSpec, prepared: PreparedCase) -> Dict[str, Any]:
    started = datetime.now(timezone.utc)
    usage = Usage()
    try:
        if prepared.case_type == "classification":
            output, usage, extra_metadata = await _evaluate_classification(spec, prepared)
        else:
            output_budget = 6_000
            call = await _call_model(
                spec,
                VISION_PROMPTS[prepared.objective or "rx"],
                VISION_SCHEMAS[prepared.objective or "rx"],
                prepared.images or [],
                max_output_tokens=output_budget,
            )
            output, usage, extra_metadata = call.output, call.usage, {}
            extra_metadata["max_output_tokens"] = output_budget
            extra_metadata["provider_retries"] = call.retry_count
            if call.incomplete_reason:
                extra_metadata["provider_finish_reason"] = call.incomplete_reason
        if output and output.get("parse_error"):
            status = "incomplete"
            error_text = "The provider output ended before a complete JSON result was returned."
        elif prepared.case_type == "vision" and call.incomplete_reason:
            status = "incomplete"
            error_text = f"Provider finish reason: {call.incomplete_reason}"
        else:
            status = "completed"
            error_text = None
    except Exception as exc:  # Keep one model failure from hiding other results.
        if isinstance(exc, EvaluationExecutionError):
            usage = exc.usage
            output = exc.output
        else:
            output = None
        extra_metadata = {}
        status = "error"
        if isinstance(exc, httpx.HTTPStatusError):
            detail = exc.response.text[:1500]
            error_text = f"{exc.response.status_code} from {spec.provider}: {detail}"
        else:
            error_text = str(exc)[:2000]
    completed = datetime.now(timezone.utc)
    metadata = {**(prepared.metadata or {}), **extra_metadata, "rate_card": _rate_snapshot(spec), "duration_ms": int((completed - started).total_seconds() * 1000)}
    return {
        "spec": spec,
        "status": status,
        "output": output,
        "usage": usage,
        "cost": calculate_cost(spec, usage),
        "error_text": error_text,
        "metadata": metadata,
        "completed_at": completed,
    }


async def run_model_evaluation(
    db: AsyncSession, request: ModelEvaluationRunRequest
) -> tuple[str, List[ModelEvaluationRun]]:
    if request.case_type == "classification":
        if not request.conversation_id:
            raise ValueError("conversation_id is required for classification")
        prepared = await _prepare_classification(db, request.conversation_id)
    elif request.case_type == "vision":
        if not request.email_id or request.result_index is None or not request.objective:
            raise ValueError("email_id, result_index, and objective are required for vision")
        prepared = await _prepare_vision(db, request.email_id, request.result_index, request.objective)
    else:
        raise ValueError("case_type must be classification or vision")

    enabled_by_key = await get_model_settings(db)
    specs: List[ModelSpec] = []
    for model_key in dict.fromkeys(request.model_keys):
        spec = MODEL_BY_KEY.get(model_key)
        if not spec:
            raise ValueError(f"Unknown evaluation model: {model_key}")
        if request.case_type not in spec.case_types:
            raise ValueError(f"{spec.display_name} does not support {request.case_type} cases")
        if not enabled_by_key.get(spec.key, True):
            raise ValueError(f"{spec.display_name} is disabled for evaluation")
        specs.append(spec)

    evaluated = await asyncio.gather(*(_evaluate_one(spec, prepared) for spec in specs))
    model_keys = [spec.key for spec in specs]
    await db.execute(
        update(ModelEvaluationCaseReview)
        .where(
            ModelEvaluationCaseReview.case_type == prepared.case_type,
            ModelEvaluationCaseReview.case_id == prepared.case_id,
            ModelEvaluationCaseReview.seed_model_key.in_(model_keys),
        )
        .values(seed_run_id=None)
    )
    await db.execute(
        delete(ModelEvaluationRun).where(
            ModelEvaluationRun.case_type == prepared.case_type,
            ModelEvaluationRun.case_id == prepared.case_id,
            ModelEvaluationRun.model_key.in_(model_keys),
        )
    )
    rows: List[ModelEvaluationRun] = []
    for item in evaluated:
        spec = item["spec"]
        usage: Usage = item["usage"]
        rows.append(
            ModelEvaluationRun(
                case_type=prepared.case_type,
                case_id=prepared.case_id,
                conversation_id=prepared.conversation_id,
                email_id=prepared.email_id,
                result_index=prepared.result_index,
                objective=prepared.objective,
                provider=spec.provider,
                model=spec.model,
                model_key=spec.key,
                status=item["status"],
                output=item["output"],
                raw_usage=usage.raw,
                request_metadata=item["metadata"],
                input_tokens=usage.input_tokens,
                cached_input_tokens=usage.cached_input_tokens,
                cache_write_tokens=usage.cache_write_tokens,
                output_tokens=usage.output_tokens,
                total_tokens=usage.input_tokens + usage.output_tokens,
                cost_usd=item["cost"],
                error_text=item["error_text"],
                completed_at=item["completed_at"],
            )
        )
    db.add_all(rows)
    await db.commit()
    for row in rows:
        await db.refresh(row)
    return prepared.case_id, rows


async def list_model_evaluation_runs(
    db: AsyncSession, *, case_type: str, case_id: str
) -> List[ModelEvaluationRun]:
    if case_type not in {"classification", "vision"}:
        raise ValueError("case_type must be classification or vision")
    result = await db.execute(
        select(ModelEvaluationRun)
        .where(
            ModelEvaluationRun.case_type == case_type,
            ModelEvaluationRun.case_id == case_id,
        )
        .order_by(ModelEvaluationRun.created_at.desc())
        .limit(100)
    )
    return list(result.scalars().all())


async def get_case_ground_truth(
    db: AsyncSession, *, case_type: str, case_id: str
) -> Optional[ModelEvaluationCaseReview]:
    if case_type not in {"classification", "vision"}:
        raise ValueError("case_type must be classification or vision")
    result = await db.execute(
        select(ModelEvaluationCaseReview).where(
            ModelEvaluationCaseReview.case_type == case_type,
            ModelEvaluationCaseReview.case_id == case_id,
        )
    )
    return result.scalar_one_or_none()


async def save_case_ground_truth(
    db: AsyncSession,
    *,
    case_type: str,
    case_id: str,
    reference_output: Optional[Dict[str, Any]],
    reference_text: Optional[str],
    notes: Optional[str],
    reference_source: str,
    seed_model_key: Optional[str],
    seed_run_id: Optional[str],
    reviewed_by: str,
) -> ModelEvaluationCaseReview:
    allowed_sources = {"human", "ai_seeded", "ai_seeded_human_edited", "unknown"}
    if reference_source not in allowed_sources:
        raise ValueError("Invalid ground-truth reference source")
    parsed_seed_run_id: Optional[UUID] = None
    if seed_run_id:
        try:
            parsed_seed_run_id = UUID(seed_run_id)
        except ValueError as exc:
            raise ValueError("Invalid seed run ID") from exc
    review = await get_case_ground_truth(db, case_type=case_type, case_id=case_id)
    if review is None:
        review = ModelEvaluationCaseReview(case_type=case_type, case_id=case_id)
        db.add(review)
    review.reference_output = _without_extracted_notes(reference_output) if case_type == "vision" else reference_output
    review.reference_text = reference_text
    review.notes = notes
    review.reference_source = reference_source
    review.seed_model_key = seed_model_key
    review.seed_run_id = parsed_seed_run_id
    review.reviewed_by = reviewed_by
    review.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(review)
    return review


async def review_model_evaluation_run(
    db: AsyncSession,
    *,
    run_id: str,
    human_rating: Optional[str],
    human_notes: Optional[str],
    is_preferred: bool,
    reviewed_by: str,
) -> ModelEvaluationRun:
    allowed_ratings = {None, "correct", "minor_errors", "major_errors", "incorrect"}
    if human_rating not in allowed_ratings:
        raise ValueError("Invalid human rating")
    try:
        run_key = UUID(run_id)
    except ValueError as exc:
        raise LookupError("Evaluation run not found") from exc
    row = await db.get(ModelEvaluationRun, run_key)
    if row is None:
        raise LookupError("Evaluation run not found")
    if is_preferred:
        await db.execute(
            update(ModelEvaluationRun)
            .where(
                ModelEvaluationRun.case_type == row.case_type,
                ModelEvaluationRun.case_id == row.case_id,
                ModelEvaluationRun.id != row.id,
            )
            .values(is_preferred=False)
        )
    row.human_rating = human_rating
    row.human_notes = human_notes
    row.is_preferred = is_preferred
    row.reviewed_by = reviewed_by
    row.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


def serialize_ground_truth(
    review: Optional[ModelEvaluationCaseReview], *, case_type: str, case_id: str
) -> Dict[str, Any]:
    reference_output = review.reference_output if review else None
    if case_type == "vision":
        reference_output = _without_extracted_notes(reference_output)
    return {
        "case_type": case_type,
        "case_id": case_id,
        "reference_output": reference_output,
        "reference_text": review.reference_text if review else None,
        "notes": review.notes if review else None,
        "reference_source": review.reference_source if review else "unknown",
        "seed_model_key": review.seed_model_key if review else None,
        "seed_run_id": str(review.seed_run_id) if review and review.seed_run_id else None,
        "reviewed_by": review.reviewed_by if review else None,
        "updated_at": review.updated_at if review else None,
    }


def serialize_run(row: ModelEvaluationRun) -> Dict[str, Any]:
    output = _without_extracted_notes(row.output) if row.case_type == "vision" else row.output
    return {
        "id": str(row.id), "case_type": row.case_type, "case_id": row.case_id,
        "conversation_id": row.conversation_id, "email_id": str(row.email_id) if row.email_id else None,
        "result_index": row.result_index, "objective": row.objective, "provider": row.provider,
        "model": row.model, "model_key": row.model_key, "status": row.status,
        "output": output, "raw_usage": row.raw_usage, "request_metadata": row.request_metadata,
        "input_tokens": row.input_tokens, "cached_input_tokens": row.cached_input_tokens,
        "cache_write_tokens": row.cache_write_tokens, "output_tokens": row.output_tokens,
        "total_tokens": row.total_tokens, "cost_usd": float(row.cost_usd or 0),
        "error_text": row.error_text, "human_rating": row.human_rating,
        "human_notes": row.human_notes, "is_preferred": row.is_preferred,
        "reviewed_by": row.reviewed_by, "reviewed_at": row.reviewed_at,
        "created_at": row.created_at, "completed_at": row.completed_at,
    }
