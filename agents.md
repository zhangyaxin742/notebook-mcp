# AGENTS.md

This file is the durable, repository-level instruction file for agentic coding tools working in this repo.

It is not a brainstorming note and not a one-off planning artifact. Treat it as the operating contract for Codex, Claude Code, Copilot agents, and similar tools.

## Purpose

Use this file for rules that should hold every time an agent works in this repository:

- project goals
- architecture defaults
- coordination rules
- testing and review expectations
- file ownership
- stop conditions

If you discover a recurring mistake or ambiguity, fix this file so the correction persists.

## Precedence

Instruction priority is:

1. Direct user request
2. This file
3. Agent defaults and assumptions

If two instructions conflict and the conflict is not clearly resolved by this order, ask the user and stop.

## Project Goal

Build a personal, self-hosted, open-source MCP server that syncs NotebookLM content into a local research index and exposes it to ChatGPT and Claude.

NotebookLM is the ingestion and artifact-generation layer, not the main reasoning engine. The system should sync NotebookLM notebooks, sources, summaries, and generated artifacts into a local canonical store, then expose that material through MCP for deeper analysis.

## Non-Negotiable Product Constraints

- v1 is personal/self-hosted, not multi-tenant SaaS.
- v1 must support private authenticated NotebookLM sync.
- Assume NotebookLM has no stable public API for this use case.
- Primary NotebookLM integration path is authenticated internal HTTP calls.
- Playwright is the fallback for login bootstrap, cookie refresh, and break-glass recovery.
- The MCP server must support remote HTTP use for ChatGPT and Claude.
- ChatGPT compatibility requires exact read-only `search(query: string)` and `fetch(id: string)` tools.
- The MCP server is read-only by default for research flows.
- Do not build live NotebookLM chat/query as part of the default v1 research path.
- Persist synced data locally in deterministic, inspectable formats.
- Preserve provenance and canonical URLs for citations.

## Technical Defaults

Use these defaults unless the user explicitly changes them:

- Language: Python
- MCP framework: FastMCP or equivalent Python MCP framework
- Local store: SQLite
- Lexical search: SQLite FTS5
- Semantic search: configurable embeddings backend, local-first by default
- Sync model: pull from NotebookLM into a canonical local store, then index locally
- Transport priority: Streamable HTTP first, SSE if feasible without destabilizing v1

## Global Engineering Rules

- Make minimum viable edits. Prefer line edits over rewrites.
- Do not overwrite another agent's edits.
- Do not change shared contracts unilaterally.
- Do not invent cross-agent schemas silently.
- Do not hardcode secrets, tokens, cookies, or local absolute user paths.
- Never commit sensitive auth data or raw fixtures containing secrets.
- Prefer additive changes over broad refactors.
- Keep outputs deterministic and git-friendly.
- If a file is owned by another terminal, do not touch it without user approval.

## Quality Bar

Before yielding control, each agent must do all of the following for its owned scope:

- check the requested work against the exact action item it owns
- add or update tests when the change justifies it
- run the most relevant checks available
- review its own diff for regressions, risky assumptions, and scope creep
- document any remaining blocker or untested path explicitly

If a test or validation step cannot be run, say exactly why.

## Prompting And Orchestration Standards

These are the standards this file should follow and that agents should preserve when editing it:

- Keep instructions specific, actionable, and scoped.
- Group related rules under short headings.
- Avoid conflicting instructions because agent behavior under conflict is non-deterministic.
- Keep repository-wide rules here; move narrow rules closer to the code they govern.
- If this file grows too broad, split narrower guidance into nested `AGENTS.md` files or dedicated docs referenced from here.
- Prefer stable operating instructions over temporary planning prose.

## Multi-Terminal Orchestration Model

This repository is designed for six parallel terminals, each with a disjoint ownership area.

Every agent must know which terminal number it is. If the user has not specified the terminal number for the current session, ask once and stop.

Only follow the section for your own terminal number. Ignore all other terminal-specific implementation instructions except the shared rules in this file.

## Readiness Gate

Terminal 1 must go first.

Terminals 2 through 6 must not begin implementation until all of these files exist:

- `docs/contracts/overview.md`
- `docs/contracts/data-model.md`
- `docs/contracts/tool-contracts.md`
- `docs/contracts/ownership.md`

If any of these files do not exist, or exist but are obviously incomplete, ask the user and stop.

## Cross-Agent Communication Protocol

Do not rely on chat memory between terminals.

Shared coordination happens through repository files:

- `docs/contracts/` for canonical interfaces and ownership
- `docs/status/terminal-1.md` through `docs/status/terminal-6.md` for progress and blockers

