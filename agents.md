<proposed_plan>
# Six-Codex Parallel Build Plan

## Summary

Use six Codex instances with **disjoint ownership** and a shared contract:

- One agent owns **architecture/contracts**
- One owns **NotebookLM auth + connector**
- One owns **sync/normalization/persistence**
- One owns **indexing/retrieval**
- One owns **MCP server + tool schemas**
- One owns **test harness/docs/integration validation**

All agents should work in parallel, but they must treat the **contracts agent** as the source of truth for cross-cutting interfaces. If an agent hits ambiguity that would change interfaces, behavior, data shape, or deployment assumptions, the rule is: **ASK user and STOP**.

## Shared Instructions For Every Codex Terminal

Paste this into every terminal before the role-specific instructions.

### Global mission
Build a personal/self-hosted, open-source MCP server that syncs NotebookLM content into a local research index and exposes it to ChatGPT and Claude via MCP, with exact `search`/`fetch` compatibility for ChatGPT deep research and read-only research tools for Claude.

### Global technical requirements
- Target a **personal/self-hosted** v1.
- Support **private authenticated NotebookLM sync**.
- Assume NotebookLM integration is via **undocumented internal endpoints**, with **Playwright fallback** for auth/bootstrap/recovery.
- MCP server must support **remote HTTP** use for ChatGPT/Anthropic.
- ChatGPT compatibility requires exact read-only MCP tools:
  - `search(query: string)`
  - `fetch(id: string)`
- Research data must be persisted locally in a deterministic, inspectable form.
- Default server posture is **read-only** for research tools.
- If you define APIs, types, tables, or JSON shapes used by other agents, keep them explicit and stable.

### Global definition of done
Your task is done only when:
- The assigned deliverable is implemented or fully specified in-repo.
- Cross-agent interfaces you touch are documented clearly.
- Tests or validation for your owned area exist, or you explain exactly what remains blocked.
- You do not leave another agent needing to guess your schema or behavior.

### Global constraints
- Do not overwrite or refactor files owned by another agent unless the shared contract explicitly says you should.
- Do not make product decisions outside your owned scope.
- Prefer additive changes over broad rewrites.
- Keep outputs deterministic and git-friendly.
- If a cross-agent dependency is missing, stub to the agreed contract or stop and ask.

### Must do
- Respect ownership boundaries.
- Document any public interface you introduce.
- Leave TODOs only if they are precise and externally unblockable.
- Validate assumptions against the repo and existing shared contracts before coding.
- If confused by ambiguity that changes implementation meaningfully: **ASK user and STOP**.

### Must not do
- Do not silently invent interfaces used by other agents.
- Do not change shared schemas unilaterally.
- Do not build features outside your assignment.
- Do not implement live NotebookLM chat unless your task explicitly says so.
- Do not add write-capable MCP research tools by default.

### Confusion protocol
If any of the following occurs, **ASK user and STOP**:
- Two plausible interface designs exist and the choice affects other agents.
- The NotebookLM behavior/API you need is unclear and you cannot confirm from code/docs.
- A file appears owned by another terminal and your change would conflict.
- A requirement seems inconsistent with ChatGPT/Anthropic MCP constraints.
- You need to change a previously agreed contract.

## Terminal 1: Contracts And Repo Skeleton

### Mission
Own the top-level architecture, repository layout, shared types, interface contracts, and decision records. Other agents depend on you for shape and boundaries.

### Deliverables
- Repository skeleton for the project.
- ADR-style docs for major decisions.
- Shared contract docs for:
  - canonical document model
  - notebook/source/artifact normalized model
  - sync pipeline stages
  - MCP public tool schemas beyond `search`/`fetch`
  - ownership map for directories/files
- Base config patterns for env vars and local storage paths.

### Technical requirements
- Define the canonical fetchable unit, likely `DocumentRecord`.
- Define stable IDs for:
  - notebook
  - source
  - artifact
  - document
  - chunk
- Define canonical URL rules.
- Define on-disk layout and SQLite ownership at a high level.
- Define which modules are internal-only vs shared.
- Create a `docs/` area with contract files that the other agents can implement against.

### Definition of done
- Another engineer can implement each subsystem without guessing type shapes.
- Shared contracts are explicit enough that no other terminal needs to invent schema.
- Directory ownership is clear and minimizes merge conflicts.
- Any unresolved decision is surfaced clearly as blocked, not buried.

