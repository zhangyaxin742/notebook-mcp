from __future__ import annotations

from hashlib import sha256
from urllib.parse import quote


def derive_key(seed: str) -> str:
    return sha256(seed.encode("utf-8")).hexdigest()[:16]


def notebook_key(raw_id: str | None, derived: str | None) -> str:
    return raw_id or derived or ""


def entity_key(raw_id: str | None, derived: str | None) -> str:
    return raw_id or derived or ""


def notebook_record_id(raw_id: str | None, derived: str | None) -> str:
    return f"nlm:notebook:{notebook_key(raw_id, derived)}"


def source_record_id(notebook_part: str, raw_id: str | None, derived: str | None) -> str:
    return f"nlm:source:{notebook_part}:{entity_key(raw_id, derived)}"


def artifact_record_id(
    notebook_part: str,
    artifact_kind: str,
    raw_id: str | None,
    derived: str | None,
) -> str:
    return f"nlm:artifact:{notebook_part}:{artifact_kind}:{entity_key(raw_id, derived)}"


def document_record_id(notebook_part: str, document_kind: str, origin_part: str) -> str:
    return f"nlm:document:{notebook_part}:{document_kind}:{origin_part}"


def chunk_record_id(document_id: str, chunk_index: int) -> str:
    return f"nlm:chunk:{document_id}:{chunk_index}"


def notebook_fallback_url(notebook_part: str) -> str:
    return f"notebooklm://notebook/{notebook_part}"


def source_fallback_url(notebook_part: str, source_part: str) -> str:
    return f"notebooklm://notebook/{notebook_part}/source/{source_part}"


def artifact_fallback_url(notebook_part: str, artifact_kind: str, artifact_part: str) -> str:
    return f"notebooklm://notebook/{notebook_part}/artifact/{artifact_kind}/{artifact_part}"


def safe_document_filename(document_id: str) -> str:
    return quote(document_id, safe="") + ".json"
