from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from src.store.ids import (
    artifact_fallback_url,
    artifact_record_id,
    derive_key,
    document_record_id,
    entity_key,
    notebook_fallback_url,
    notebook_key,
    notebook_record_id,
    source_fallback_url,
    source_record_id,
)
from src.store.models import (
    ArtifactRecord,
    DocumentRecord,
    NormalizedNotebookSnapshot,
    NotebookRecord,
    SourceRecord,
    SyncFailure,
    content_sha256,
)


ARTIFACT_KIND_ALIASES = {
    "audio overview": "audio_overview",
    "audio_overview": "audio_overview",
    "briefing": "briefing_doc",
    "briefing doc": "briefing_doc",
    "briefing_doc": "briefing_doc",
    "custom report": "custom_report",
    "custom_report": "custom_report",
    "faq": "faq",
    "note": "note",
    "notebook overview": "notebook_overview",
    "notebook_overview": "notebook_overview",
    "overview": "notebook_overview",
    "study guide": "study_guide",
    "study_guide": "study_guide",
    "table": "table",
    "transcript": "transcript",
    "video overview": "video_overview",
    "video_overview": "video_overview",
}

ARTIFACT_TO_DOCUMENT_KIND = {
    "briefing_doc": "artifact_text",
    "study_guide": "artifact_text",
    "faq": "artifact_text",
    "custom_report": "artifact_text",
    "audio_overview": "artifact_text",
    "video_overview": "artifact_text",
    "transcript": "transcript_text",
    "note": "note_text",
    "table": "table_text",
    "notebook_overview": "notebook_overview",
}


def normalize_notebook_bundle(raw_bundle: Mapping[str, Any], synced_at: str) -> NormalizedNotebookSnapshot:
    notebook, notebook_context = _normalize_notebook(raw_bundle, synced_at)
    failures: list[SyncFailure] = []

    sources: list[SourceRecord] = []
    for raw_source in _coerce_sequence(
        _first_present(raw_bundle, "sources", "source_items", "sourceItems"),
        entity_type="source",
        failures=failures,
    ):
        try:
            source = _normalize_source(raw_source, notebook, notebook_context)
        except ValueError as exc:
            failures.append(SyncFailure(entity_type="source", message=str(exc), details=_compact_details(raw_source)))
            continue
        sources.append(source)

    artifacts: list[ArtifactRecord] = []
    for raw_artifact in _coerce_sequence(
        _first_present(raw_bundle, "artifacts", "artifact_items", "artifactItems"),
        entity_type="artifact",
        failures=failures,
    ):
        try:
            artifact = _normalize_artifact(raw_artifact, notebook, notebook_context)
        except ValueError as exc:
            failures.append(
                SyncFailure(entity_type="artifact", message=str(exc), details=_compact_details(raw_artifact))
            )
            continue
        artifacts.append(artifact)

    notebook = NotebookRecord(
        id=notebook.id,
        origin=notebook.origin,
        title=notebook.title,
        url=notebook.url,
        raw_id=notebook.raw_id,
        derived_key=notebook.derived_key,
        source_count=len(sources),
        artifact_count=len(artifacts),
        last_synced_at=synced_at,
        metadata=notebook.metadata,
    )

    documents: list[DocumentRecord] = []
    for source in sources:
        if source.summary_text:
            documents.append(_source_document(source, notebook_context))
    for artifact in artifacts:
        if artifact.text:
            documents.append(_artifact_document(artifact, notebook_context))

    return NormalizedNotebookSnapshot(
        notebook=notebook,
        sources=tuple(sorted(sources, key=lambda item: item.id)),
        artifacts=tuple(sorted(artifacts, key=lambda item: item.id)),
        documents=tuple(sorted(documents, key=lambda item: item.id)),
        failures=tuple(failures),
    )


