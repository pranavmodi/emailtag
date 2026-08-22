import asyncio
from decimal import Decimal

import pytest
import httpx

from app.services.model_evaluation_runner import (
    MODEL_BY_KEY,
    CallResult,
    PreparedCase,
    Usage,
    VISION_SCHEMAS,
    _evaluate_classification,
    _evaluate_one,
    _call_chat_compatible,
    _call_openai_production_classification,
    _extract_json,
    _post_with_retries,
    _rule_key,
    calculate_cost,
    get_model_catalog,
)


def test_catalog_filters_by_case_type_and_reports_key_availability(monkeypatch):
    monkeypatch.delenv("MODEL_EVAL_TOGETHER_API_KEY", raising=False)
    models = get_model_catalog("vision")

    assert models
    assert all("vision" in model["case_types"] for model in models)
    assert not any(model["key"] == "together:openai/gpt-oss-20b" for model in models)


def test_top_open_vision_candidates_are_available_for_document_evaluation(monkeypatch):
    monkeypatch.setenv("MODEL_EVAL_TOGETHER_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_EVAL_FIREWORKS_API_KEY", "test-key")
    models = {model["key"]: model for model in get_model_catalog("vision")}

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    expected = {
        "together:MiniMaxAI/MiniMax-M3",
        "together:google/gemma-4-31B-it",
        "fireworks:accounts/fireworks/models/kimi-k2p6",
        "openrouter:qwen/qwen3-vl-8b-instruct",
        "openrouter:qwen/qwen3.5-27b",
        "openrouter:z-ai/glm-4.5v",
    }
    assert expected <= models.keys()
    assert all(models[key]["available"] for key in expected)
    assert "together:Qwen/Qwen3-VL-8B-Instruct" not in models
    assert "together:Qwen/Qwen3.5-9B" not in models


def test_latest_requested_vendor_models_are_in_catalog():
    assert "openai:gpt-5-mini" in MODEL_BY_KEY
    assert "gemini:gemini-3.7-flash" in MODEL_BY_KEY
    assert "xai:grok-4.6" in MODEL_BY_KEY


def test_cost_uses_cached_and_cache_write_rates():
    spec = MODEL_BY_KEY["openai:gpt-5.6-luna"]
    usage = Usage(
        input_tokens=1_000_000,
        cached_input_tokens=100_000,
        cache_write_tokens=200_000,
        output_tokens=100_000,
    )

    # 700K ordinary input + 100K cached + 200K cache-write + 100K output.
    assert calculate_cost(spec, usage) == Decimal("0.31200000")


@pytest.mark.parametrize("objective", ["rx", "lien"])
def test_document_schemas_do_not_request_unstructured_notes(objective):
    schema = VISION_SCHEMAS[objective]

    assert "notes" not in schema["properties"]
    assert "notes" not in schema["required"]


def test_rx_schema_includes_address_and_diagnosis_codes():
    schema = VISION_SCHEMAS["rx"]

    assert "diagnosis_codes" in schema["required"]
    assert "address" in schema["properties"]["patient"]["required"]
    assert schema["properties"]["diagnosis_codes"]["type"] == "array"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"choice":"A"}', {"choice": "A"}),
        ('```json\n{"choice":"B"}\n```', {"choice": "B"}),
        ('Answer: {"choice":"C"}.', {"choice": "C"}),
    ],
)
def test_extract_json_accepts_common_provider_wrappers(raw, expected):
    assert _extract_json(raw) == expected


def test_rule_key_matches_production_sanitizing():
    assert _rule_key([]) == "ROOT"
    assert _rule_key(["New & Existing", "RX/Docs-Test."]) == "ROOT_NEW_AND_EXISTING_RX_DOCS_TEST"


def test_invalid_catalog_case_type_is_rejected():
    with pytest.raises(ValueError, match="classification or vision"):
        get_model_catalog("production")


def test_classification_replay_stops_at_first_production_divergence(monkeypatch):
    calls = []

    async def fake_call(
        spec,
        prompt,
        schema,
        images=(),
        max_output_tokens=3000,
        system_prompt=None,
    ):
        calls.append(prompt)
        return CallResult(
            output={
                "chosen_option": "Medical Records & Images",
                "conversation_summary": "Records request",
                "reason": "The email requests records",
            },
            usage=Usage(input_tokens=100, output_tokens=20),
        )

    monkeypatch.setattr("app.services.model_evaluation_runner._call_model", fake_call)
    prepared = PreparedCase(
        case_type="classification",
        case_id="cnv_test",
        conversation_id="cnv_test",
        email_id=None,
        result_index=None,
        objective=None,
        classification_steps=[
            {
                "rule_key": "ROOT",
                "prompt": "exact stored production prompt step 1",
                "options": ["Scheduling", "Medical Records & Images"],
                "expected_choice": "Scheduling",
            },
            {
                "rule_key": "ROOT_SCHEDULING",
                "prompt": "exact stored production prompt step 2",
                "options": ["RX", "Cancel Request"],
                "expected_choice": "RX",
            },
        ],
        metadata={
            "production_path": ["Scheduling", "RX"],
            "production_tags": ["RX"],
        },
    )

    output, usage, metadata = asyncio.run(
        _evaluate_classification(MODEL_BY_KEY["openai:gpt-5.6-luna"], prepared)
    )

    assert calls == ["exact stored production prompt step 1"]
    assert output["production_match"] is False
    assert output["failed_at_step"] == 1
    assert output["expected_choice"] == "Scheduling"
    assert output["actual_choice"] == "Medical Records & Images"
    assert usage.input_tokens == 100
    assert metadata["production_match"] is False


