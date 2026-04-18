# Terminal 4 Status

- current scope: chunking, lexical indexing, semantic indexing, and hybrid retrieval over canonical persisted documents
- files owned: `src/index/**`, `src/retrieval/**`, `docs/status/terminal-4.md`
- current blocker: waiting on Terminal 3 to provide the concrete persisted document repository adapter against the shared local store
- last meaningful change: added canonical retrieval models, an in-memory repository, explicit chunking policy, isolated SQLite FTS indexing, a swappable embedding backend, and a hybrid retrieval service
