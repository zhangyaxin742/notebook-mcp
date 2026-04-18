# Fixtures

This directory is owned by Terminal 6.

The fixtures here are for tests, documentation, and validation only. They are not shared runtime contracts and must not be treated as production payload guarantees.

## Redaction Rules

- Never store live cookies, bearer tokens, CSRF tokens, or browser session state.
- Replace sensitive values with placeholders such as `<redacted-header>` and `<redacted-path>`.
- Keep fixture text deterministic and diff-friendly.
- Prefer minimal examples that demonstrate a behavior without reproducing full raw NotebookLM responses.

## Layout

- `terminal6/manifest.json`: fixture inventory used by baseline tests
- `terminal6/canonical/`: contract-aligned example records
- `terminal6/failure-modes/`: scrubbed failure examples used by docs and tests

## Maintenance

If a future fixture needs new fields to match a shared contract, update the contract first through Terminal 1. Do not invent repository-wide schemas here.