### Constraints
- Do not deeply implement subsystem logic owned by other terminals.
- Keep contract docs short, precise, and decision-complete.
- If you need to pick between valid alternatives, prefer the simplest option that preserves later extensibility.

### Must do
- Publish a file ownership map.
- Publish exact JSON/type examples for normalized notebook/source/artifact/document records.
- Publish naming conventions and ID derivation rules.
- Publish required env/config keys.

### Must not do
- Do not implement NotebookLM API calls.
- Do not implement retrieval ranking.
- Do not implement MCP transport/server details beyond interface contracts.

### Ask user and stop when
- You cannot choose a canonical URL strategy without product input.
- You find a major contract conflict with the ChatGPT `search`/`fetch` compatibility requirement.

## Terminal 2: NotebookLM Auth And Connector

### Mission
Own NotebookLM access: authenticated session handling, connector abstraction, internal API client, and Playwright fallback for login/bootstrap/recovery.

### Deliverables
- Connector interface for NotebookLM access.
- Internal API client implementation.
- Auth/session management:
  - cookie loading/storage
  - token/session refresh
  - login bootstrap flow
- Optional Playwright fallback path for auth recovery and possibly artifact access.
- CLI or scripts for `login` and `doctor`.

### Technical requirements
- Primary integration path: authenticated internal HTTP requests.
- Fallback path: Playwright for:
  - first-time login
  - cookie refresh
  - break-glass recovery
- Session persistence must be local and isolated.
- No hardcoded credentials.
- Errors must distinguish:
  - auth expired
  - endpoint drift
  - permission denied
  - unsupported artifact/data shape

### Definition of done
- A caller can authenticate, check health, and list/fetch raw NotebookLM entities through a stable connector API.
- Auth state survives restarts.
- Failure modes are explicit and actionable.
- No downstream module needs to know whether data came from internal API or Playwright fallback.

### Constraints
- Keep this layer raw and transport-focused.
- Do not normalize into canonical local documents here.
- Do not own indexing or MCP logic.
- Be careful with anything that may violate terms or rely on fragile selectors unless necessary.

### Must do
- Define a clean connector interface consumed by sync code.
- Include a doctor/debug path that verifies session viability.
- Capture raw payload fixtures when useful for tests, scrub secrets.
- Prefer deterministic, typed parsing around the raw responses.

### Must not do
- Do not expose secrets in logs.
- Do not mix canonical persistence logic into auth/client code.
- Do not assume DOM scraping is the main path if internal API access works.
- Do not implement NotebookLM chat/query tools unless specifically required.

### Ask user and stop when
- Internal API and DOM paths disagree about what data is authoritative.
- You need to choose a credential storage mechanism with meaningful security tradeoffs not already covered.
- A required NotebookLM artifact appears inaccessible without a riskier approach than expected.

## Terminal 3: Sync, Normalization, And Local Persistence

### Mission
Own the sync engine: pull raw NotebookLM data from the connector, normalize it into the canonical model, and persist it to disk and SQLite.

### Deliverables
- Sync orchestration pipeline.
- Raw-to-canonical normalization logic.
- Deterministic file snapshot writer.
- SQLite schema and persistence code for notebooks, sources, artifacts, documents, chunks, and sync runs.
- CLI commands for:
  - `sync notebook <id>`
  - `sync all`
  - sync status inspection

### Technical requirements
- Inputs come only from the shared connector interface.
- Outputs must include:
  - on-disk snapshots
  - normalized DB rows
  - derived fetchable documents
- Sync must be idempotent.
- Re-sync must update changed records predictably.
- Preserve provenance:
  - original NotebookLM notebook/source/artifact identifiers
  - source URLs
  - sync timestamps
  - artifact type
- Handle partial sync failures gracefully.

### Definition of done
- A notebook can be synced end-to-end into local storage.
- Re-running sync does not create duplicate logical records.
- Downstream retrieval and MCP code can rely on the stored canonical data without touching NotebookLM directly.
- Persistence and snapshot outputs are deterministic enough for debugging and git inspection.

