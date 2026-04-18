from __future__ import annotations

from pathlib import Path
from typing import Iterable

from src.store.ids import entity_key, notebook_key, safe_document_filename
from src.store.models import (
    ArtifactRecord,
    NormalizedNotebookSnapshot,
    SyncRunRecord,
    canonical_json,
)
from src.store.settings import StorePaths


class SnapshotWriter:
    def __init__(self, paths: StorePaths) -> None:
        self._paths = paths

    def write_snapshot(self, snapshot: NormalizedNotebookSnapshot, run: SyncRunRecord) -> Path:
        self._paths.ensure_directories()
        notebook_part = notebook_key(snapshot.notebook.raw_id, snapshot.notebook.derived_key)
        notebook_dir = self._paths.snapshots_dir / "notebooks" / notebook_part
        sources_dir = notebook_dir / "sources"
        artifacts_dir = notebook_dir / "artifacts"
        documents_dir = notebook_dir / "documents"

        sources_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        documents_dir.mkdir(parents=True, exist_ok=True)

        expected_source_files: set[Path] = set()
        for source in snapshot.sources:
            source_part = entity_key(source.raw_id, source.derived_key)
            target = sources_dir / f"{source_part}.json"
            target.write_text(canonical_json(source.to_dict()), encoding="utf-8")
            expected_source_files.add(target)

        expected_artifact_files: set[Path] = set()
        for artifact in snapshot.artifacts:
            artifact_part = entity_key(artifact.raw_id, artifact.derived_key)
            artifact_dir = artifacts_dir / artifact.artifact_kind
            artifact_dir.mkdir(parents=True, exist_ok=True)
            target = artifact_dir / f"{artifact_part}.json"
            target.write_text(canonical_json(artifact.to_dict()), encoding="utf-8")
            expected_artifact_files.add(target)

        expected_document_files: set[Path] = set()
        for document in snapshot.documents:
            target = documents_dir / safe_document_filename(document.id)
            target.write_text(canonical_json(document.to_dict()), encoding="utf-8")
            expected_document_files.add(target)

        self._prune_json_files(sources_dir, expected_source_files)
        self._prune_json_files(documents_dir, expected_document_files)
        self._prune_artifact_dirs(artifacts_dir, snapshot.artifacts, expected_artifact_files)

        manifest = {
            "artifacts": [artifact.id for artifact in snapshot.artifacts],
            "documents": [document.id for document in snapshot.documents],
            "failures": [failure.to_dict() for failure in snapshot.failures],
            "notebook": snapshot.notebook.to_dict(),
            "sources": [source.id for source in snapshot.sources],
            "sync_run": run.to_dict(),
        }
        (notebook_dir / "manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
        return notebook_dir

    def _prune_json_files(self, directory: Path, expected_files: set[Path]) -> None:
        for candidate in directory.glob("*.json"):
            if candidate not in expected_files and candidate.name != "manifest.json":
                candidate.unlink()

    def _prune_artifact_dirs(
        self,
        artifacts_dir: Path,
        artifacts: Iterable[ArtifactRecord],
        expected_files: set[Path],
    ) -> None:
        expected_kinds = {artifact.artifact_kind for artifact in artifacts}
        for kind_dir in artifacts_dir.iterdir():
            if not kind_dir.is_dir():
                continue
            if kind_dir.name not in expected_kinds:
                for candidate in kind_dir.glob("*.json"):
                    candidate.unlink()
                kind_dir.rmdir()
                continue
            for candidate in kind_dir.glob("*.json"):
                if candidate not in expected_files:
                    candidate.unlink()
