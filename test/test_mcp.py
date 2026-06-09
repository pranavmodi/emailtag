import json

import pytest

from app.mcp import _parse_mcp_response_text


def test_parse_mcp_sse_with_keepalive_pings():
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {"success": False, "error": "An unexpected error occurred: "}
                    ),
                }
            ],
            "isError": False,
        },
    }
    response_text = (
        ": ping - 2026-06-09 10:29:59.629102+00:00\n\n"
        ": ping - 2026-06-09 10:30:14.630098+00:00\n\n"
        "event: message\n"
        f"data: {json.dumps(payload)}"
    )

    assert _parse_mcp_response_text(response_text) == payload


def test_parse_mcp_response_rejects_raw_text():
    with pytest.raises(json.JSONDecodeError):
        _parse_mcp_response_text("not json and not sse")
