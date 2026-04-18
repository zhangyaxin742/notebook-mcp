# notebook-mcp

`notebook-mcp` is a self-hosted MCP server and local research pipeline for NotebookLM-derived data. It is designed to:

- authenticate to a private NotebookLM session
- sync NotebookLM notebooks into canonical local records
- persist snapshots and SQLite state under a local data directory
- build retrieval indexes over canonical documents
- expose read-only MCP tools such as `search` and `fetch` over Streamable HTTP

The system is still oriented toward careful operator setup. NotebookLM integration depends on undocumented behavior and may drift.

## Current Status

Implemented today:

- shared contracts under `docs/contracts/`
- NotebookLM auth CLI and endpoint discovery surfaces
- canonical SQLite store and snapshot writer
- retrieval and MCP transport/runtime smoke coverage
- Streamable HTTP MCP server with `local-dev` and `bearer` auth modes

Not packaged yet:

- there is no `pyproject.toml`, lockfile, or pinned dependency manifest in this repository
- sync and reindex are implemented as library surfaces, not stable operator CLIs
- real private-account validation is still required before treating the system as deployment-ready

## Repository Layout

- `src/auth/`: session bootstrap, validation, endpoint discovery, protected session storage
- `src/notebooklm_client/`: raw NotebookLM connector and endpoint config loading
- `src/sync/`: normalization, sync orchestration, persisted chunk reindexing
- `src/store/`: canonical records, SQLite store, snapshot writer
- `src/retrieval/`, `src/index/`: chunking, lexical search, semantic search, retrieval
- `src/mcp_server/`: MCP protocol server, Streamable HTTP transport, public tools
- `docs/contracts/`: shared data model, ownership, and MCP tool contracts
- `tests/`: stdlib `unittest` validation harness

## Prerequisites

- Python 3.11+ recommended
- Windows is the best-supported runtime today for protected session storage because the auth store uses DPAPI when available
- Playwright is optional and only needed for browser-driven NotebookLM login/bootstrap or endpoint discovery

## Install And Validate

This repository currently has no dependency manifest. The baseline validation path uses the Python standard library only.

1. Create and activate a virtual environment.
2. Copy `.env.example` to your local shell or local env tooling as needed. Do not commit secrets.
3. Run the baseline test harness:

```powershell
python -m unittest discover -s tests -v
```

4. Optional transport smoke validation:

```powershell
python -m src.mcp_server.validate_transport
```

If you plan to use browser bootstrap flows, install Playwright separately in your local environment before running the auth CLI.

## Configuration

Default local state lives under `.local/notebook-mcp/` and is intentionally ignored by git.

Important environment variables:

- `NOTEBOOK_MCP_DATA_DIR`: local data root, default `.local/notebook-mcp`
- `NOTEBOOK_MCP_DB_PATH`: SQLite path, default `.local/notebook-mcp/db/notebook_mcp.sqlite3`
- `NOTEBOOK_MCP_HOST`: HTTP bind host, default `127.0.0.1`
- `NOTEBOOK_MCP_PORT`: HTTP bind port, default `8000`
- `NOTEBOOK_MCP_TRANSPORT`: currently `streamable-http` only
- `NOTEBOOK_MCP_AUTH_MODE`: `local-dev` or `bearer`
- `NOTEBOOK_MCP_BEARER_TOKEN`: required in `bearer` mode
- `NOTEBOOK_MCP_ALLOWED_ORIGINS`: comma-separated origin allowlist for `bearer` mode
- `NOTEBOOK_MCP_BROWSER_PROFILE_DIR`: local browser profile path for auth/bootstrap flows

NotebookLM endpoint config is loaded from:

```text
.local/notebook-mcp/auth/notebooklm_endpoints.json
```

If the file is missing, the runtime creates a default template. That template is only a best-effort guess. Replace it with discovered live endpoints when NotebookLM drifts.

## Auth And Endpoint Discovery

Auth utilities are available through:

```powershell
python -m src.auth.cli login
python -m src.auth.cli validate
python -m src.auth.cli doctor
python -m src.auth.cli discover-endpoints
```

Useful flags:

- `python -m src.auth.cli login --headless`
- `python -m src.auth.cli doctor --playwright-fallback --auto-recover-auth`
- `python -m src.auth.cli discover-endpoints --bootstrap-login`

Session state is stored under `.local/notebook-mcp/auth/session.json`. On Windows the store uses DPAPI when available. On runtimes without strong OS-backed encryption, the store falls back to permission-hardened plaintext and warns the operator.

## Sync And Reindex

The sync and reindex implementations exist, but they are currently library-first surfaces rather than stable operator CLIs.

Key entry points:

- `src.sync.service.NotebookSyncService`
- `src.sync.reindex.PersistedChunkReindexer`

Executable examples today:

- `tests/test_terminal3_sync.py`
- `tests/test_terminal4_retrieval.py`

Expected flow:

1. authenticate and validate NotebookLM access
2. load or discover NotebookLM endpoint config
3. sync a notebook into canonical SQLite state and deterministic snapshots
4. rebuild persisted retrieval indexes from canonical chunks when needed

## Serve The MCP Server

Start the MCP server with:

```powershell
python -m src.mcp_server
```

Useful modes:

```powershell
python -m src.mcp_server --demo-data
python -m src.mcp_server --null-backend
python -m src.mcp_server --auth-mode bearer --allow-origin https://chat.openai.com
python -m src.mcp_server --data-dir .local/notebook-mcp --db-path .local/notebook-mcp/db/notebook_mcp.sqlite3
```

Current runtime behavior:

- default backend: SQLite-backed local store and retrieval service
- validation backends: `--demo-data` and `--null-backend`
- transport: `streamable-http`
- endpoint path: `/mcp`

Public tools:

- `search`
- `fetch`
- `list_notebooks`
- `get_notebook`
- `list_notebook_documents`
- `search_notebook`
- `get_sync_status`

## Security Warnings

- Do not commit anything under `.local/`.
- Do not store NotebookLM cookies, CSRF material, or bearer tokens in committed files, fixtures, or shell history.
- `local-dev` mode is for loopback-only development. It is not a remote security boundary.
- Remote exposure should use `bearer` mode with a strong token managed outside the repository and an explicit `NOTEBOOK_MCP_ALLOWED_ORIGINS` allowlist.
- The endpoint config file is not a secret store. It must not contain cookies, session exports, or bearer tokens.
- Treat NotebookLM endpoint discovery output as unstable operator config, not a durable public API contract.

## More Documentation

- [docs/contracts/overview.md](docs/contracts/overview.md)
- [docs/contracts/data-model.md](docs/contracts/data-model.md)
- [docs/contracts/tool-contracts.md](docs/contracts/tool-contracts.md)
- [docs/contracts/config.md](docs/contracts/config.md)
- [docs/setup.md](docs/setup.md)
- [docs/runbook.md](docs/runbook.md)
- [docs/setup-production-readiness.md](docs/setup-production-readiness.md)
