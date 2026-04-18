# Setup Guide

This guide is owned by Terminal 6 and documents the expected operator flow for a new contributor.

Current repository state on 2026-04-18:

- shared contracts exist
- Terminal 6 validation scaffolding exists
- runtime login, sync, indexing, and serve entrypoints are still pending implementation in other owned paths

Because of that, this document distinguishes between:

- what can be validated today
- what a contributor should verify once the remaining terminals land their code

## Baseline Setup

1. Install a recent Python 3 runtime.
2. Review `docs/contracts/overview.md`, `docs/contracts/data-model.md`, and `docs/contracts/tool-contracts.md` before changing runtime behavior.
3. Use `.env.example` as the reference for local environment variables. Keep secrets out of the repository and out of committed shell history.
4. Expect local state to live under `.local/notebook-mcp/` by default, with storage for `db/`, `snapshots/`, `auth/`, `logs/`, and `cache/`.

## Validation Available Today

The current repository has no shipped runtime commands yet. The validation path available today is the Terminal 6 baseline harness:

```powershell
python -m unittest discover -s tests -v
```

This validates:

- scrubbed fixtures are present and deterministic
- committed fixtures do not contain obvious live secret material
- setup and runbook docs cover the required flows and failure modes

## Expected Login Flow

The login flow belongs to Terminal 2 and is not implemented in this repository snapshot yet.

When it lands, the operator path should be:

1. start a login bootstrap or doctor command
2. complete the authenticated browser step without exporting raw cookies manually
3. validate that session state is stored only in local ignored paths under the data directory
4. confirm that logs and fixtures remain scrubbed

Validation checkpoint:

- a doctor-style command should distinguish expired auth from endpoint drift and unsupported response shape
- no committed file should contain browser session state, cookie values, or bearer tokens

## Expected Sync Flow

The sync flow belongs to Terminal 3 and is not implemented in this repository snapshot yet.

When it lands, the operator path should be:

1. trigger a sync against the shared connector abstraction
2. persist deterministic snapshots under the local data directory
3. write canonical notebook, source, artifact, document, and chunk records
4. make partial failures explicit instead of silently succeeding

Validation checkpoint:

- repeated syncs should be idempotent at the logical record level
- provenance and canonical URLs should remain present in persisted records
- a failed sync should produce an explicit status instead of hiding missing data

## Expected Reindex Flow

The reindex flow belongs to Terminal 4 and is not implemented in this repository snapshot yet.

When it lands, the operator path should be:

1. rebuild lexical and semantic indexes from canonical persisted data only
2. avoid live NotebookLM access during indexing
3. validate both global and notebook-scoped retrieval paths

Validation checkpoint:

- document IDs returned by retrieval should always be canonical `DocumentRecord.id` values
- chunking behavior should be deterministic for the same document content

## Expected Serve Flow

The serve flow belongs to Terminal 5 and is not implemented in this repository snapshot yet.

When it lands, the operator path should be:

1. start the MCP server over the configured remote HTTP transport
2. verify the public tool list is read-only by default
3. call `search(query: string)` and `fetch(id: string)` against persisted local data

Validation checkpoint:

- `search` returns only `id`, `title`, and canonical `url`
- `fetch` returns one canonical document payload and a clear not-found error for unknown IDs
- tool metadata marks read-only tools with `readOnlyHint: true`

## Known Setup Limitations

- This repository does not yet define the final command names for login, sync, reindex, or serve.
- Baseline validation is currently contract- and fixture-driven, not end-to-end runtime validation.
- NotebookLM is integrated through undocumented behavior, so operator expectations should assume drift risk and periodic maintenance.