### Constraints
- Do not own auth or raw NotebookLM access.
- Do not own ranking/search logic.
- Do not own external MCP tool exposure.
- Respect contract definitions from Terminal 1.

### Must do
- Keep a clear boundary between raw payloads and canonical records.
- Track sync runs and error states.
- Write migration-safe schema initialization if possible.
- Make artifact/document derivation explicit rather than implicit.

### Must not do
- Do not invent canonical fields outside the shared contract.
- Do not bury raw NotebookLM identifiers.
- Do not directly call Playwright or raw HTTP if the connector abstraction already exists.

### Ask user and stop when
- A NotebookLM entity does not map cleanly to the agreed canonical document model.
- Multiple reasonable dedupe/update strategies exist and would change fetch/search behavior.

## Terminal 4: Indexing And Retrieval

### Mission
Own the local search system: chunking, FTS, embeddings, hybrid ranking, and retrieval APIs over canonical documents.

### Deliverables
- Chunking/index build pipeline.
- SQLite FTS setup.
- Embedding pipeline abstraction and default backend.
- Hybrid retrieval/rank fusion implementation.
- Search service used by MCP `search` and notebook-scoped search tools.
- Reindex command.

### Technical requirements
- Index only canonical persisted data, not live NotebookLM data.
- Support:
  - global search
  - notebook-scoped search
  - optional filtering by document kind
- Retrieval should be explainable enough for debugging:
  - source of hit
  - lexical vs semantic contribution
  - final rank
- Make embedding backend configurable.
- Default to a simple, practical local-first approach.

### Definition of done
- Search returns relevant results over a realistic multi-source notebook dataset.
- Reindex works incrementally or fully, and the failure path is understandable.
- MCP layer can call a stable search service without caring about rank internals.
- Retrieval quality is testable with fixtures.

### Constraints
- Do not own MCP schema or transport.
- Do not own SQLite canonical schema except what is needed for indexing tables.
- Avoid overengineering rerankers or distributed infrastructure for v1.

### Must do
- Build both lexical and semantic search.
- Provide a stable internal result shape with IDs, scores, and provenance.
- Keep chunking policy explicit and documented.
- Add tests around ranking behavior and filtering.

### Must not do
- Do not return ad hoc result types that bypass canonical document IDs.
- Do not depend on live NotebookLM availability.
- Do not make the embedding provider mandatory if a no-op/test path is needed.

### Ask user and stop when
- Embedding backend choice materially changes deployment assumptions and no default is acceptable.
- Chunking strategy ambiguity would change `fetch`/citation behavior significantly.

## Terminal 5: MCP Server And Public Tool Surface

### Mission
Own the MCP server, transports, tool registration, ChatGPT-compatible `search`/`fetch`, and the read-only companion research tools.

### Deliverables
- MCP server implementation.
- Remote HTTP transport setup.
- Exact `search` and `fetch` tools for ChatGPT compatibility.
- Read-only companion tools:
  - `list_notebooks`
  - `get_notebook`
  - `list_notebook_documents`
  - `search_notebook`
  - `get_sync_status`
- Tool descriptions/annotations optimized for model tool selection.
- Local dev and remote-personal run modes.

### Technical requirements
- `search` and `fetch` must match ChatGPT compatibility requirements exactly.
- Read-only tools must be marked with `readOnlyHint: true`.
- Responses must preserve canonical URLs for citations.
- Server should support **Streamable HTTP** first; add **SSE** if feasible without destabilizing v1.
- Separate internal service interfaces from MCP adapter code.

### Definition of done
- MCP Inspector or equivalent can list and call tools successfully.
- `search` and `fetch` are schema-compatible with ChatGPT deep research expectations.
- Claude-compatible remote MCP usage is possible over HTTPS.
- Tool descriptions are good enough that the model can select the right tool without heavy prompting hacks.

### Constraints
- Do not own retrieval logic internals.
- Do not own sync logic.
- Keep the toolset read-only by default.
- Avoid exposing too many tools if they dilute model selection quality.

### Must do
- Implement exact ChatGPT-compatible wrappers for `search`/`fetch`.
- Use internal services for data access rather than embedding logic in tool handlers.
- Add explicit annotations and concise tool descriptions.
- Keep MCP adapter code thin and testable.

