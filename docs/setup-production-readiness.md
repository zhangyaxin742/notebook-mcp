# Production Readiness Checklist

This checklist is owned by Terminal 6. Its purpose is to tell an operator whether the repository is still in prototype mode or is ready for a real private deployment posture.

Use these rules conservatively:

- if any item under the target mode is unknown, treat it as not ready
- passing the current test suite is necessary but not sufficient for real deployment mode
- undocumented NotebookLM behavior remains a standing drift risk even when every checklist item passes

## Mode Classification

You are in prototype mode if any of the following are true:

- you are using demo data or the null backend
- auth is not exercised against a real private NotebookLM account
- sync has not been validated against real private notebook data
- the server is reachable only for local experimentation and not configured for intentional self-hosted use
- bearer auth, origin allowlisting, and operational secrets handling are not configured for remote exposure

You may treat the system as real deployment mode only when the relevant readiness section below is fully satisfied for the way you intend to run it.

## Local-Dev Readiness

Local-dev readiness means the repository is usable for safe local engineering work on the same machine, usually with `auth_mode=local-dev`.

Required criteria:

- `python -m unittest discover -s tests -v` passes locally
- canonical local storage paths resolve under the configured data directory
- sync writes deterministic snapshots and SQLite state without duplicate logical records
- retrieval returns canonical document IDs and canonical URLs from persisted local data
- MCP `search` and `fetch` behave correctly over the local Streamable HTTP endpoint
- no committed fixtures, docs, or logs contain cookies, bearer tokens, or CSRF material
- the operator understands that local-dev mode accepts only loopback clients and is not a remote security boundary

Do not classify local-dev readiness as private deployment readiness just because the tests pass. Local-dev readiness is still a development posture.

## Private Self-Hosted Readiness

Private self-hosted readiness means one operator can run the system for real personal use on trusted infrastructure, without exposing it broadly to the public internet.

Required criteria:

- every local-dev readiness item passes
- login bootstrap and doctor flows have been exercised successfully against a real private NotebookLM account
- session storage stays in ignored local paths and never requires manual cookie export into repo files
- at least one full sync against real notebook data completes and can be repeated idempotently
- stored notebook, source, artifact, document, and chunk records preserve provenance and canonical URLs
- retrieval is validated against real synced data, not only demo fixtures
- the operator can detect and triage auth expired, endpoint drift, unsupported shape, partial sync, and not found failures
- local backup and restore expectations for the SQLite database and snapshots are defined for the host running the service
- the operator is intentionally keeping access private to trusted machines, VPN, or equivalent private network controls

If any of those items are missing, the system is still effectively prototype mode for private self-hosted use.

## Remote-Exposed Readiness

Remote-exposed readiness means the MCP endpoint is intentionally reachable from outside the local machine, including across a home lab, VPS, tunnel, reverse proxy, or the public internet.

Required criteria:

- every private self-hosted readiness item passes
- the server is not running in `local-dev` auth mode for remote traffic
- bearer auth is enabled with a strong secret managed outside the repository
- allowed origins are explicitly configured for the remote browser or client surfaces that need access
- transport behavior has been validated end to end with the actual remote exposure path, not only direct loopback requests
- logs, reverse proxy headers, and monitoring do not leak auth credentials or notebook content unexpectedly
- network exposure is intentional and documented, including host, port, TLS termination, and firewall posture
- the operator has a credential rotation path for bearer tokens and any NotebookLM session refresh workflow
- failure handling is documented for endpoint drift and auth expiry without requiring unsafe debugging practices

Treat remote-exposed readiness as failed if the deployment depends on ad hoc port forwarding, shared bearer tokens in shell history, or browser origins that are effectively wildcarded.

## Quick Decision Rules

Use this short classification if you need an immediate answer:

- prototype mode: tests may pass, but real private NotebookLM auth or real sync validation has not been completed
- local-dev ready: safe for engineering on the same machine, not for intentional remote use
- private self-hosted ready: usable for one operator on trusted private infrastructure after real account validation
- remote-exposed ready: usable over intentional remote exposure only after bearer auth, allowed origins, and operational controls are fully validated

## Evidence To Keep

Keep the following evidence outside the repository or in scrubbed notes:

- date of the last successful real login bootstrap check
- date of the last successful real sync and re-sync validation
- confirmation that bearer auth and allowed origins match the intended deployment surface
- confirmation that backup, restore, and credential rotation steps are known to the operator

If you cannot produce that evidence, default back to prototype mode.
