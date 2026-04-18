current scope: sync orchestration, normalization, deterministic snapshots, and SQLite persistence for canonical records
files owned: src/sync/**, src/store/**, docs/status/terminal-3.md
current blocker: terminal 2 has not published a connector implementation yet, so sync currently expects an injected connector with `fetch_notebook(notebook_id)`
last meaningful change: added the initial Terminal 3 subsystem for canonical record persistence, replace-in-place notebook syncs, sync-run failure tracking, and snapshot writing
