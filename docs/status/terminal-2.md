current scope: NotebookLM auth/session handling, raw connector abstraction, internal HTTP client, and Playwright fallback for auth/bootstrap/recovery
files owned: `src/auth/**`, `src/notebooklm_client/**`, `docs/status/terminal-2.md`
current blocker: real NotebookLM internal endpoint values still need to be captured from an authenticated browser session and written to the local endpoint config file
last meaningful change: added shared endpoint-config contract support plus a file-based loader so auth and connector flows can read one local NotebookLM endpoint config instead of repeated CLI path flags