Each terminal owns exactly one status file:

- Terminal 1 owns `docs/status/terminal-1.md`
- Terminal 2 owns `docs/status/terminal-2.md`
- Terminal 3 owns `docs/status/terminal-3.md`
- Terminal 4 owns `docs/status/terminal-4.md`
- Terminal 5 owns `docs/status/terminal-5.md`
- Terminal 6 owns `docs/status/terminal-6.md`

Status files should stay short and factual:

- current scope
- files owned
- current blocker
- last meaningful change

If a blocker changes interfaces, behavior, or deployment assumptions, ask the user and stop. Do not wait for another terminal to resolve it silently.

## Shared Critical Files

These files are shared-critical and must not be edited casually:

- `agents.md`
- `CODEX.md`
- top-level dependency manifests
- lockfiles
- `.gitignore`
- `.env.example`
- `docs/contracts/*`

Only Terminal 1 may edit shared-critical files by default.

If another terminal needs one of these files changed, it must ask the user and stop unless the user has already delegated that exact change.

## Security Rules

- Never log raw auth cookies, bearer tokens, session headers, or CSRF tokens.
- Never commit browser session state.
- Scrub fixtures before saving them.
- Treat undocumented NotebookLM endpoints as unstable and potentially sensitive.
- If a safer and a riskier data-access path both exist, prefer the safer one.

## Stop Conditions

Ask the user and stop immediately if any of the following happens:

- two plausible interface designs exist and the choice affects other terminals
- a required contract file is missing or contradictory
- you need to edit a file owned by another terminal
- you need to change a shared contract
- NotebookLM behavior is unclear and cannot be confirmed from code or documentation
- a transport, auth, or storage decision would materially change deployment assumptions
- a requested change appears to conflict with ChatGPT or Claude MCP requirements

## Whole-Project Definition Of Done

The project is done only when all of the following are true:

- NotebookLM content can be synced into a canonical local store
- canonical data can be searched locally with lexical and semantic retrieval
- MCP `search` and `fetch` are compatible with ChatGPT expectations
- Claude and ChatGPT can use the server as a read-only research connector
- provenance and canonical citation URLs are preserved
- setup, sync, reindex, and serve flows are documented
- tests or fixture-based validations exist for the core flows

## Launch Protocol

1. Start Terminal 1 first.
2. Terminal 1 creates the contract docs and ownership map.
3. Only after that, start Terminals 2 through 6.
4. Every terminal must read `docs/contracts/ownership.md` before touching code.
5. If Terminal 1 updates a contract later, affected terminals must re-read it before continuing.
6. If two terminals would touch the same file, stop one terminal and ask the user to resolve ownership.

## What Every Terminal Should Do First

At the start of the session:

1. Identify your terminal number.
2. Read this file.
3. Read the required contract docs.
4. Read your owned status file if it exists.
5. Summarize your owned scope before making edits.

## Terminal 1: Contracts And Shared Skeleton

Only follow this section if the user has assigned you Terminal 1.

### Mission

Own the top-level architecture, repository skeleton, shared contracts, shared-critical files, and ownership map.

### Owned Paths

- `docs/contracts/**`
- `docs/status/terminal-1.md`
- shared-critical files listed above
- empty directory scaffolding for owned subsystem directories, if needed

### Deliverables

- `docs/contracts/overview.md`
- `docs/contracts/data-model.md`
- `docs/contracts/tool-contracts.md`
- `docs/contracts/ownership.md`
- initial repo skeleton directories
- any shared env/config contract docs needed for the other terminals to proceed

### Must Do

- define the canonical fetchable document model
- define stable IDs for notebook, source, artifact, document, and chunk
- define canonical URL rules
- define owned paths for each terminal
- define which shared files are off-limits
- keep contracts explicit enough that other terminals do not guess

### Must Not Do

- do not implement NotebookLM API calls
- do not implement retrieval logic
- do not implement MCP handlers
- do not leave ownership ambiguous

### Definition Of Done

Terminal 1 is done when the other terminals can implement safely without inventing shared schemas.

## Terminal 2: NotebookLM Auth And Connector

Only follow this section if the user has assigned you Terminal 2.

### Mission

Own NotebookLM session handling, raw connector abstraction, internal API client, and Playwright fallback for auth and recovery.

### Owned Paths

- `src/notebooklm_client/**`
- `src/auth/**`
- auth-related CLI entrypoints that are not shared-critical
- `docs/status/terminal-2.md`

### Must Do

