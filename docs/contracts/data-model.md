# Canonical Data Model

This file defines the canonical entities that all downstream layers must use.

## Design Rules

- Canonical records are local system records, not raw NotebookLM payloads.
- Raw payload fields may be stored separately, but downstream code must not depend on raw field names.
- IDs are opaque strings. Treat them as stable identifiers, not user-facing labels.
- `DocumentRecord` is the canonical fetchable unit for retrieval and MCP `fetch`.

## ID Rules

### Raw ID Usage

If NotebookLM exposes a stable raw identifier for an entity, use it directly inside the canonical ID.

### Derived Key Usage

If a stable raw identifier is missing, derive `derived_key` as:

`sha256(stable_seed).hexdigest()[:16]`

The stable seed must be a UTF-8 string assembled exactly from the documented seed fields in this file.

## Canonical ID Formats

- `NotebookRecord.id = "nlm:notebook:{notebook_raw_id_or_derived_key}"`
- `SourceRecord.id = "nlm:source:{notebook_key}:{source_raw_id_or_derived_key}"`
- `ArtifactRecord.id = "nlm:artifact:{notebook_key}:{artifact_kind}:{artifact_raw_id_or_derived_key}"`
- `DocumentRecord.id = "nlm:document:{notebook_key}:{document_kind}:{origin_key}"`
- `ChunkRecord.id = "nlm:chunk:{document_id}:{chunk_index}"`

Where:

- `notebook_key` is the notebook raw ID if present, otherwise notebook `derived_key`
- `origin_key` is the origin raw ID if present, otherwise the origin `derived_key`

## Canonical URL Rules

Use the first applicable rule:

1. If the origin is a source and has a stable original source URL, use that.
2. If NotebookLM exposes a stable HTTPS notebook URL or artifact URL, use that.
3. Otherwise use a deterministic `notebooklm://` fallback URL.

Fallback URL formats:

- notebook: `notebooklm://notebook/{notebook_key}`
- source: `notebooklm://notebook/{notebook_key}/source/{source_key}`
- artifact: `notebooklm://notebook/{notebook_key}/artifact/{artifact_kind}/{artifact_key}`
- document: inherit the canonical URL of its origin entity

## NotebookRecord

Represents one NotebookLM notebook.

```json
{
  "id": "nlm:notebook:abc123",
  "origin": "notebooklm",
  "raw_id": "abc123",
  "derived_key": null,
  "title": "AI Safety Research",
  "url": "https://notebooklm.google.com/notebook/abc123",
  "source_count": 143,
  "artifact_count": 8,
  "last_synced_at": "2026-04-18T20:00:00Z",
  "metadata": {
    "share_mode": "private"
  }
}
```

Required fields:

- `id`
- `origin`
- `title`
- `url`

Optional fields:

- `raw_id`
- `derived_key`
- `source_count`
- `artifact_count`
- `last_synced_at`
- `metadata`

Notebook stable seed when raw ID is missing:

`"notebook|" + title`

## SourceRecord

Represents one source attached to a notebook.

```json
{
  "id": "nlm:source:abc123:src789",
  "notebook_id": "nlm:notebook:abc123",
  "origin": "notebooklm",
  "raw_id": "src789",
  "derived_key": null,
  "title": "Example paper",
  "url": "https://example.com/paper",
  "source_type": "web",
  "summary_text": "NotebookLM-generated source summary.",
  "created_at": null,
  "metadata": {
    "author": null
  }
}
```

Required fields:

- `id`
- `notebook_id`
- `origin`
- `title`
- `url`
- `source_type`

Optional fields:

- `raw_id`
- `derived_key`
- `summary_text`
- `created_at`
- `metadata`

Source stable seed when raw ID is missing:

`"source|" + notebook_id + "|" + title + "|" + url`

## ArtifactRecord

Represents a generated notebook artifact or notebook-authored text object.

Allowed `artifact_kind` values:

- `briefing_doc`
- `study_guide`
- `faq`
- `custom_report`
- `audio_overview`
- `video_overview`
- `transcript`
- `note`
- `table`
- `notebook_overview`

```json
{
  "id": "nlm:artifact:abc123:briefing_doc:art456",
  "notebook_id": "nlm:notebook:abc123",
  "origin": "notebooklm",
  "artifact_kind": "briefing_doc",
  "raw_id": "art456",
  "derived_key": null,
  "title": "Briefing document",
  "url": "notebooklm://notebook/abc123/artifact/briefing_doc/art456",
  "text": "Full artifact text.",
  "mime_type": "text/markdown",
  "metadata": {
    "source_count": 143
  }
}
```

Required fields:

- `id`
- `notebook_id`
- `origin`
- `artifact_kind`
- `title`
- `url`

Optional fields:

- `raw_id`
- `derived_key`
- `text`
- `mime_type`
- `metadata`

Artifact stable seed when raw ID is missing:

`"artifact|" + notebook_id + "|" + artifact_kind + "|" + title`

## DocumentRecord

This is the canonical fetchable unit for retrieval and MCP `fetch`.

Allowed `document_kind` values:

- `source_summary`
- `artifact_text`
- `note_text`
- `transcript_text`
- `table_text`
- `notebook_overview`

```json
{
  "id": "nlm:document:abc123:source_summary:src789",
  "notebook_id": "nlm:notebook:abc123",
  "origin_type": "source",
  "origin_id": "nlm:source:abc123:src789",
  "document_kind": "source_summary",
  "title": "Example paper",
  "text": "NotebookLM-generated source summary.",
  "url": "https://example.com/paper",
  "content_sha256": "5f8e8d3f5c6a0b7d62c55883f0b56df2e15d8978cfe2a6b9cb9f4ed4cf9d3e3b",
  "metadata": {
    "source_type": "web"
  }
}
```

Required fields:

- `id`
- `notebook_id`
- `origin_type`
- `origin_id`
- `document_kind`
- `title`
- `text`
- `url`
- `content_sha256`

Optional fields:

- `metadata`

Document rules:

- One document has exactly one origin entity.
- Documents are the units returned by `fetch`.
- Search returns document IDs, not source IDs or artifact IDs.
- Document text must be plain text or markdown-compatible text. Do not return binary data.

Document stable seed when origin raw ID is missing:

`"document|" + notebook_id + "|" + document_kind + "|" + origin_id`

## ChunkRecord

Represents one retrieval chunk derived from a document.

```json
{
  "id": "nlm:chunk:nlm:document:abc123:artifact_text:art456:0",
  "document_id": "nlm:document:abc123:artifact_text:art456",
  "notebook_id": "nlm:notebook:abc123",
  "chunk_index": 0,
  "text": "Chunk text...",
  "char_start": 0,
  "char_end": 512,
  "token_count_estimate": 128,
  "content_sha256": "e0b153045b90d56fb24c4c6c8b4c7d7244e0eb5e8f0d80d7efb0fd897f0b3bc7",
  "metadata": {
    "document_kind": "artifact_text"
  }
}
```

Required fields:

- `id`
- `document_id`
- `notebook_id`
- `chunk_index`
- `text`
- `content_sha256`

Optional fields:

- `char_start`
- `char_end`
- `token_count_estimate`
- `metadata`

## Snapshot Layout

Canonical disk layout under the data root:

```text
<data_root>/
  notebooks/
    <notebook_key>/
      manifest.json
      sources/
        <source_key>.json
      artifacts/
        <artifact_kind>/
          <artifact_key>.json
      documents/
        <document_id_safe>.json
```

Rules:

- Snapshot JSON must be deterministic and sorted where practical.
- `document_id_safe` may be a filesystem-safe encoded form of `DocumentRecord.id`, but the JSON body must contain the original `id`.
