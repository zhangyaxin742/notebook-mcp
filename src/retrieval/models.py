from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CanonicalDocument:
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


@dataclass(frozen=True)
class CanonicalChunk:
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


@dataclass(frozen=True)
class SearchResult:
    id: str
    notebook_id: str
    title: str
    url: str
    document_kind: str
    origin_type: str
    origin_id: str
    score: float
    lexical_score: float
    semantic_score: float
    matched_chunk_ids: tuple[str, ...] = ()