- define a stable connector interface consumed by sync code
- implement auth/session loading and validation
- support login bootstrap and doctor flows
- distinguish auth-expired vs endpoint-drift vs unsupported-shape failures
- scrub any saved fixtures and logs

### Must Not Do

- do not normalize raw NotebookLM data into canonical local records here
- do not implement indexing or MCP logic
- do not expose secrets in logs
- do not make DOM scraping the primary path if internal API access works

### Definition Of Done

Terminal 2 is done when downstream code can call one raw connector interface without caring whether data came from internal HTTP or Playwright fallback.

## Terminal 3: Sync, Normalization, And Persistence

Only follow this section if the user has assigned you Terminal 3.

### Mission

Own the sync engine, normalization into canonical records, snapshot writing, and SQLite persistence.

### Owned Paths

- `src/sync/**`
- `src/store/**`
- persistence migrations and schema files outside shared-critical files
- `docs/status/terminal-3.md`

### Must Do

- consume only the shared connector interface
- write deterministic local snapshots
- persist notebooks, sources, artifacts, documents, chunks, and sync runs
- keep sync idempotent
- preserve provenance fields and source URLs
- make partial sync failures explicit

### Must Not Do

- do not call raw HTTP or Playwright directly if the connector abstraction exists
- do not invent canonical fields outside the contract
- do not bury raw NotebookLM identifiers

### Definition Of Done

Terminal 3 is done when a notebook can be synced end-to-end into canonical local storage and re-synced without duplicate logical records.

## Terminal 4: Indexing And Retrieval

Only follow this section if the user has assigned you Terminal 4.

### Mission

Own chunking, FTS, embeddings, hybrid ranking, and search services over canonical stored data.

### Owned Paths

- `src/index/**`
- `src/retrieval/**`
- `docs/status/terminal-4.md`

### Must Do

- index only canonical persisted data
- support global search and notebook-scoped search
- keep chunking policy explicit
- expose a stable internal search result shape with IDs, scores, and provenance
- add tests for ranking and filtering behavior where practical

### Must Not Do

- do not depend on live NotebookLM availability
- do not bypass canonical document IDs
- do not make the embedding backend impossible to swap

### Definition Of Done

Terminal 4 is done when retrieval works over realistic fixture data and the MCP layer can consume a stable internal search service.

## Terminal 5: MCP Server And Public Tool Surface

Only follow this section if the user has assigned you Terminal 5.

### Mission

Own the MCP server, transport setup, ChatGPT-compatible `search` and `fetch`, and the read-only companion tools.

### Owned Paths

- `src/mcp_server/**`
- server entrypoints not listed as shared-critical
- `docs/status/terminal-5.md`

### Must Do

- implement exact ChatGPT-compatible `search` and `fetch`
- preserve canonical URLs for citations
- mark read-only tools with `readOnlyHint: true`
- keep adapter code thin and use internal services rather than embedding logic in handlers
- support remote HTTP transport with Streamable HTTP first

### Must Not Do

- do not expose write/admin tools in the default research toolset
- do not deviate from the expected `search` and `fetch` shapes
- do not invent citation URLs

### Definition Of Done

Terminal 5 is done when the MCP server can list and call tools successfully and the public tool surface matches the contracts.

## Terminal 6: Tests, Fixtures, Validation, And Docs

Only follow this section if the user has assigned you Terminal 6.

### Mission

Own the test harness, scrubbed fixtures, integration validation, setup docs, and operator runbooks.

### Owned Paths

- `tests/**`
- `fixtures/**`
- `docs/setup*`
- `docs/runbook*`
- `docs/status/terminal-6.md`

### Must Do

- create a fixture strategy that does not leak secrets
- cover the main failure modes
- document setup, login, sync, reindex, and serve flows
- document known limitations and likely drift risks from undocumented NotebookLM integration
- make testing gaps explicit

### Must Not Do

- do not fabricate guarantees about NotebookLM stability
- do not hide untested paths
- do not require unsafe credential handling for baseline validation

### Definition Of Done

Terminal 6 is done when a new contributor can understand the setup and the core flows have a documented validation path.

## Recommended Verification Commands

If the necessary tooling exists, prefer these validation categories before yielding:

- unit tests for the owned subsystem
- type checks
- lint for changed files
- fixture-based integration tests

If no standard commands exist yet, document what you would run once they exist and why.

## Maintenance Guidance

Keep this file focused.

If rules become too narrow or too numerous:

- move subsystem-specific guidance closer to the subsystem
- split specialized instructions into nested `AGENTS.md` files
- keep only repository-wide rules here

Do not turn this file back into a planning transcript.
