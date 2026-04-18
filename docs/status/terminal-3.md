current scope: sync orchestration, normalization, deterministic snapshots, SQLite persistence, persisted document/chunk adapters, and sync-connected chunk persistence/reindex flow
files owned: src/sync/**, src/store/**, docs/status/terminal-3.md
current blocker: terminal 2 has not published a connector implementation yet, so full end-to-end sync still expects an injected connector with `fetch_notebook(notebook_id)`
last meaningful change: connected chunk generation into notebook sync, added persisted chunk/document repository adapters plus a persisted-chunk reindex helper, and added Terminal 3 sync correctness coverage for normalization, idempotent re-sync, failure recording, and snapshot determinism
