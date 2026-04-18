# Public Tool Contracts

This file defines the MCP tool surface other terminals must target.

## General Rules

- All public tools in v1 are read-only.
- All read-only tools must be marked with `readOnlyHint: true`.
- `search` and `fetch` must follow the ChatGPT-compatible input and output shapes exactly.
- Public tool handlers must read from canonical local data and retrieval services, not live NotebookLM.

## Tool: `search`

Purpose:

- global search across canonical persisted documents

Input schema:

```json
{
  "type": "object",
  "properties": {
    "query": { "type": "string" }
  },
  "required": ["query"],
  "additionalProperties": false
}
```

Tool result wrapper:

```json
{
  "content": [
    {
      "type": "text",
      "text": "{\"results\":[{\"id\":\"nlm:document:abc123:source_summary:src789\",\"title\":\"Example paper\",\"url\":\"https://example.com/paper\"}]}"
    }
  ]
}
```

Search payload shape inside `text`:

```json
{
  "results": [
    {
      "id": "nlm:document:abc123:source_summary:src789",
      "title": "Example paper",
      "url": "https://example.com/paper"
    }
  ]
}
```

Rules:

- `id` must be a `DocumentRecord.id`
- `title` must be the document title
- `url` must be the canonical document URL
- do not include score fields in the public `search` payload

## Tool: `fetch`

Purpose:

- fetch one canonical document by `DocumentRecord.id`

Input schema:

```json
{
  "type": "object",
  "properties": {
    "id": { "type": "string" }
  },
  "required": ["id"],
  "additionalProperties": false
}
```

Tool result wrapper:

```json
{
  "content": [
    {
      "type": "text",
      "text": "{\"id\":\"nlm:document:abc123:source_summary:src789\",\"title\":\"Example paper\",\"text\":\"NotebookLM-generated source summary.\",\"url\":\"https://example.com/paper\",\"metadata\":{\"origin_type\":\"source\",\"origin_id\":\"nlm:source:abc123:src789\",\"document_kind\":\"source_summary\",\"notebook_id\":\"nlm:notebook:abc123\"}}"
    }
  ]
}
```

Fetch payload shape inside `text`:

```json
{
  "id": "nlm:document:abc123:source_summary:src789",
  "title": "Example paper",
  "text": "NotebookLM-generated source summary.",
  "url": "https://example.com/paper",
  "metadata": {
    "origin_type": "source",
    "origin_id": "nlm:source:abc123:src789",
    "document_kind": "source_summary",
    "notebook_id": "nlm:notebook:abc123"
  }
}
```

Rules:

- `id` must equal the requested `DocumentRecord.id`
- `text` is document text only, not formatted binary or structured attachments
- `metadata` may add fields, but must include at least:
  - `origin_type`
  - `origin_id`
  - `document_kind`
  - `notebook_id`

## Companion Tools

These tools are allowed in v1 in addition to `search` and `fetch`.

### `list_notebooks`

Input:

```json
{
  "type": "object",
  "properties": {},
  "additionalProperties": false
}
```

Output:

- array of notebook summaries with `id`, `title`, `url`, `source_count`, `artifact_count`

### `get_notebook`

Input:

```json
{
  "type": "object",
  "properties": {
    "notebook_id": { "type": "string" }
  },
  "required": ["notebook_id"],
  "additionalProperties": false
}
```

Output:

- one notebook detail object matching the canonical notebook shape used internally

### `list_notebook_documents`

Input:

```json
{
  "type": "object",
  "properties": {
    "notebook_id": { "type": "string" },
    "document_kind": { "type": "string" }
  },
  "required": ["notebook_id"],
  "additionalProperties": false
}
```

Rules:

- `document_kind` is optional
- if provided, it must match an allowed `document_kind` from `data-model.md`

Output:

- array of document summaries with `id`, `title`, `url`, `document_kind`

### `search_notebook`

Input:

```json
{
  "type": "object",
  "properties": {
    "notebook_id": { "type": "string" },
    "query": { "type": "string" },
    "document_kind": { "type": "string" },
    "limit": { "type": "integer", "minimum": 1, "maximum": 50 }
  },
  "required": ["notebook_id", "query"],
  "additionalProperties": false
}
```

Output:

- array of document summaries with `id`, `title`, `url`, `document_kind`

### `get_sync_status`

Input:

```json
{
  "type": "object",
  "properties": {
    "notebook_id": { "type": "string" }
  },
  "additionalProperties": false
}
```

Output:

- sync status summary for one notebook or the whole local store

## Public Error Rules

- Unknown document IDs must return a clear not-found error.
- Public tools must not leak secrets, raw auth headers, or internal NotebookLM request details.
- Debug-only fields must not appear in public tool payloads.
