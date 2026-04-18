# Ownership Map

This file defines which terminal owns which paths and which files are shared-critical.

## Shared-Critical Files

These files are shared-critical:

- `AGENTS.md`
- `CODEX.md`
- `README.md`
- top-level dependency manifests
- lockfiles
- `.gitignore`
- `.env.example`
- `docs/contracts/**`

Only Terminal 1 may edit shared-critical files by default.

## Terminal Path Ownership

### Terminal 1

Owned paths:

- `docs/contracts/**`
- `docs/status/terminal-1.md`
- shared-critical files

Responsibilities:

- contracts
- shared skeleton
- ownership map

### Terminal 2

Owned paths:

- `src/notebooklm_client/**`
- `src/auth/**`
- `docs/status/terminal-2.md`

Responsibilities:

- NotebookLM auth
- connector abstraction
- internal HTTP client
- Playwright fallback for auth/bootstrap/recovery

### Terminal 3

Owned paths:

- `src/sync/**`
- `src/store/**`
- `docs/status/terminal-3.md`

Responsibilities:

- sync orchestration
- normalization
- local snapshots
- SQLite persistence

### Terminal 4

Owned paths:

- `src/index/**`
- `src/retrieval/**`
- `docs/status/terminal-4.md`

Responsibilities:

- chunking
- indexing
- lexical search
- semantic search
- hybrid retrieval

### Terminal 5

Owned paths:

- `src/mcp_server/**`
- `docs/status/terminal-5.md`

Responsibilities:

- MCP server
- transport
- public tool adapters

### Terminal 6

Owned paths:

- `tests/**`
- `fixtures/**`
- `docs/setup*`
- `docs/runbook*`
- `docs/status/terminal-6.md`

Responsibilities:

- tests
- fixtures
- validation
- setup and runbooks

## Coordination Rules

- Do not edit another terminal's owned path.
- Do not edit shared-critical files unless you are Terminal 1 or the user explicitly approved it.
- If a required change crosses ownership boundaries, ask the user and stop.
- Use `docs/status/terminal-<n>.md` for factual status updates, not design decisions.
- Shared design decisions belong in `docs/contracts/**`.
- Runtime-generated state under `.local/`, Python cache directories, compiled bytecode, browser profiles, session files, logs, and local SQLite artifacts must not be committed.

## Readiness Gate

Terminals 2 through 6 must not start implementation until these files exist:

- `docs/contracts/overview.md`
- `docs/contracts/data-model.md`
- `docs/contracts/tool-contracts.md`
- `docs/contracts/ownership.md`

## Initial Skeleton Directories

These directories are intentionally present for the owning terminals to fill in later:

- `src/notebooklm_client/`
- `src/auth/`
- `src/sync/`
- `src/store/`
- `src/index/`
- `src/retrieval/`
- `src/mcp_server/`
- `tests/`
- `fixtures/`