### Must not do
- Do not expose write/admin tools in the default research toolset.
- Do not deviate from the expected `search`/`fetch` response shape.
- Do not invent citation URLs that are not stable/canonical per contract.

### Ask user and stop when
- A proposed public tool shape conflicts with ChatGPT deep research compatibility.
- Remote transport/auth choices require product/security decisions beyond the agreed v1 scope.

## Terminal 6: Tests, Fixtures, Integration Validation, And Docs

### Mission
Own validation: test infrastructure, recorded fixtures, integration checks, runbooks, and operator documentation.

### Deliverables
- Test plan implemented in repo.
- Fixture strategy for NotebookLM raw payloads and normalized data.
- End-to-end validation path covering:
  - auth check
  - sync
  - reindex
  - MCP search/fetch
- Operator docs:
  - setup
  - login
  - sync
  - run server
  - known limitations
- Drift/risk docs for undocumented NotebookLM integration.

### Technical requirements
- Record test fixtures in a scrubbed form.
- Cover failure modes:
  - expired auth
  - partial sync
  - missing artifact
  - endpoint drift
  - empty search
- Validate ChatGPT/Claude compatibility where feasible.
- Keep docs honest about undocumented NotebookLM dependency and likely drift.

### Definition of done
- A new contributor can set up and understand the system from docs.
- The main happy path is testable without guessing commands.
- Risk areas and manual recovery steps are documented.
- Integration gaps are explicit rather than implied.

### Constraints
- Do not take ownership of subsystem implementation unless fixing small testability issues.
- Prefer fixtures and harnesses over fragile live-only tests.
- Keep docs practical, not promotional.

### Must do
- Build a fixture strategy that does not leak secrets.
- Write a setup/runbook for six-terminal collaboration if useful.
- Capture known limitations clearly.
- Document the expected behavior of each CLI/admin flow.

### Must not do
- Do not conceal untested areas.
- Do not write docs that assume hidden tribal knowledge.
- Do not create fake guarantees around NotebookLM stability.

### Ask user and stop when
- Live integration validation would require unsafe credential handling.
- You cannot truthfully document behavior because another terminal has not finalized the interface.

## Coordination Rules Between Terminals

- Terminal 1 goes first on contracts, then everyone else builds against those contracts.
- Terminal 2 and Terminal 3 must agree on the connector interface before broad implementation.
- Terminal 3 and Terminal 4 must agree on canonical document/chunk boundaries before indexing is finalized.
- Terminal 4 and Terminal 5 must agree on the internal search result shape before MCP adapters are finalized.
- Terminal 6 should start early with fixture/runbook scaffolding, then continuously validate others’ outputs.

If any terminal needs to violate ownership or alter a shared contract, the rule remains:

**ASK user and STOP.**

## Suggested Ownership Layout

- Terminal 1: `docs/`, shared `schemas/` or `contracts/`, repo skeleton, ADRs
- Terminal 2: `src/notebooklm_client/`, `src/auth/`, login/doctor CLI pieces
- Terminal 3: `src/sync/`, `src/store/`, migrations, snapshot persistence
- Terminal 4: `src/index/`, `src/retrieval/`
- Terminal 5: `src/mcp_server/`, public tool adapters, run server entrypoints
- Terminal 6: `tests/`, `fixtures/`, `docs/setup*`, `docs/runbook*`, validation scripts

## Recommended First Message To Every Agent

Use this exact opener in each terminal:

“Read the shared project contracts first. You own only the scope in this terminal’s instruction block. Do not make cross-agent schema decisions. If anything is ambiguous in a way that changes interfaces, behavior, or deployment assumptions, ask the user and stop.”

## Launch Sequence

1. Start Terminal 1 first and have it produce the initial contract files and ownership map.
2. Once those contracts exist, start Terminals 2 through 6 in parallel.
3. Require every terminal to read Terminal 1’s contract docs before editing code.
4. If Terminal 1 updates a shared contract later, all affected terminals must re-read it before continuing.
5. If two terminals need the same file, stop one and reassign ownership rather than letting both edit it.

## What To Paste Into Each Terminal

Paste the shared instructions first, then append exactly one of the six terminal blocks above. If the agent asks a question caused by ambiguity in interfaces, behavior, or scope, answer it centrally and then propagate the decision to all affected terminals before letting them continue.
</proposed_plan>
