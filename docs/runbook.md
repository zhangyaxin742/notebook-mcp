# Operator Runbook

This runbook is owned by Terminal 6 and documents safe operator expectations for the v1 self-hosted workflow.

## Normal Operating Sequence

The intended sequence is:

1. establish authenticated access through the Terminal 2 login/bootstrap flow
2. run a sync through the Terminal 3 sync flow
3. rebuild retrieval indexes through the Terminal 4 reindex flow when needed
4. serve read-only MCP tools through the Terminal 5 server flow

As of 2026-04-18, these runtime flows are documented targets rather than implemented commands in this repository snapshot.

## Handling Auth Expired

Symptoms:

- a login page or auth error appears where authenticated JSON is expected
- session validation fails before notebook enumeration

Response:

1. re-run the login bootstrap or doctor path
2. verify session state only in ignored local storage
3. retry the sync after validation passes

Safety rule:

- do not paste raw cookies or bearer tokens into shell history, tests, fixtures, issues, or docs

## Handling Endpoint Drift

Symptoms:

- an undocumented NotebookLM endpoint starts returning a different status or payload shape
- a previously valid connector request no longer produces the expected data envelope

Response:

1. capture a minimal scrubbed repro
2. compare it against the committed failure-mode fixture examples
3. stop for user review if the fix would change shared contracts or deployment assumptions

Risk note:

- undocumented endpoints can drift without notice; no stability guarantee should be assumed

## Handling Unsupported Shape

Symptoms:

- the response is still JSON but required identifiers or collections are missing
- downstream normalization would need to guess at a new shape

Response:

1. fail closed
2. store only a scrubbed diagnostic sample if needed
3. update parsing logic only after the new shape is understood and contract-compatible

## Handling Partial Sync

Symptoms:

- some records persist successfully while the notebook run still reports failure
- local data exists, but the snapshot or sync status is incomplete

Response:

1. inspect the recorded sync status
2. correct the upstream failure
3. re-run sync and confirm idempotent behavior

Operator expectation:

- partial sync must be explicit; silent success is a defect

## Handling Not Found

Symptoms:

- `fetch` receives a syntactically valid canonical document ID that is absent locally

Response:

1. confirm whether the document should have been produced by sync
2. re-run sync if the origin data is expected to exist
3. if the record is still absent, investigate persistence or normalization gaps

Public behavior expectation:

- the MCP surface should return a clear not found error without leaking internal request details

## Fixture Strategy

- use only scrubbed fixtures under `fixtures/`
- prefer compact examples over full raw captures
- include redaction placeholders where sensitive material would normally exist
- do not commit browser profiles, exported cookies, or live auth headers

## Validation Path

Available now:

```powershell
python -m unittest discover -s tests -v
```

Expected later, once runtime code exists:

- auth bootstrap validation
- fixture-based sync validation
- retrieval validation over canonical data
- MCP `search` and `fetch` validation over remote HTTP

## Limitations And Drift Risk

- NotebookLM integration is based on undocumented behavior and may change without notice.
- This repository snapshot does not yet contain the runtime command implementations for login, sync, reindex, or serve.
- Current validation is mostly static and contract-driven until the other terminal-owned subsystems land.

## Testing Gaps

- no live auth validation is possible from the current repository state
- no end-to-end sync test exists yet
- no retrieval ranking test exists yet
- no MCP transport smoke test exists yet

These gaps are intentional to avoid inventing behavior before the owning terminals implement their subsystems.
