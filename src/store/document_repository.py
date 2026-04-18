from __future__ import annotations

from collections.abc import Iterator

from src.retrieval.models import CanonicalDocument
from src.store.models import DocumentRecord
from src.store.settings import StorePaths
from src.store.sqlite_store import SQLiteStore


class SQLiteDocumentRepository:
    def __init__(
        self,
        store: SQLiteStore | None = None,
        *,
        paths: StorePaths | None = None,
    ) -> None:
        resolved_paths = paths or StorePaths.from_env()
        self._store = store or SQLiteStore(resolved_paths)
        self._store.initialize()

    def iter_documents(
        self,
        *,
        notebook_id: str | None = None,
        document_kind: str | None = None,
    ) -> Iterator[CanonicalDocument]:
        for record in self._store.iter_documents(
            notebook_id=notebook_id,
            document_kind=document_kind,
        ):
            yield self._to_canonical_document(record)

    def get_document(self, document_id: str) -> CanonicalDocument | None:
        record = self._store.get_document(document_id)
        if record is None:
            return None
        return self._to_canonical_document(record)

    def _to_canonical_document(self, record: DocumentRecord) -> CanonicalDocument:
        return CanonicalDocument(
            id=record.id,
            notebook_id=record.notebook_id,
            origin_type=record.origin_type,
            origin_id=record.origin_id,
            document_kind=record.document_kind,
            title=record.title,
            text=record.text,
            url=record.url,
            content_sha256=record.content_sha256,
            metadata=dict(record.metadata),
        )
