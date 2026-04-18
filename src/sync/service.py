from __future__ import annotations

from uuid import uuid4

from src.store import SnapshotWriter, SQLiteStore, StorePaths
from src.store.models import NormalizedNotebookSnapshot, SyncFailure, SyncOutcome, SyncRunRecord, utc_now_iso
from src.sync.normalize import normalize_notebook_bundle
from src.sync.types import NotebookConnector


class NotebookSyncService:
    def __init__(
        self,
        store: SQLiteStore | None = None,
        snapshot_writer: SnapshotWriter | None = None,
        paths: StorePaths | None = None,
    ) -> None:
        resolved_paths = paths or StorePaths.from_env()
        self._store = store or SQLiteStore(resolved_paths)
        self._snapshot_writer = snapshot_writer or SnapshotWriter(resolved_paths)
        self._store.initialize()

    def sync_notebook(self, connector: NotebookConnector, notebook_id: str) -> SyncOutcome:
        started_at = utc_now_iso()
        run_id = f"sync:{uuid4()}"
        running = SyncRunRecord(
            id=run_id,
            notebook_id=notebook_id,
            started_at=started_at,
            status="running",
            summary="Notebook sync started",
        )
        self._store.record_sync_run_start(running)

        try:
            raw_bundle = connector.fetch_notebook(notebook_id)
            snapshot = normalize_notebook_bundle(raw_bundle, synced_at=started_at)
            self._store.replace_notebook_snapshot(snapshot)
            completed = self._finalize_run(snapshot, run_id, started_at)
            self._snapshot_writer.write_snapshot(snapshot, completed)
            self._store.finalize_sync_run(completed, snapshot.failures)
            return SyncOutcome(run=completed, snapshot=snapshot, failures=snapshot.failures)
        except Exception as exc:
            failed = SyncRunRecord(
                id=run_id,
                notebook_id=notebook_id,
                started_at=started_at,
                completed_at=utc_now_iso(),
                status="failed",
                error_count=1,
                summary=str(exc),
            )
            failure = SyncFailure(entity_type="sync_run", entity_id=notebook_id, message=str(exc))
            self._store.finalize_sync_run(failed, (failure,))
            return SyncOutcome(run=failed, failures=(failure,))

    def _finalize_run(
        self,
        snapshot: NormalizedNotebookSnapshot,
        run_id: str,
        started_at: str,
    ) -> SyncRunRecord:
        failure_count = len(snapshot.failures)
        status = "partial_success" if failure_count else "success"
        return SyncRunRecord(
            id=run_id,
            notebook_id=snapshot.notebook.id,
            started_at=started_at,
            completed_at=utc_now_iso(),
            status=status,
            source_count=len(snapshot.sources),
            artifact_count=len(snapshot.artifacts),
            document_count=len(snapshot.documents),
            chunk_count=len(snapshot.chunks),
            error_count=failure_count,
            summary=f"Synced {len(snapshot.sources)} sources, {len(snapshot.artifacts)} artifacts, {len(snapshot.documents)} documents",
        )
