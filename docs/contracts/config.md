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
- `NOTEBOOK_MCP_EMBEDDING_BACKEND`
- `NOTEBOOK_MCP_EMBEDDING_MODEL`
- `NOTEBOOK_MCP_BROWSER_PROFILE_DIR`

## Transport Defaults

- host default: `127.0.0.1`
- port default: `8000`
- transport default: `streamable-http`

## Configuration Rules

- Do not store secrets in `.env.example`.
- Do not hardcode local machine-specific absolute paths.
- If a subsystem needs additional configuration keys that other terminals must know about, Terminal 1 must add them here first.