def _normalize_notebook(raw_bundle: Mapping[str, Any], synced_at: str) -> tuple[NotebookRecord, dict[str, str]]:
    raw_id = _optional_string(_first_present(raw_bundle, "id", "notebook_id", "notebookId"))
    title = _required_string(_first_present(raw_bundle, "title", "name"), "Notebook title is required")
    derived = None if raw_id else derive_key(f"notebook|{title}")
    notebook_part = notebook_key(raw_id, derived)
    url = _optional_string(_first_present(raw_bundle, "url", "notebook_url", "notebookUrl")) or notebook_fallback_url(
        notebook_part
    )
    metadata = _metadata_from_mapping(raw_bundle, excluded_keys={"id", "notebook_id", "notebookId", "title", "name", "url", "notebook_url", "notebookUrl", "sources", "source_items", "sourceItems", "artifacts", "artifact_items", "artifactItems"})
    notebook = NotebookRecord(
        id=notebook_record_id(raw_id, derived),
        origin="notebooklm",
        raw_id=raw_id,
        derived_key=derived,
        title=title,
        url=url,
        source_count=None,
        artifact_count=None,
        last_synced_at=synced_at,
        metadata=metadata,
    )
    return notebook, {"notebook_id": notebook.id, "notebook_part": notebook_part}


def _normalize_source(
    raw_source: Mapping[str, Any],
    notebook: NotebookRecord,
    notebook_context: Mapping[str, str],
) -> SourceRecord:
    title = _required_string(_first_present(raw_source, "title", "name"), "Source title is required")
    raw_id = _optional_string(_first_present(raw_source, "id", "source_id", "sourceId"))
    source_url = _optional_string(_first_present(raw_source, "url", "source_url", "sourceUrl"))
    derived = None if raw_id else derive_key(f"source|{notebook.id}|{title}|{source_url or ''}")
    source_part = entity_key(raw_id, derived)
    summary_text = _optional_text(_first_present(raw_source, "summary_text", "summaryText", "summary"))
    source_type = _optional_string(_first_present(raw_source, "source_type", "sourceType", "type")) or "unknown"
    return SourceRecord(
        id=source_record_id(notebook_context["notebook_part"], raw_id, derived),
        notebook_id=notebook.id,
        origin="notebooklm",
        raw_id=raw_id,
        derived_key=derived,
        title=title,
        url=source_url or source_fallback_url(notebook_context["notebook_part"], source_part),
        source_type=source_type,
        summary_text=summary_text,
        created_at=_optional_string(_first_present(raw_source, "created_at", "createdAt")),
        metadata=_metadata_from_mapping(
            raw_source,
            excluded_keys={
                "id",
                "source_id",
                "sourceId",
                "title",
                "name",
                "url",
                "source_url",
                "sourceUrl",
                "source_type",
                "sourceType",
                "type",
                "summary_text",
                "summaryText",
                "summary",
                "created_at",
                "createdAt",
            },
        ),
    )


def _normalize_artifact(
    raw_artifact: Mapping[str, Any],
    notebook: NotebookRecord,
    notebook_context: Mapping[str, str],
) -> ArtifactRecord:
    title = _required_string(_first_present(raw_artifact, "title", "name"), "Artifact title is required")
    raw_id = _optional_string(_first_present(raw_artifact, "id", "artifact_id", "artifactId"))
    raw_kind = _required_string(
        _first_present(raw_artifact, "artifact_kind", "artifactKind", "kind", "type"),
        "Artifact kind is required",
    )
    artifact_kind = ARTIFACT_KIND_ALIASES.get(raw_kind.strip().lower())
    if artifact_kind is None:
        raise ValueError(f"Unsupported artifact kind: {raw_kind}")
    derived = None if raw_id else derive_key(f"artifact|{notebook.id}|{artifact_kind}|{title}")
    artifact_part = entity_key(raw_id, derived)
    artifact_url = _optional_string(_first_present(raw_artifact, "url", "artifact_url", "artifactUrl"))
    artifact_text = _optional_text(_first_present(raw_artifact, "text", "content", "body", "markdown", "transcript"))
    return ArtifactRecord(
        id=artifact_record_id(notebook_context["notebook_part"], artifact_kind, raw_id, derived),
        notebook_id=notebook.id,
        origin="notebooklm",
        artifact_kind=artifact_kind,
        raw_id=raw_id,
        derived_key=derived,
        title=title,
        url=artifact_url or artifact_fallback_url(notebook_context["notebook_part"], artifact_kind, artifact_part),
        text=artifact_text,
        mime_type=_optional_string(_first_present(raw_artifact, "mime_type", "mimeType")),
        metadata=_metadata_from_mapping(
            raw_artifact,
            excluded_keys={
                "id",
                "artifact_id",
                "artifactId",
                "artifact_kind",
                "artifactKind",
                "kind",
                "type",
                "title",
                "name",
                "url",
                "artifact_url",
                "artifactUrl",
                "text",
                "content",
                "body",
                "markdown",
                "transcript",
                "mime_type",
                "mimeType",
            },
        ),
    )


