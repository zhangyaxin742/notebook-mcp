from __future__ import annotations

from collections.abc import Iterator

from src.retrieval.models import CanonicalChunk
from src.store.models import ChunkRecord
from src.store.settings import StorePaths
from src.store.sqlite_store import SQLiteStore


class SQLiteChunkRepository:
    def __init__(
        self,
        store: SQLiteStore | None = None,
        *,
        paths: StorePaths | None = None,
    ) -> None:
        resolved_paths = paths or StorePaths.from_env()
        self._store = store or SQLiteStore(resolved_paths)
        self._store.initialize()

    def iter_chunks(
        self,
        *,
        notebook_id: str | None = None,
        document_id: str | None = None,
    ) -> Iterator[CanonicalChunk]:
        for record in self._store.iter_chunks(
            notebook_id=notebook_id,
            document_id=document_id,
        ):
            yield self._to_canonical_chunk(record)

    def _to_canonical_chunk(self, record: ChunkRecord) -> CanonicalChunk:
        return CanonicalChunk(
            id=record.id,
            document_id=record.document_id,
            notebook_id=record.notebook_id,
            chunk_index=record.chunk_index,
            text=record.text,
            content_sha256=record.content_sha256,
            char_start=record.char_start,
            char_end=record.char_end,
            token_count_estimate=record.token_count_estimate,
            metadata=dict(record.metadata),
        )
