from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3

from src.store.models import (
    ArtifactRecord,
    ChunkRecord,
    DocumentRecord,
    NormalizedNotebookSnapshot,
    NotebookRecord,
    SourceRecord,
    SyncFailure,
    SyncRunRecord,
    canonical_json_compact,
)
from src.store.settings import StorePaths


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS notebooks (
        id TEXT PRIMARY KEY,
        origin TEXT NOT NULL,
        raw_id TEXT,
        derived_key TEXT,
        title TEXT NOT NULL,
        url TEXT NOT NULL,
        source_count INTEGER,
        artifact_count INTEGER,
        last_synced_at TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sources (
        id TEXT PRIMARY KEY,
        notebook_id TEXT NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
        origin TEXT NOT NULL,
        raw_id TEXT,
        derived_key TEXT,
        title TEXT NOT NULL,
        url TEXT NOT NULL,
        source_type TEXT NOT NULL,
        summary_text TEXT,
        created_at TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS artifacts (
        id TEXT PRIMARY KEY,
        notebook_id TEXT NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
        origin TEXT NOT NULL,
        artifact_kind TEXT NOT NULL,
        raw_id TEXT,
        derived_key TEXT,
        title TEXT NOT NULL,
        url TEXT NOT NULL,
        text TEXT,
        mime_type TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        notebook_id TEXT NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
        origin_type TEXT NOT NULL,
        origin_id TEXT NOT NULL,
        document_kind TEXT NOT NULL,
        title TEXT NOT NULL,
        text TEXT NOT NULL,
        url TEXT NOT NULL,
        content_sha256 TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chunks (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        notebook_id TEXT NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
        chunk_index INTEGER NOT NULL,
        text TEXT NOT NULL,
        char_start INTEGER,
        char_end INTEGER,
        token_count_estimate INTEGER,
        content_sha256 TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sync_runs (
        id TEXT PRIMARY KEY,
        notebook_id TEXT,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        status TEXT NOT NULL,
        source_count INTEGER NOT NULL DEFAULT 0,
        artifact_count INTEGER NOT NULL DEFAULT 0,
        document_count INTEGER NOT NULL DEFAULT 0,
        chunk_count INTEGER NOT NULL DEFAULT 0,
        error_count INTEGER NOT NULL DEFAULT 0,
        summary TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sync_run_failures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sync_run_id TEXT NOT NULL REFERENCES sync_runs(id) ON DELETE CASCADE,
        entity_type TEXT NOT NULL,
        entity_id TEXT,
        message TEXT NOT NULL,
        details_json TEXT NOT NULL DEFAULT '{}'
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_sources_notebook_id ON sources(notebook_id)",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_notebook_id ON artifacts(notebook_id)",
    "CREATE INDEX IF NOT EXISTS idx_documents_notebook_id ON documents(notebook_id)",
    "CREATE INDEX IF NOT EXISTS idx_documents_origin_id ON documents(origin_id)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id)",
    "CREATE INDEX IF NOT EXISTS idx_sync_runs_notebook_id ON sync_runs(notebook_id)",
)


class SQLiteStore:
    def __init__(self, paths: StorePaths) -> None:
        self._paths = paths
        self._paths.ensure_directories()

    @property
    def db_path(self) -> Path:
        return self._paths.db_path

    def initialize(self) -> None:
        connection = self._connect()
        try:
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)
            connection.commit()
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> sqlite3.Connection:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def record_sync_run_start(self, run: SyncRunRecord) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO sync_runs (
                    id, notebook_id, started_at, completed_at, status,
                    source_count, artifact_count, document_count, chunk_count, error_count, summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.notebook_id,
                    run.started_at,
                    run.completed_at,
                    run.status,
                    run.source_count,
                    run.artifact_count,
                    run.document_count,
                    run.chunk_count,
                    run.error_count,
                    run.summary,
                ),
            )

    def finalize_sync_run(self, run: SyncRunRecord, failures: tuple[SyncFailure, ...]) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE sync_runs
                SET notebook_id = ?, completed_at = ?, status = ?,
                    source_count = ?, artifact_count = ?, document_count = ?,
                    chunk_count = ?, error_count = ?, summary = ?
                WHERE id = ?
                """,
                (
                    run.notebook_id,
                    run.completed_at,
                    run.status,
                    run.source_count,
                    run.artifact_count,
                    run.document_count,
                    run.chunk_count,
                    run.error_count,
                    run.summary,
                    run.id,
                ),
            )
            connection.execute("DELETE FROM sync_run_failures WHERE sync_run_id = ?", (run.id,))
            connection.executemany(
                """
                INSERT INTO sync_run_failures (sync_run_id, entity_type, entity_id, message, details_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        run.id,
                        failure.entity_type,
                        failure.entity_id,
                        failure.message,
                        canonical_json_compact(failure.details),
                    )
                    for failure in failures
                ],
            )

    def replace_notebook_snapshot(self, snapshot: NormalizedNotebookSnapshot) -> None:
        with self.transaction() as connection:
            self._upsert_notebook(connection, snapshot.notebook)
            self._replace_sources(connection, snapshot.notebook.id, snapshot.sources)
            self._replace_artifacts(connection, snapshot.notebook.id, snapshot.artifacts)
            self._replace_documents(connection, snapshot.notebook.id, snapshot.documents)

    def replace_document_chunks(self, document_id: str, notebook_id: str, chunks: tuple[ChunkRecord, ...]) -> None:
        with self.transaction() as connection:
            connection.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            connection.executemany(
                """
                INSERT INTO chunks (
                    id, document_id, notebook_id, chunk_index, text,
                    char_start, char_end, token_count_estimate, content_sha256, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    document_id = excluded.document_id,
                    notebook_id = excluded.notebook_id,
                    chunk_index = excluded.chunk_index,
                    text = excluded.text,
                    char_start = excluded.char_start,
                    char_end = excluded.char_end,
                    token_count_estimate = excluded.token_count_estimate,
                    content_sha256 = excluded.content_sha256,
                    metadata_json = excluded.metadata_json
                """,
                [
                    (
                        chunk.id,
                        document_id,
                        notebook_id,
                        chunk.chunk_index,
                        chunk.text,
                        chunk.char_start,
                        chunk.char_end,
                        chunk.token_count_estimate,
                        chunk.content_sha256,
                        canonical_json_compact(chunk.metadata),
                    )
                    for chunk in chunks
                ],
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._paths.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _upsert_notebook(self, connection: sqlite3.Connection, notebook: NotebookRecord) -> None:
        connection.execute(
            """
            INSERT INTO notebooks (
                id, origin, raw_id, derived_key, title, url,
                source_count, artifact_count, last_synced_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                origin = excluded.origin,
                raw_id = excluded.raw_id,
                derived_key = excluded.derived_key,
                title = excluded.title,
                url = excluded.url,
                source_count = excluded.source_count,
                artifact_count = excluded.artifact_count,
                last_synced_at = excluded.last_synced_at,
                metadata_json = excluded.metadata_json
            """,
            (
                notebook.id,
                notebook.origin,
                notebook.raw_id,
                notebook.derived_key,
                notebook.title,
                notebook.url,
                notebook.source_count,
                notebook.artifact_count,
                notebook.last_synced_at,
                canonical_json_compact(notebook.metadata),
            ),
        )

    def _replace_sources(
        self,
        connection: sqlite3.Connection,
        notebook_id: str,
        sources: tuple[SourceRecord, ...],
    ) -> None:
        connection.executemany(
            """
            INSERT INTO sources (
                id, notebook_id, origin, raw_id, derived_key,
                title, url, source_type, summary_text, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                notebook_id = excluded.notebook_id,
                origin = excluded.origin,
                raw_id = excluded.raw_id,
                derived_key = excluded.derived_key,
                title = excluded.title,
                url = excluded.url,
                source_type = excluded.source_type,
                summary_text = excluded.summary_text,
                created_at = excluded.created_at,
                metadata_json = excluded.metadata_json
            """,
            [
                (
                    source.id,
                    source.notebook_id,
                    source.origin,
                    source.raw_id,
                    source.derived_key,
                    source.title,
                    source.url,
                    source.source_type,
                    source.summary_text,
                    source.created_at,
                    canonical_json_compact(source.metadata),
                )
                for source in sources
            ],
        )
        self._delete_missing_ids(connection, "sources", notebook_id, [source.id for source in sources])

    def _replace_artifacts(
        self,
        connection: sqlite3.Connection,
        notebook_id: str,
        artifacts: tuple[ArtifactRecord, ...],
    ) -> None:
        connection.executemany(
            """
            INSERT INTO artifacts (
                id, notebook_id, origin, artifact_kind, raw_id, derived_key,
                title, url, text, mime_type, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                notebook_id = excluded.notebook_id,
                origin = excluded.origin,
                artifact_kind = excluded.artifact_kind,
                raw_id = excluded.raw_id,
                derived_key = excluded.derived_key,
                title = excluded.title,
                url = excluded.url,
                text = excluded.text,
                mime_type = excluded.mime_type,
                metadata_json = excluded.metadata_json
            """,
            [
                (
                    artifact.id,
                    artifact.notebook_id,
                    artifact.origin,
                    artifact.artifact_kind,
                    artifact.raw_id,
                    artifact.derived_key,
                    artifact.title,
                    artifact.url,
                    artifact.text,
                    artifact.mime_type,
                    canonical_json_compact(artifact.metadata),
                )
                for artifact in artifacts
            ],
        )
        self._delete_missing_ids(connection, "artifacts", notebook_id, [artifact.id for artifact in artifacts])

    def _replace_documents(
        self,
        connection: sqlite3.Connection,
        notebook_id: str,
        documents: tuple[DocumentRecord, ...],
    ) -> None:
        connection.executemany(
            """
            INSERT INTO documents (
                id, notebook_id, origin_type, origin_id, document_kind,
                title, text, url, content_sha256, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                notebook_id = excluded.notebook_id,
                origin_type = excluded.origin_type,
                origin_id = excluded.origin_id,
                document_kind = excluded.document_kind,
                title = excluded.title,
                text = excluded.text,
                url = excluded.url,
                content_sha256 = excluded.content_sha256,
                metadata_json = excluded.metadata_json
            """,
            [
                (
                    document.id,
                    document.notebook_id,
                    document.origin_type,
                    document.origin_id,
                    document.document_kind,
                    document.title,
                    document.text,
                    document.url,
                    document.content_sha256,
                    canonical_json_compact(document.metadata),
                )
                for document in documents
            ],
        )
        self._delete_missing_ids(connection, "documents", notebook_id, [document.id for document in documents])

    def _delete_missing_ids(
        self,
        connection: sqlite3.Connection,
        table_name: str,
        notebook_id: str,
        keep_ids: list[str],
    ) -> None:
        if keep_ids:
            placeholders = ", ".join("?" for _ in keep_ids)
            connection.execute(
                f"DELETE FROM {table_name} WHERE notebook_id = ? AND id NOT IN ({placeholders})",
                (notebook_id, *keep_ids),
            )
            return
        connection.execute(f"DELETE FROM {table_name} WHERE notebook_id = ?", (notebook_id,))
