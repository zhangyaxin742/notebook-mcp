from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
import json


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def content_sha256(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


def canonical_json_compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True)
class NotebookRecord:
    id: str
    origin: str
    title: str
    url: str
    raw_id: str | None = None
    derived_key: str | None = None
    source_count: int | None = None
    artifact_count: int | None = None
    last_synced_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_count": self.artifact_count,
            "derived_key": self.derived_key,
            "id": self.id,
            "last_synced_at": self.last_synced_at,
            "metadata": self.metadata,
            "origin": self.origin,
            "raw_id": self.raw_id,
            "source_count": self.source_count,
            "title": self.title,
            "url": self.url,
        }


@dataclass(frozen=True)
class SourceRecord:
    id: str
    notebook_id: str
    origin: str
    title: str
    url: str
    source_type: str
    raw_id: str | None = None
    derived_key: str | None = None
    summary_text: str | None = None
    created_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "derived_key": self.derived_key,
            "id": self.id,
            "metadata": self.metadata,
            "notebook_id": self.notebook_id,
            "origin": self.origin,
            "raw_id": self.raw_id,
            "source_type": self.source_type,
            "summary_text": self.summary_text,
            "title": self.title,
            "url": self.url,
        }


@dataclass(frozen=True)
class ArtifactRecord:
    id: str
    notebook_id: str
    origin: str
    artifact_kind: str
    title: str
    url: str
    raw_id: str | None = None
    derived_key: str | None = None
    text: str | None = None
    mime_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_kind": self.artifact_kind,
            "derived_key": self.derived_key,
            "id": self.id,
            "metadata": self.metadata,
            "mime_type": self.mime_type,
            "notebook_id": self.notebook_id,
            "origin": self.origin,
            "raw_id": self.raw_id,
            "text": self.text,
            "title": self.title,
            "url": self.url,
        }


@dataclass(frozen=True)
class DocumentRecord:
    id: str
    notebook_id: str
    origin_type: str
    origin_id: str
    document_kind: str
    title: str
    text: str
    url: str
    content_sha256: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_sha256": self.content_sha256,
            "document_kind": self.document_kind,
            "id": self.id,
            "metadata": self.metadata,
            "notebook_id": self.notebook_id,
            "origin_id": self.origin_id,
            "origin_type": self.origin_type,
            "text": self.text,
            "title": self.title,
            "url": self.url,
        }


@dataclass(frozen=True)
class ChunkRecord:
    id: str
    document_id: str
    notebook_id: str
    chunk_index: int
    text: str
    content_sha256: str
    char_start: int | None = None
    char_end: int | None = None
    token_count_estimate: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "char_end": self.char_end,
            "char_start": self.char_start,
            "chunk_index": self.chunk_index,
            "content_sha256": self.content_sha256,
            "document_id": self.document_id,
            "id": self.id,
            "metadata": self.metadata,
            "notebook_id": self.notebook_id,
            "text": self.text,
            "token_count_estimate": self.token_count_estimate,
        }


@dataclass(frozen=True)
class SyncFailure:
    entity_type: str
    message: str
    entity_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "details": self.details,
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "message": self.message,
        }


@dataclass(frozen=True)
class SyncRunRecord:
    id: str
    status: str
    started_at: str
    notebook_id: str | None = None
    completed_at: str | None = None
    source_count: int = 0
    artifact_count: int = 0
    document_count: int = 0
    chunk_count: int = 0
    error_count: int = 0
    summary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_count": self.artifact_count,
            "chunk_count": self.chunk_count,
            "completed_at": self.completed_at,
            "document_count": self.document_count,
            "error_count": self.error_count,
            "id": self.id,
            "notebook_id": self.notebook_id,
            "source_count": self.source_count,
            "started_at": self.started_at,
            "status": self.status,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class NormalizedNotebookSnapshot:
    notebook: NotebookRecord
    sources: tuple[SourceRecord, ...]
    artifacts: tuple[ArtifactRecord, ...]
    documents: tuple[DocumentRecord, ...]
    chunks: tuple[ChunkRecord, ...] = ()
    failures: tuple[SyncFailure, ...] = ()


@dataclass(frozen=True)
class SyncOutcome:
    run: SyncRunRecord
    snapshot: NormalizedNotebookSnapshot | None = None
    failures: tuple[SyncFailure, ...] = ()

