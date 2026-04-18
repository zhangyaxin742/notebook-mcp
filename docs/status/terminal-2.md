current scope: NotebookLM auth/session handling, protected local session storage, default endpoint config loading/bootstrap, internal HTTP client, Playwright fallback for auth/bootstrap/recovery, and offline connector validation
files owned: `src/auth/**`, `src/notebooklm_client/**`, `docs/status/terminal-2.md`
current blocker: endpoint discovery and the default endpoint template still need validation against a real authenticated NotebookLM session to confirm live endpoint correctness
last meaningful change: replaced plaintext session writes with protected storage, auto-bootstrapped the default local endpoint config path, and added offline connector tests for error classification and failover
