from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
import json
from typing import Any


SENSITIVE_KEYWORDS = (
    "authorization",
    "cookie",
    "csrf",
    "session",
    "token",
)


def _looks_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(keyword in lowered for keyword in SENSITIVE_KEYWORDS)


def scrub_value(key: str, value: Any) -> Any:
    if key == "session_summary":
        return value
    if _looks_sensitive(key):
        return "<redacted>"
    if isinstance(value, str) and value.startswith("Bearer "):
        return "Bearer <redacted>"
    return value


def scrub_payload(payload: Any, key: str = "") -> Any:
    if isinstance(payload, Mapping):
        return {
            str(child_key): scrub_payload(
                scrub_value(str(child_key), child_value),
                key=str(child_key),
            )
            for child_key, child_value in payload.items()
        }
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        return [scrub_payload(item, key=key) for item in payload]
    return payload


def write_scrubbed_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(scrub_payload(payload), handle, indent=2, sort_keys=True)
        handle.write("\n")
