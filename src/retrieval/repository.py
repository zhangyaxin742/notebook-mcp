from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from typing import Protocol

from .models import CanonicalDocument


class CanonicalDocumentRepository(Protocol):
    def iter_documents(
        self,
        *,
        notebook_id: str | None = None,
        document_kind: str | None = None,
    ) -> Iterable[CanonicalDocument]:
        ...

    def get_document(self, document_id: str) -> CanonicalDocument | None:
        ...


class InMemoryDocumentRepository:
    def __init__(self, documents: Sequence[CanonicalDocument]) -> None:
        ordered = sorted(
            documents,
            key=lambda document: (
                document.notebook_id,
                document.document_kind,
                document.title.lower(),
                document.id,
            ),
        )
        self._documents = tuple(ordered)
        self._documents_by_id = {document.id: document for document in ordered}

    def iter_documents(
        self,
        *,
        notebook_id: str | None = None,
        document_kind: str | None = None,
    ) -> Iterator[CanonicalDocument]:
        for document in self._documents:
            if notebook_id is not None and document.notebook_id != notebook_id:
                continue
            if document_kind is not None and document.document_kind != document_kind:
                continue
            yield document

    def get_document(self, document_id: str) -> CanonicalDocument | None:
        return self._documents_by_id.get(document_id)

