# Contracts Overview

This directory is the source of truth for shared interfaces in `notebook-mcp`.

Other terminals must implement against these contracts and must not invent alternative shapes. If a contract change is needed, stop and ask the user.

## Architecture Summary

The system has five runtime layers:

1. NotebookLM connector
2. Sync and normalization
3. Local persistence
4. Indexing and retrieval
5. MCP adapter

The connector reads from NotebookLM.
The sync layer converts raw NotebookLM entities into canonical local records.
The persistence layer stores those canonical records deterministically.
The retrieval layer searches only persisted canonical data.
The MCP server exposes retrieval and document access tools to ChatGPT and Claude over Streamable HTTP.

Current runtime seam decisions:

- the default MCP backend is the SQLite-backed local store and retrieval service
- the server may also be started with a null backend or a small in-memory demo backend for smoke testing
- the public transport is `streamable-http` only in v1
- HTTP access supports two security modes:
  - `local-dev`: loopback clients only
  - `bearer`: explicit bearer token plus allowed-origin checks
- NotebookLM endpoint configuration is loaded from a local JSON file under the auth runtime directory and auto-created with a default template when missing
- NotebookLM session storage is local-only and uses Windows DPAPI when available, otherwise permission-hardened plaintext storage

## Required Data Flow

The required flow is:

1. Authenticate to NotebookLM
2. Read raw notebooks, sources, and artifacts
3. Normalize raw entities into canonical records
4. Persist canonical records to disk and SQLite
5. Derive fetchable documents from canonical records
6. Build lexical and semantic indexes from those documents
7. Expose read-only MCP tools over the persisted/indexed data

Live NotebookLM chat is not part of the default v1 path.

## Shared Invariants

- All retrieval and MCP access must read from canonical local data, not directly from live NotebookLM.
- Every fetchable document must have a stable `id`, `title`, `text`, and canonical `url`.
- Provenance must be preserved back to the NotebookLM origin entity and source URL where available.
- Local snapshots must be deterministic and diff-friendly.
- Companion tools may be richer than ChatGPT `search` and `fetch`, but must remain read-only by default.
- Local operator state under `.local/` is runtime data, not repository data, and must remain ignored.

## Contract Files

- [data-model.md](./data-model.md): canonical entity shapes, IDs, URLs, examples
- [tool-contracts.md](./tool-contracts.md): public MCP tool contracts
- [ownership.md](./ownership.md): path ownership, shared-critical files, coordination rules
- [config.md](./config.md): shared configuration keys and storage paths

## Change Policy

- Terminal 1 owns this directory.
- Changes here are shared contract changes.
- Any terminal that needs a change here must ask the user and stop.
