# Test Harness

Terminal 6 owns the baseline validation harness in this repository.

The current harness is intentionally dependency-light:

```powershell
python -m unittest discover -s tests -v
```

What it covers today:

- fixture inventory integrity
- contract-aligned example record shape checks
- secret scrubbing checks for committed fixtures
- documentation coverage for setup and runbook requirements
- sync runtime behavior, including idempotence and failed-run recording
- retrieval runtime behavior, including chunking and hybrid search
- MCP protocol and HTTP transport smoke behavior
- import smoke checks across the main package surfaces

What it does not cover yet:

- live NotebookLM authentication
- real NotebookLM network integration against a live private account
- browser-driven Playwright login execution
- production deployment monitoring, backup, and rollback procedures

Those areas depend on implementation owned by other terminals and should be added once those paths exist.