def _source_document(source: SourceRecord, notebook_context: Mapping[str, str]) -> DocumentRecord:
    origin_part = entity_key(source.raw_id, source.derived_key)
    return DocumentRecord(
        id=document_record_id(notebook_context["notebook_part"], "source_summary", origin_part),
        notebook_id=source.notebook_id,
        origin_type="source",
        origin_id=source.id,
        document_kind="source_summary",
        title=source.title,
        text=source.summary_text or "",
        url=source.url,
        content_sha256=content_sha256(source.summary_text or ""),
        metadata={"source_type": source.source_type},
    )


def _artifact_document(artifact: ArtifactRecord, notebook_context: Mapping[str, str]) -> DocumentRecord:
    origin_part = entity_key(artifact.raw_id, artifact.derived_key)
    document_kind = ARTIFACT_TO_DOCUMENT_KIND[artifact.artifact_kind]
    metadata = {"artifact_kind": artifact.artifact_kind}
    if artifact.mime_type:
        metadata["mime_type"] = artifact.mime_type
    return DocumentRecord(
        id=document_record_id(notebook_context["notebook_part"], document_kind, origin_part),
        notebook_id=artifact.notebook_id,
        origin_type="artifact",
        origin_id=artifact.id,
        document_kind=document_kind,
        title=artifact.title,
        text=artifact.text or "",
        url=artifact.url,
        content_sha256=content_sha256(artifact.text or ""),
        metadata=metadata,
    )


def _first_present(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _required_string(value: Any, error_message: str) -> str:
    string_value = _optional_string(value)
    if string_value:
        return string_value
    raise ValueError(error_message)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, Mapping):
        return "\n".join(f"{key}: {value[key]}" for key in sorted(value))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        parts = [_optional_text(item) for item in value]
        compact = [part for part in parts if part]
        return "\n\n".join(compact) if compact else None
    return None


def _coerce_sequence(
    value: Any,
    *,
    entity_type: str,
    failures: list[SyncFailure],
) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        normalized_items: list[Mapping[str, Any]] = []
        for item in value:
            if isinstance(item, Mapping):
                normalized_items.append(item)
                continue
            failures.append(
                SyncFailure(
                    entity_type=entity_type,
                    message="Entity payload must be a mapping",
                    details={"value_repr": repr(item)},
                )
            )
        return normalized_items
    return []


def _metadata_from_mapping(mapping: Mapping[str, Any], excluded_keys: set[str]) -> dict[str, Any]:
    metadata = {}
    for key in sorted(mapping):
        if key in excluded_keys:
            continue
        normalized = _metadata_value(mapping[key])
        if normalized is not _SKIP:
            metadata[key] = normalized
    return metadata


def _compact_details(mapping: Mapping[str, Any]) -> dict[str, Any]:
    details = {}
    for key in sorted(mapping):
        value = mapping[key]
        if isinstance(value, (str, int, float, bool)) or value is None:
            details[key] = value
    return details


_SKIP = object()


def _metadata_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {
            nested_key: normalized
            for nested_key in sorted(value)
            if (normalized := _metadata_value(value[nested_key])) is not _SKIP
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [normalized for item in value if (normalized := _metadata_value(item)) is not _SKIP]
    return _SKIP
