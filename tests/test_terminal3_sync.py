from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.index import ChunkingPolicy
from src.store import SnapshotWriter, SQLiteChunkRepository, SQLiteStore, StorePaths, SyncRunRecord
from src.sync import NotebookSyncService, PersistedChunkReindexer, normalize_notebook_bundle


class StubConnector:
    def __init__(self, bundle: dict) -> None:
        self._bundle = bundle

    def fetch_notebook(self, notebook_id: str) -> dict:
        return self._bundle


class FailingConnector:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def fetch_notebook(self, notebook_id: str) -> dict:
        raise self._error


def make_paths(base_dir: str) -> StorePaths:
    root = Path(base_dir) / "data"
    return StorePaths(
        data_dir=root,
        db_path=root / "db" / "notebook_mcp.sqlite3",
        snapshots_dir=root / "snapshots",
    )


def read_table_count(db_path: Path, table_name: str) -> int:
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
    finally:
        connection.close()
    return int(row[0])


def read_count_and_distinct(db_path: Path, table_name: str) -> tuple[int, int]:
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(f"SELECT COUNT(*), COUNT(DISTINCT id) FROM {table_name}").fetchone()
    finally:
        connection.close()
    return int(row[0]), int(row[1])


def read_sync_failures(db_path: Path, sync_run_id: str) -> list[tuple[str, str, str | None, dict]]:
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT entity_type, message, entity_id, details_json
            FROM sync_run_failures
            WHERE sync_run_id = ?
            ORDER BY id ASC
            """,
            (sync_run_id,),
        ).fetchall()
    finally:
        connection.close()

    return [
        (
            str(entity_type),
            str(message),
            str(entity_id) if entity_id is not None else None,
            json.loads(details_json),
        )
        for entity_type, message, entity_id, details_json in rows
    ]


def collect_snapshot_files(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*.json"))
    }


def make_valid_bundle(
    *,
    summary_text: str | None = None,
    artifact_text: str | None = None,
) -> dict:
    return {
        "id": "notebook-a",
        "title": "Research Notebook",
        "url": "https://notebooklm.google.com/notebook/notebook-a",
        "share_mode": "private",
        "auth_cookie": "should-not-survive",
        "sources": [
            {
                "id": "source-1",
                "title": "Example Paper",
                "url": "https://example.com/paper",
                "source_type": "web",
                "summary_text": summary_text
                or "This summary preserves provenance and retrieval-ready text for the paper.",
                "author": "Researcher",
                "csrf_token": "drop-me",
            }
        ],
        "artifacts": [
            {
                "id": "artifact-1",
                "artifact_kind": "briefing_doc",
                "title": "Briefing document",
                "url": "https://notebooklm.google.com/notebook/notebook-a/artifact/briefing_doc/artifact-1",
                "text": artifact_text
                or "This artifact text supports persisted sync testing and indexing validation.",
                "mime_type": "text/markdown",
                "token_value": "drop-me-too",
            }
        ],
    }


class Terminal3SyncTests(unittest.TestCase):
    def test_normalization_preserves_provenance_and_canonical_urls(self) -> None:
        snapshot = normalize_notebook_bundle(make_valid_bundle(), synced_at="2026-04-18T00:00:00Z")

        self.assertEqual(snapshot.notebook.metadata, {"share_mode": "private"})
        self.assertEqual(len(snapshot.sources), 1)
        self.assertEqual(len(snapshot.artifacts), 1)
        self.assertEqual(len(snapshot.documents), 2)

        source = snapshot.sources[0]
        source_document = next(document for document in snapshot.documents if document.origin_type == "source")
        self.assertEqual(source.url, "https://example.com/paper")
        self.assertEqual(source_document.origin_id, source.id)
        self.assertEqual(source_document.url, source.url)
        self.assertEqual(source_document.metadata, {"source_type": "web"})

        artifact = snapshot.artifacts[0]
        artifact_document = next(document for document in snapshot.documents if document.origin_type == "artifact")
        self.assertEqual(artifact_document.origin_id, artifact.id)
        self.assertEqual(artifact_document.url, artifact.url)
        self.assertEqual(
            artifact_document.metadata,
            {"artifact_kind": "briefing_doc", "mime_type": "text/markdown"},
        )

    def test_sync_is_idempotent_and_does_not_duplicate_logical_records(self) -> None:
        with tempfile.TemporaryDirectory(dir=".") as temp_dir:
            paths = make_paths(temp_dir)
            service = NotebookSyncService(
                paths=paths,
                chunking_policy=ChunkingPolicy(max_chars=120, overlap_chars=20, min_chunk_chars=40),
            )
            connector = StubConnector(
                make_valid_bundle(
                    summary_text=" ".join(["repeatable-summary"] * 80),
                    artifact_text=" ".join(["repeatable-artifact"] * 80),
                )
            )

            first = service.sync_notebook(connector, "notebook-a")
            second = service.sync_notebook(connector, "notebook-a")

            self.assertEqual(first.run.status, "success")
            self.assertEqual(second.run.status, "success")

            self.assertEqual(read_table_count(paths.db_path, "notebooks"), 1)
            self.assertEqual(read_table_count(paths.db_path, "sources"), 1)
            self.assertEqual(read_table_count(paths.db_path, "artifacts"), 1)
            self.assertEqual(read_table_count(paths.db_path, "documents"), 2)
            self.assertGreater(read_table_count(paths.db_path, "chunks"), 2)
            self.assertEqual(read_table_count(paths.db_path, "sync_runs"), 2)

            for table_name in ("notebooks", "sources", "artifacts", "documents", "chunks"):
                with self.subTest(table=table_name):
                    count, distinct_count = read_count_and_distinct(paths.db_path, table_name)
                    self.assertEqual(count, distinct_count)

    def test_partial_failures_are_recorded_predictably(self) -> None:
        with tempfile.TemporaryDirectory(dir=".") as temp_dir:
            paths = make_paths(temp_dir)
            service = NotebookSyncService(paths=paths)
            connector = StubConnector(
                {
                    "id": "notebook-a",
                    "title": "Research Notebook",
                    "sources": [
                        {"id": "source-1", "title": "Good Source", "summary_text": "usable summary"},
                        "not-a-mapping",
                    ],
                    "artifacts": [
                        {
                            "id": "artifact-bad",
                            "artifact_kind": "diagram",
                            "title": "Unsupported Artifact",
                            "text": "ignored",
                            "session_token": "must-not-leak",
                        }
                    ],
                }
            )

            outcome = service.sync_notebook(connector, "notebook-a")

            self.assertEqual(outcome.run.status, "partial_success")
            self.assertEqual(outcome.run.error_count, 2)
            self.assertEqual(len(outcome.failures), 2)

            failures = read_sync_failures(paths.db_path, outcome.run.id)
            self.assertEqual(
                failures,
                [
                    ("source", "Entity payload must be a mapping", None, {"value_repr": "'not-a-mapping'"}),
                    ("artifact", "Unsupported artifact kind: diagram", None, {"artifact_kind": "diagram", "id": "artifact-bad", "text": "ignored", "title": "Unsupported Artifact"}),
                ],
            )

    def test_snapshot_writer_is_deterministic_for_same_snapshot_and_run(self) -> None:
        with tempfile.TemporaryDirectory(dir=".") as temp_dir:
            paths = make_paths(temp_dir)
            writer = SnapshotWriter(paths)
            snapshot = normalize_notebook_bundle(make_valid_bundle(), synced_at="2026-04-18T00:00:00Z")
            run = SyncRunRecord(
                id="sync:fixed",
                notebook_id=snapshot.notebook.id,
                started_at="2026-04-18T00:00:00Z",
                completed_at="2026-04-18T00:01:00Z",
                status="success",
                source_count=len(snapshot.sources),
                artifact_count=len(snapshot.artifacts),
                document_count=len(snapshot.documents),
                chunk_count=0,
                error_count=0,
                summary="Deterministic snapshot test",
            )

            notebook_dir = writer.write_snapshot(snapshot, run)
            before = collect_snapshot_files(notebook_dir)
            writer.write_snapshot(snapshot, run)
            after = collect_snapshot_files(notebook_dir)

            self.assertEqual(before, after)

    def test_sync_persists_chunks_and_reindex_flow_reads_them_from_sqlite(self) -> None:
        with tempfile.TemporaryDirectory(dir=".") as temp_dir:
            paths = make_paths(temp_dir)
            store = SQLiteStore(paths)
            service = NotebookSyncService(
                store=store,
                paths=paths,
                chunking_policy=ChunkingPolicy(max_chars=150, overlap_chars=25, min_chunk_chars=50),
            )
            connector = StubConnector(
                make_valid_bundle(
                    summary_text=(
                        ("Persisted chunk indexing validates lexical search against synced data. " * 12)
                        + "\n\n"
                        + ("Chunk persistence should survive reindex flows cleanly. " * 10)
                    ),
                    artifact_text="Artifact companion text for chunk persistence coverage.",
                )
            )

            outcome = service.sync_notebook(connector, "notebook-a")

            self.assertEqual(outcome.run.status, "success")
            self.assertGreater(outcome.run.chunk_count, 1)

            chunk_repository = SQLiteChunkRepository(store=store)
            reindexer = PersistedChunkReindexer(chunk_repository)
            try:
                chunks = reindexer.refresh(notebook_id="nlm:notebook:notebook-a")
                self.assertEqual(len(chunks), read_table_count(paths.db_path, "chunks"))

                hits = reindexer.lexical_index.search(
                    "chunk persistence",
                    notebook_id="nlm:notebook:notebook-a",
                    limit=5,
                )
                self.assertTrue(hits)
                self.assertIn(hits[0].chunk_id, {chunk.id for chunk in chunks})
            finally:
                reindexer.close()

    def test_sync_records_failed_run_when_connector_raises(self) -> None:
        with tempfile.TemporaryDirectory(dir=".") as temp_dir:
            paths = make_paths(temp_dir)
            service = NotebookSyncService(paths=paths)

            outcome = service.sync_notebook(
                FailingConnector(RuntimeError("connector unavailable")),
                "notebook-a",
            )

            self.assertEqual(outcome.run.status, "failed")
            self.assertEqual(outcome.run.error_count, 1)
            self.assertEqual(outcome.failures[0].entity_type, "sync_run")
            self.assertEqual(outcome.failures[0].entity_id, "notebook-a")
            self.assertEqual(read_table_count(paths.db_path, "sync_runs"), 1)

            failures = read_sync_failures(paths.db_path, outcome.run.id)
            self.assertEqual(
                failures,
                [("sync_run", "connector unavailable", "notebook-a", {})],
            )


if __name__ == "__main__":
    unittest.main()
