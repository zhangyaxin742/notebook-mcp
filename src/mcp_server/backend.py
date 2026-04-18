from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable


JSONDict = dict[str, Any]

ALLOWED_DOCUMENT_KINDS = (
    "source_summary",
    "artifact_text",
    "note_text",
    "transcript_text",
    "table_text",
    "notebook_overview",
)


class BackendError(Exception):
    """Base error for MCP backend failures."""


class NotFoundError(BackendError):
    """Raised when a requested canonical entity does not exist."""


@runtime_checkable
class ResearchBackend(Protocol):
    def search(self, query: str) -> Sequence[Mapping[str, Any]]:
        ...

    def fetch(self, document_id: str) -> Mapping[str, Any]:
        ...

    def list_notebooks(self) -> Sequence[Mapping[str, Any]]:
        ...

    def get_notebook(self, notebook_id: str) -> Mapping[str, Any]:
        ...

    def list_notebook_documents(
        self, notebook_id: str, document_kind: str | None = None
    ) -> Sequence[Mapping[str, Any]]:
        ...

    def search_notebook(
        self,
        notebook_id: str,
        query: str,
        document_kind: str | None = None,
        limit: int = 10,
    ) -> Sequence[Mapping[str, Any]]:
        ...

    def get_sync_status(self, notebook_id: str | None = None) -> Mapping[str, Any]:
        ...


class NullResearchBackend:
    """Default backend until the sync/store/retrieval terminals land their services."""

    def search(self, query: str) -> Sequence[Mapping[str, Any]]:
        return []

    def fetch(self, document_id: str) -> Mapping[str, Any]:
        raise NotFoundError(f"Document not found: {document_id}")

    def list_notebooks(self) -> Sequence[Mapping[str, Any]]:
        return []

    def get_notebook(self, notebook_id: str) -> Mapping[str, Any]:
        raise NotFoundError(f"Notebook not found: {notebook_id}")

    def list_notebook_documents(
        self, notebook_id: str, document_kind: str | None = None
    ) -> Sequence[Mapping[str, Any]]:
        return []

    def search_notebook(
        self,
        notebook_id: str,
        query: str,
        document_kind: str | None = None,
        limit: int = 10,
    ) -> Sequence[Mapping[str, Any]]:
        return []

    def get_sync_status(self, notebook_id: str | None = None) -> Mapping[str, Any]:
        return {
            "status": "unconfigured",
            "notebook_id": notebook_id,
            "message": "No research backend is configured for the MCP server.",
        }


