"""Pluggable external sensor adapter contract for firm trigger events.

Adapters normalize vendor-specific payloads into `ExternalFirmSignalIn`-compatible
dicts. The core persists only normalized firm events; vendors never become the
system of record.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict


class FirmEventSensorAdapter(ABC):
    """Contract every external sensor driver must implement."""

    vendor: str

    @abstractmethod
    def normalize(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Return a normalized external signal payload for `/events/external`."""


class StubFirmEventSensorAdapter(FirmEventSensorAdapter):
    """No-op example adapter for future Common Room, Trigify, or scraper drivers."""

    vendor = "stub"

    def normalize(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        signal_type = payload.get("signal_type", "news_mention")
        return {
            "vendor": self.vendor,
            "signal_type": signal_type,
            "occurred_at": payload.get("occurred_at") or datetime.utcnow().isoformat(),
            "score": payload.get("score", 50.0),
            "dedup_key": payload.get("dedup_key"),
            "detail": payload.get("detail", payload),
            "alias_type": payload.get("alias_type"),
            "alias_value": payload.get("alias_value"),
            "website": payload.get("website"),
            "domain": payload.get("domain"),
            "email": payload.get("email"),
            "legacy_pif_id": payload.get("legacy_pif_id"),
        }