def test_provider_post_retries_transient_status(monkeypatch):
    class FakeClient:
        def __init__(self):
            self.calls = 0

        async def post(self, url, **kwargs):
            self.calls += 1
            request = httpx.Request("POST", url)
            if self.calls == 1:
                return httpx.Response(503, request=request, json={"error": "overloaded"})
            return httpx.Response(200, request=request, json={"ok": True})

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr("app.services.model_evaluation_runner.asyncio.sleep", no_sleep)
    client = FakeClient()
    response, retries = asyncio.run(_post_with_retries(client, "https://provider.test"))

    assert response.status_code == 200
    assert retries == 1
    assert client.calls == 2


def test_provider_post_does_not_retry_permanent_client_error(monkeypatch):
    class FakeClient:
        def __init__(self):
            self.calls = 0

        async def post(self, url, **kwargs):
            self.calls += 1
            return httpx.Response(400, request=httpx.Request("POST", url), json={"error": "bad request"})

    client = FakeClient()
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(_post_with_retries(client, "https://provider.test"))
    assert client.calls == 1


def test_gpt5_mini_evaluation_matches_production_request_profile(monkeypatch):
    captured = {}

    async def fake_post(_client, url, **kwargs):
        captured["url"] = url
        captured["payload"] = kwargs["json"]
        response = httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"chosen_option":"Scheduling","conversation_summary":"Summary","reason":"Reason"}'
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            },
        )
        return response, 0

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("app.services.model_evaluation_runner._post_with_retries", fake_post)
    schema = {
        "type": "object",
        "properties": {
            "chosen_option": {"type": "string", "enum": ["Scheduling"]},
            "conversation_summary": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["chosen_option", "conversation_summary", "reason"],
        "additionalProperties": False,
    }

    result = asyncio.run(
        _call_openai_production_classification(
            MODEL_BY_KEY["openai:gpt-5-mini"],
            "exact stored production prompt",
            schema,
        )
    )

    assert result.output["chosen_option"] == "Scheduling"
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["payload"]["reasoning_effort"] == "medium"
    assert captured["payload"]["max_completion_tokens"] == 16_000
    assert captured["payload"]["response_format"]["json_schema"]["name"] == "classification_response"


def test_structured_document_marks_provider_truncation(monkeypatch):
    captured = {}

    async def fake_call(spec, prompt, schema, images=(), max_output_tokens=3000):
        captured["max_output_tokens"] = max_output_tokens
        return CallResult(
            output={"unparsed_text": "partial", "parse_error": "truncated"},
            usage=Usage(input_tokens=100, output_tokens=max_output_tokens),
            incomplete_reason="max_output_tokens",
        )

    monkeypatch.setattr("app.services.model_evaluation_runner._call_model", fake_call)
    prepared = PreparedCase(
        case_type="vision",
        case_id="synthetic:0",
        conversation_id="synthetic",
        email_id=None,
        result_index=0,
        objective="rx",
        images=["data:image/png;base64,synthetic"],
    )

    result = asyncio.run(_evaluate_one(MODEL_BY_KEY["openai:gpt-5.6-luna"], prepared))

    assert captured["max_output_tokens"] == 6_000
    assert result["status"] == "incomplete"
    assert result["usage"].output_tokens == 6_000


def test_openrouter_calls_enforce_zdr_and_no_data_collection(monkeypatch):
    captured = {}

    async def fake_post(_client, _url, **kwargs):
        captured.update(kwargs["json"])
        response = httpx.Response(
            200,
            request=httpx.Request("POST", "https://openrouter.test"),
            json={
                "choices": [{"message": {"content": '{"choice":"A"}'}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2, "cost": 0.00001},
            },
        )
        return response, 0

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr("app.services.model_evaluation_runner._post_with_retries", fake_post)
    result = asyncio.run(
        _call_chat_compatible(
            MODEL_BY_KEY["openrouter:qwen/qwen3-vl-8b-instruct"],
            "Choose A",
            {"type": "object", "properties": {"choice": {"type": "string"}}},
            [],
            100,
        )
    )

    assert result.output == {"choice": "A"}
    assert captured["provider"] == {
        "zdr": True,
        "data_collection": "deny",
        "allow_fallbacks": True,
    }
    assert result.usage.provider_cost == Decimal("0.00001")