@dataclass(slots=True)
class InMemoryResearchBackend:
    """Reference backend for smoke tests and local manual validation."""

    notebooks: dict[str, JSONDict] = field(default_factory=dict)
    documents: dict[str, JSONDict] = field(default_factory=dict)
    sync_status: dict[str, JSONDict] = field(default_factory=dict)

    def search(self, query: str) -> Sequence[Mapping[str, Any]]:
        needle = query.casefold()
        results: list[JSONDict] = []
        for document in self.documents.values():
            if self._document_matches(document, needle):
                results.append(self._document_summary(document))
        return results

    def fetch(self, document_id: str) -> Mapping[str, Any]:
        document = self.documents.get(document_id)
        if document is None:
            raise NotFoundError(f"Document not found: {document_id}")
        return self._fetch_payload(document)

    def list_notebooks(self) -> Sequence[Mapping[str, Any]]:
        return [self._notebook_summary(notebook) for notebook in self.notebooks.values()]

    def get_notebook(self, notebook_id: str) -> Mapping[str, Any]:
        notebook = self.notebooks.get(notebook_id)
        if notebook is None:
            raise NotFoundError(f"Notebook not found: {notebook_id}")
        return dict(notebook)

    def list_notebook_documents(
        self, notebook_id: str, document_kind: str | None = None
    ) -> Sequence[Mapping[str, Any]]:
        return [
            self._document_listing(document)
            for document in self.documents.values()
            if document["notebook_id"] == notebook_id
            and (document_kind is None or document["document_kind"] == document_kind)
        ]

    def search_notebook(
        self,
        notebook_id: str,
        query: str,
        document_kind: str | None = None,
        limit: int = 10,
    ) -> Sequence[Mapping[str, Any]]:
        needle = query.casefold()
        results: list[JSONDict] = []
        for document in self.documents.values():
            if document["notebook_id"] != notebook_id:
                continue
            if document_kind is not None and document["document_kind"] != document_kind:
                continue
            if self._document_matches(document, needle):
                results.append(self._document_listing(document))
            if len(results) >= limit:
                break
        return results

    def get_sync_status(self, notebook_id: str | None = None) -> Mapping[str, Any]:
        if notebook_id is not None:
            status = self.sync_status.get(notebook_id)
            if status is None:
                raise NotFoundError(f"Notebook not found: {notebook_id}")
            return dict(status)

        return {
            "status": "ready",
            "notebook_count": len(self.notebooks),
            "document_count": len(self.documents),
        }

    def _document_matches(self, document: Mapping[str, Any], needle: str) -> bool:
        haystacks = (
            str(document.get("title", "")),
            str(document.get("text", "")),
            str(document.get("url", "")),
        )
        return any(needle in value.casefold() for value in haystacks)

    def _document_summary(self, document: Mapping[str, Any]) -> JSONDict:
        return {
            "id": document["id"],
            "title": document["title"],
            "url": document["url"],
        }

    def _document_listing(self, document: Mapping[str, Any]) -> JSONDict:
        return {
            "id": document["id"],
            "title": document["title"],
            "url": document["url"],
            "document_kind": document["document_kind"],
        }

    def _fetch_payload(self, document: Mapping[str, Any]) -> JSONDict:
        metadata = dict(document.get("metadata", {}))
        metadata.setdefault("origin_type", document["origin_type"])
        metadata.setdefault("origin_id", document["origin_id"])
        metadata.setdefault("document_kind", document["document_kind"])
        metadata.setdefault("notebook_id", document["notebook_id"])

        return {
            "id": document["id"],
            "title": document["title"],
            "text": document["text"],
            "url": document["url"],
            "metadata": metadata,
        }

    def _notebook_summary(self, notebook: Mapping[str, Any]) -> JSONDict:
        return {
            "id": notebook["id"],
            "title": notebook["title"],
            "url": notebook["url"],
            "source_count": notebook.get("source_count"),
            "artifact_count": notebook.get("artifact_count"),
        }


def build_demo_backend() -> InMemoryResearchBackend:
    notebook_id = "nlm:notebook:abc123"
    document_id = "nlm:document:abc123:source_summary:src789"

    notebooks = {
        notebook_id: {
            "id": notebook_id,
            "origin": "notebooklm",
            "raw_id": "abc123",
            "title": "AI Safety Research",
            "url": "https://notebooklm.google.com/notebook/abc123",
            "source_count": 143,
            "artifact_count": 8,
            "last_synced_at": "2026-04-18T20:00:00Z",
            "metadata": {"share_mode": "private"},
        }
    }
    documents = {
        document_id: {
            "id": document_id,
            "notebook_id": notebook_id,
            "origin_type": "source",
            "origin_id": "nlm:source:abc123:src789",
            "document_kind": "source_summary",
            "title": "Example paper",
            "text": "NotebookLM-generated source summary.",
            "url": "https://example.com/paper",
            "content_sha256": (
                "5f8e8d3f5c6a0b7d62c55883f0b56df2e15d8978cfe2a6b9cb9f4ed4cf9d3e3b"
            ),
            "metadata": {"source_type": "web"},
        }
    }
    sync_status = {
        notebook_id: {
            "status": "ready",
            "notebook_id": notebook_id,
            "last_synced_at": "2026-04-18T20:00:00Z",
            "document_count": 1,
        }
    }

    return InMemoryResearchBackend(
        notebooks=notebooks,
        documents=documents,
        sync_status=sync_status,
    )
