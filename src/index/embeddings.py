from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from src.retrieval.models import CanonicalChunk


class EmbeddingBackend(Protocol):
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[tuple[float, ...]]:
        ...

    def embed_query(self, text: str) -> tuple[float, ...]:
        ...


class HashingEmbeddingBackend:
    def __init__(self, dimensions: int = 256) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive.")
        self.dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> tuple[float, ...]:
        return self._embed(text)

    def _embed(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self.dimensions
        counts = Counter(_tokenize(text))
        if not counts:
            return tuple(vector)

        for token, frequency in counts.items():
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], byteorder="big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign * (1.0 + math.log1p(frequency))

        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude == 0:
            return tuple(vector)

        return tuple(value / magnitude for value in vector)


@dataclass(frozen=True)
class SemanticChunkHit:
    chunk_id: str
    document_id: str
    score: float


class SemanticChunkIndex:
    def __init__(self, backend: EmbeddingBackend) -> None:
        self._backend = backend
        self._chunks_by_id: dict[str, CanonicalChunk] = {}
        self._vectors_by_chunk_id: dict[str, tuple[float, ...]] = {}

    def replace(self, chunks: list[CanonicalChunk]) -> None:
        ordered_chunks = sorted(chunks, key=lambda chunk: (chunk.document_id, chunk.chunk_index, chunk.id))
        texts = [
            f"{chunk.metadata.get('document_title', '')}\n\n{chunk.text}".strip()
            for chunk in ordered_chunks
        ]
        vectors = self._backend.embed_documents(texts)
        self._chunks_by_id = {chunk.id: chunk for chunk in ordered_chunks}
        self._vectors_by_chunk_id = {
            chunk.id: vector for chunk, vector in zip(ordered_chunks, vectors, strict=True)
        }

    def search(
        self,
        query: str,
        *,
        notebook_id: str | None = None,
        document_kind: str | None = None,
        limit: int = 20,
    ) -> list[SemanticChunkHit]:
        query_vector = self._backend.embed_query(query)
        if not any(query_vector):
            return []

        hits: list[SemanticChunkHit] = []
        for chunk_id, vector in self._vectors_by_chunk_id.items():
            chunk = self._chunks_by_id[chunk_id]
            if notebook_id is not None and chunk.notebook_id != notebook_id:
                continue
            if document_kind is not None and chunk.metadata.get("document_kind") != document_kind:
                continue

            score = _cosine_similarity(query_vector, vector)
            if score <= 0:
                continue

            hits.append(
                SemanticChunkHit(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    score=score,
                )
            )

        hits.sort(key=lambda hit: (-hit.score, hit.document_id, hit.chunk_id))
        return hits[:limit]


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True))
