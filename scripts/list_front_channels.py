#!/usr/bin/env python3
"""List all FrontApp channels and their IDs.

This utility pulls the channel list using the Front REST API and prints a
readable table.  It relies on the same environment variables / `.env` file
that the main application uses (`FRONT_AUTH_TOKEN` and
`FRONT_API_BASE_URL`).

Usage
-----
$ python scripts/list_front_channels.py

Ensure your virtualenv has the required libraries installed (``httpx`` and
``python-dotenv`` if you want to load the .env manually – the application
already does this via ``app.core.config.settings``).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any, Dict, List, Optional

import httpx

# Load environment variables from `.env` if present, *without* instantiating the
# full Pydantic Settings (which requires some optional variables you may not
# have set in your local environment).
try:
    # ``python-dotenv`` is a lightweight optional dependency already used in
    # other helper scripts.  If it is not installed the user will simply need
    # to export variables manually.
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except ModuleNotFoundError:
    # dotenv not available – assume variables are already in os.environ.
    pass

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _get_env_var(name: str) -> Optional[str]:
    """Fetch *name* from ``os.environ`` and strip quotes/spaces."""

    val = os.getenv(name)
    if val is None:
        return None
    # Tolerate accidental surrounding quotes in .env ("value" | 'value')
    return val.strip().strip("'\"")


async def list_channels() -> List[Dict[str, Any]]:
    """Fetch the list of channels from Front.

    Returns
    -------
    List[Dict[str, Any]]
        Raw channel objects as returned by the Front API.
    """

    front_api_base_url = _get_env_var("FRONT_API_BASE_URL")
    front_auth_token = _get_env_var("FRONT_AUTH_TOKEN")

    if not front_api_base_url or not front_auth_token:
        raise RuntimeError(
            "Missing FRONT_API_BASE_URL or FRONT_AUTH_TOKEN. "
            "Ensure they are set in your shell or .env file."
        )

    headers = {
        "Authorization": f"Bearer {front_auth_token}",
        "Accept": "application/json",
    }
    url = f"{front_api_base_url.rstrip('/')}/channels"

    async with httpx.AsyncClient(verify=False) as client:  # noqa: S501 – demo script
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data.get("_results", [])


def _pretty_print(channels: List[Dict[str, Any]]) -> None:
    """Print a simple two-column table of *Name* and *ID*."""

    if not channels:
        print("No channels found.")
        return

    name_col_width = max(len(ch.get("name", "")) for ch in channels)
    header_name = "Channel Name"
    header_id = "Channel ID"
    name_col_width = max(name_col_width, len(header_name))

    sep_line = f"{'-' * name_col_width}-+-{'-' * len(header_id)}"
    print(f"{header_name:<{name_col_width}} | {header_id}")
    print(sep_line)

    for ch in channels:
        print(f"{ch.get('name', ''):<{name_col_width}} | {ch.get('id')}")


async def main() -> None:
    try:
        channels = await list_channels()
        _pretty_print(channels)
    except httpx.HTTPStatusError as http_err:
        logger.error(
            "Front API responded with error %s – %s",
            http_err.response.status_code,
            http_err.response.text,
        )
    except Exception as exc:
        logger.exception("Failed to fetch channel list: %s", exc)


if __name__ == "__main__":
    asyncio.run(main()) 