current scope: NotebookLM auth/session handling, raw connector abstraction, internal HTTP client, and Playwright fallback for auth/bootstrap/recovery
files owned: `src/auth/**`, `src/notebooklm_client/**`, `docs/status/terminal-2.md`
current blocker: actual NotebookLM internal endpoint paths are not yet wired into shared runtime configuration, so doctor/probe flows require explicit endpoint definitions at call time
last meaningful change: added the Terminal 2 auth/session package, HTTP-first raw connector, Playwright-backed recovery path, redaction helpers, and status tracking
