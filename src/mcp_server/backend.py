from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from src.retrieval.models import CanonicalDocument, SearchResult
from src.retrieval.service import RetrievalService
from src.store.document_repository import SQLiteDocumentRepository
from src.store.settings import StorePaths
from src.store.sqlite_store import SQLiteStore


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


class SQLiteResearchBackend:
    """Research backend backed by the canonical SQLite store and retrieval service."""

    def __init__(self, *, paths: StorePaths | None = None) -> None:
        self._paths = paths or StorePaths.from_env()
        self._store = SQLiteStore(self._paths)
        self._store.initialize()
        self._repository = SQLiteDocumentRepository(store=self._store)

    def search(self, query: str) -> Sequence[Mapping[str, Any]]:
        retrieval = self._new_retrieval_service()
        try:
            retrieval.refresh()
            return [self._search_result_payload(result) for result in retrieval.search(query)]
        finally:
            retrieval.close()

    def fetch(self, document_id: str) -> Mapping[str, Any]:
        document = self._repository.get_document(document_id)
        if document is None:
            raise NotFoundError(f"Document not found: {document_id}")
        return self._document_payload(document)

    def list_notebooks(self) -> Sequence[Mapping[str, Any]]:
        rows = self._fetchall(
            """
            SELECT
                id,
                origin,
                raw_id,
                derived_key,
                title,
                url,
                source_count,
                artifact_count,
                last_synced_at,
                metadata_json
            FROM notebooks
            ORDER BY lower(title) ASC, id ASC
            """
        )
        return [self._notebook_payload(row) for row in rows]

    def get_notebook(self, notebook_id: str) -> Mapping[str, Any]:
        row = self._fetchone(
            """
            SELECT
                id,
                origin,
                raw_id,
                derived_key,
                title,
                url,
                source_count,
                artifact_count,
                last_synced_at,
                metadata_json
            FROM notebooks
            WHERE id = ?
            """,
            (notebook_id,),
        )
        if row is None:
            raise NotFoundError(f"Notebook not found: {notebook_id}")
        return self._notebook_payload(row)

    def list_notebook_documents(
        self, notebook_id: str, document_kind: str | None = None
    ) -> Sequence[Mapping[str, Any]]:
        self._require_notebook(notebook_id)
        return [
            self._document_listing_payload(document)
            for document in self._repository.iter_documents(
                notebook_id=notebook_id,
                document_kind=document_kind,
            )
        ]

    def search_notebook(
        self,
        notebook_id: str,
        query: str,
        document_kind: str | None = None,
        limit: int = 10,
    ) -> Sequence[Mapping[str, Any]]:
        self._require_notebook(notebook_id)
        retrieval = self._new_retrieval_service()
        try:
            retrieval.refresh()
            return [
                self._document_listing_payload_from_result(result)
                for result in retrieval.search_notebook(
                    notebook_id,
                    query,
                    document_kind=document_kind,
                    limit=limit,
                )
            ]
        finally:
            retrieval.close()

    def get_sync_status(self, notebook_id: str | None = None) -> Mapping[str, Any]:
        if notebook_id is None:
            latest_run = self._fetchone(
                """
                SELECT
                    id,
                    notebook_id,
                    started_at,
                    completed_at,
                    status,
                    source_count,
                    artifact_count,
                    document_count,
                    chunk_count,
                    error_count,
                    summary
                FROM sync_runs
                ORDER BY COALESCE(completed_at, started_at) DESC, started_at DESC, id DESC
                LIMIT 1
                """
            )
            notebook_count = self._count("SELECT COUNT(*) FROM notebooks")
            document_count = self._count("SELECT COUNT(*) FROM documents")
            status = "ready" if notebook_count else "empty"
            payload: JSONDict = {
                "status": status,
                "notebook_count": notebook_count,
                "document_count": document_count,
            }
            if latest_run is not None:
                payload["latest_run"] = self._sync_run_payload(latest_run)
            return payload

        notebook = self.get_notebook(notebook_id)
        latest_run = self._fetchone(
            """
            SELECT
                id,
                notebook_id,
                started_at,
                completed_at,
                status,
                source_count,
                artifact_count,
                document_count,
                chunk_count,
                error_count,
                summary
            FROM sync_runs
            WHERE notebook_id = ?
            ORDER BY COALESCE(completed_at, started_at) DESC, started_at DESC, id DESC
            LIMIT 1
            """,
            (notebook_id,),
        )
        payload = {
            "status": "never_synced" if latest_run is None else latest_run["status"],
            "notebook_id": notebook_id,
            "title": notebook["title"],
            "last_synced_at": notebook.get("last_synced_at"),
            "document_count": self._count(
                "SELECT COUNT(*) FROM documents WHERE notebook_id = ?",
                (notebook_id,),
            ),
        }
        if latest_run is not None:
            payload["latest_run"] = self._sync_run_payload(latest_run)
        return payload

    def close(self) -> None:
        return

    def _new_retrieval_service(self) -> RetrievalService:
        return RetrievalService(self._repository)

    def _require_notebook(self, notebook_id: str) -> None:
        self.get_notebook(notebook_id)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._store.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _fetchall(
        self, query: str, parameters: tuple[Any, ...] = ()
    ) -> list[sqlite3.Row]:
        connection = self._connect()
        try:
            rows = connection.execute(query, parameters).fetchall()
        finally:
            connection.close()
        return list(rows)

    def _fetchone(
        self, query: str, parameters: tuple[Any, ...] = ()
    ) -> sqlite3.Row | None:
        connection = self._connect()
        try:
            row = connection.execute(query, parameters).fetchone()
        finally:
            connection.close()
        return row

    def _count(self, query: str, parameters: tuple[Any, ...] = ()) -> int:
        row = self._fetchone(query, parameters)
        if row is None:
            return 0
        return int(row[0])

    def _notebook_payload(self, row: sqlite3.Row) -> JSONDict:
        return {
            "id": row["id"],
            "origin": row["origin"],
            "raw_id": row["raw_id"],
            "derived_key": row["derived_key"],
            "title": row["title"],
            "url": row["url"],
            "source_count": row["source_count"],
            "artifact_count": row["artifact_count"],
            "last_synced_at": row["last_synced_at"],
            "metadata": json.loads(row["metadata_json"]),
        }

    def _document_payload(self, document: CanonicalDocument) -> JSONDict:
        metadata = dict(document.metadata)
        metadata.setdefault("origin_type", document.origin_type)
        metadata.setdefault("origin_id", document.origin_id)
        metadata.setdefault("document_kind", document.document_kind)
        metadata.setdefault("notebook_id", document.notebook_id)
        return {
            "id": document.id,
            "title": document.title,
            "text": document.text,
            "url": document.url,
            "metadata": metadata,
        }

    def _document_listing_payload(self, document: CanonicalDocument) -> JSONDict:
        return {
            "id": document.id,
            "title": document.title,
            "url": document.url,
            "document_kind": document.document_kind,
        }

    def _document_listing_payload_from_result(self, result: SearchResult) -> JSONDict:
        return {
            "id": result.id,
            "title": result.title,
            "url": result.url,
            "document_kind": result.document_kind,
        }

    def _search_result_payload(self, result: SearchResult) -> JSONDict:
        return {
            "id": result.id,
            "title": result.title,
            "url": result.url,
            "document_kind": result.document_kind,
            "origin_type": result.origin_type,
            "origin_id": result.origin_id,
            "notebook_id": result.notebook_id,
        }

    def _sync_run_payload(self, row: sqlite3.Row) -> JSONDict:
        return {
            "id": row["id"],
            "notebook_id": row["notebook_id"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "status": row["status"],
            "source_count": row["source_count"],
            "artifact_count": row["artifact_count"],
            "document_count": row["document_count"],
            "chunk_count": row["chunk_count"],
            "error_count": row["error_count"],
            "summary": row["summary"],
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
