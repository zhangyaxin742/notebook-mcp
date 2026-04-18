from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any


def derive_entity_key(seed: str) -> str:
    return sha256(seed.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class RawNotebook:
    entity_key: str
    raw_id: str | None
    title: str
    url: str | None
    source_count: int | None = None
    artifact_count: int | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawSource:
    entity_key: str
    notebook_key: str
    raw_id: str | None
    title: str
    url: str | None
    source_type: str | None = None
    summary_text: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawArtifact:
    entity_key: str
    notebook_key: str
    raw_id: str | None
    artifact_kind: str | None
    title: str
    url: str | None
    text: str | None = None
    mime_type: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawNotebookBundle:
    notebook: RawNotebook
    sources: tuple[RawSource, ...]
    artifacts: tuple[RawArtifact, ...]


@dataclass(frozen=True)
class ConnectorHealth:
    ok: bool
    transport: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
