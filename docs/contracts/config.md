# Shared Configuration Contract

This file defines the shared configuration keys and storage defaults other terminals may assume.

## Storage Defaults

Default data root:

- `.local/notebook-mcp/`

Expected subpaths under the data root:

- `db/notebook_mcp.sqlite3`
- `snapshots/`
- `auth/`
- `logs/`
- `cache/`

These are defaults, not hardcoded paths. Implementation may allow overrides, but other terminals may assume this default layout exists conceptually.

## Shared Environment Variables

Use these names if environment variables are needed:

- `NOTEBOOK_MCP_DATA_DIR`
- `NOTEBOOK_MCP_DB_PATH`
- `NOTEBOOK_MCP_LOG_LEVEL`
- `NOTEBOOK_MCP_HOST`
- `NOTEBOOK_MCP_PORT`
- `NOTEBOOK_MCP_TRANSPORT`
- `NOTEBOOK_MCP_AUTH_MODE`
- `NOTEBOOK_MCP_BEARER_TOKEN`
- `NOTEBOOK_MCP_ALLOWED_ORIGINS`
- `NOTEBOOK_MCP_EMBEDDING_BACKEND`
- `NOTEBOOK_MCP_EMBEDDING_MODEL`
- `NOTEBOOK_MCP_BROWSER_PROFILE_DIR`

Auth mode rules:

- `NOTEBOOK_MCP_AUTH_MODE=local-dev` means loopback clients only
- `NOTEBOOK_MCP_AUTH_MODE=bearer` requires `NOTEBOOK_MCP_BEARER_TOKEN`
- `NOTEBOOK_MCP_ALLOWED_ORIGINS` is a comma-separated allowlist used in bearer mode
- `NOTEBOOK_MCP_BEARER_TOKEN` is an operator secret and must never appear in `.env.example`, committed docs, or fixtures

## NotebookLM Endpoint Config

NotebookLM internal HTTP endpoints are unstable and must not be hardcoded across multiple subsystems.

The shared endpoint config file location is:

- `<data_root>/auth/notebooklm_endpoints.json`

Implementations may auto-create this file with a repository default endpoint template if it does not exist yet. The current runtime does exactly that through `ensure_endpoint_config()`, and operators should replace that template with discovered live NotebookLM endpoints when available.

This file is local operator configuration, not a committed secret. It may contain unstable internal paths, request shapes, and parsing hints, but it must not contain auth cookies, bearer tokens, or other secrets.

Expected JSON shape:

```json
{
  "base_url": "https://notebooklm.google.com",
  "endpoints": {
    "list_notebooks": {
      "path": "api/notebooks",
      "method": "GET",
      "query": {},
      "body": null,
      "root_keys": ["notebooks"],
      "timeout_seconds": 30.0
    },
    "get_notebook": {
      "path": "api/notebooks/{notebook_id}",
      "method": "GET"
    },
    "list_sources": {
      "path": "api/notebooks/{notebook_id}/sources",
      "method": "GET",
      "root_keys": ["sources"]
    },
    "list_artifacts": {
      "path": "api/notebooks/{notebook_id}/artifacts",
      "method": "GET",
      "root_keys": ["artifacts"]
    },
    "get_artifact": {
      "path": "api/notebooks/{notebook_id}/artifacts/{artifact_id}",
      "method": "GET"
    }
  }
}
```

Rules:

- `endpoints.list_notebooks` is required.
- other endpoint entries are optional, but missing entries may limit connector capabilities.
- `path` may use `{notebook_id}` and `{artifact_id}` placeholders where applicable.
- `method` defaults to `GET` if omitted.
- `query`, `body`, `root_keys`, and `timeout_seconds` are optional.
- the connector should load this file from the default path before falling back to ad hoc CLI arguments.
- the default template is a guess, not a guarantee; operator endpoint discovery may still be required when NotebookLM drifts.

## Auth Runtime State

Expected auth runtime files under `<data_root>/auth/`:

- `session.json`
- `notebooklm_endpoints.json`
- optional browser profile data under `browser-profile/`

Rules:

- auth runtime state is local-only and must remain ignored by git
- session storage currently uses Windows DPAPI when available
- when strong OS-backed encryption is unavailable, the runtime falls back to permission-hardened plaintext and must warn the operator
- endpoint config files must not be used as secret stores

## Transport Defaults

- host default: `127.0.0.1`
- port default: `8000`
- transport default: `streamable-http`

Current v1 server behavior:

- the default runtime backend is SQLite-backed local retrieval over the canonical store
- `--null-backend` and `--demo-data` are operator validation modes, not production modes
- the server endpoint path defaults to `/mcp`

## Configuration Rules

- Do not store secrets in `.env.example`.
- Do not hardcode local machine-specific absolute paths.
- If a subsystem needs additional configuration keys that other terminals must know about, Terminal 1 must add them here first.
