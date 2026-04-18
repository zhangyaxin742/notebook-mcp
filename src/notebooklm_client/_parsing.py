from __future__ import annotations

from typing import Any

from .errors import UnsupportedShapeError
from .models import RawArtifact, RawNotebook, RawSource, derive_entity_key


def _first_non_empty(item: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _first_int(item: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def extract_items(
    payload: Any,
    *,
    label: str,
    root_keys: tuple[str, ...] = (),
    fallback_keys: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
        return [dict(item) for item in payload]
    if not isinstance(payload, dict):
        raise UnsupportedShapeError(
            f"{label} payload is not a JSON object or list.",
            details={"payload_type": type(payload).__name__},
        )

    for key in root_keys + fallback_keys:
        candidate = payload.get(key)
        if isinstance(candidate, list) and all(isinstance(item, dict) for item in candidate):
            return [dict(item) for item in candidate]

    raise UnsupportedShapeError(
        f"{label} payload does not contain a supported item list.",
        details={"keys": sorted(payload.keys())},
    )


def _url_for_entity(
    item: dict[str, Any],
    *,
    fallback_base: str,
    raw_id: str | None,
    suffix: str,
) -> str | None:
    direct = _first_non_empty(item, ("url", "sourceUrl", "shareUrl", "notebookUrl", "href"))
    if direct is not None:
        return direct
    if raw_id is None:
        return None
    return f"{fallback_base.rstrip('/')}/{suffix}/{raw_id}"


def parse_raw_notebook(item: dict[str, Any], *, base_url: str) -> RawNotebook:
    raw_id = _first_non_empty(item, ("id", "notebookId", "notebook_id"))
    title = _first_non_empty(item, ("title", "name", "label"))
    if title is None:
        raise UnsupportedShapeError(
            "Notebook item is missing a title-like field.",
            details={"keys": sorted(item.keys())},
        )
    entity_key = raw_id or derive_entity_key(f"notebook|{title}")
    return RawNotebook(
        entity_key=entity_key,
        raw_id=raw_id,
        title=title,
        url=_url_for_entity(item, fallback_base=base_url, raw_id=raw_id, suffix="notebook"),
        source_count=_first_int(item, ("sourceCount", "source_count", "sourcesCount")),
        artifact_count=_first_int(item, ("artifactCount", "artifact_count", "artifactsCount")),
        raw_payload=dict(item),
    )


def parse_raw_source(
    item: dict[str, Any],
    *,
    notebook_key: str,
    base_url: str,
) -> RawSource:
    raw_id = _first_non_empty(item, ("id", "sourceId", "source_id"))
    title = _first_non_empty(item, ("title", "name", "label", "displayName"))
    if title is None:
        raise UnsupportedShapeError(
            "Source item is missing a title-like field.",
            details={"keys": sorted(item.keys())},
        )
    url = _url_for_entity(item, fallback_base=base_url, raw_id=raw_id, suffix="source")
    entity_key = raw_id or derive_entity_key(
        f"source|{notebook_key}|{title}|{url or ''}"
    )
    return RawSource(
        entity_key=entity_key,
        notebook_key=notebook_key,
        raw_id=raw_id,
        title=title,
        url=url,
        source_type=_first_non_empty(item, ("sourceType", "source_type", "type", "kind")),
        summary_text=_first_non_empty(
            item,
            ("summaryText", "summary", "autoSummary", "generatedSummary"),
        ),
        raw_payload=dict(item),
    )


def parse_raw_artifact(
    item: dict[str, Any],
    *,
    notebook_key: str,
    base_url: str,
) -> RawArtifact:
    raw_id = _first_non_empty(item, ("id", "artifactId", "artifact_id"))
    artifact_kind = _first_non_empty(item, ("artifactKind", "artifact_kind", "type", "kind"))
    title = _first_non_empty(item, ("title", "name", "label", "displayName")) or artifact_kind
    if title is None:
        raise UnsupportedShapeError(
            "Artifact item is missing a title-like field.",
            details={"keys": sorted(item.keys())},
        )
    entity_key = raw_id or derive_entity_key(
        f"artifact|{notebook_key}|{artifact_kind or ''}|{title}"
    )
    return RawArtifact(
        entity_key=entity_key,
        notebook_key=notebook_key,
        raw_id=raw_id,
        artifact_kind=artifact_kind,
        title=title,
        url=_url_for_entity(item, fallback_base=base_url, raw_id=raw_id, suffix="artifact"),
        text=_first_non_empty(item, ("text", "content", "markdown", "body")),
        mime_type=_first_non_empty(item, ("mimeType", "mime_type", "contentType")),
        raw_payload=dict(item),
    )
