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

What it does not cover yet:

- live NotebookLM authentication
- end-to-end sync execution
- indexing behavior
- MCP server transport behavior

Those areas depend on implementation owned by other terminals and should be added once those paths exist.
