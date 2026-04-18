from __future__ import annotations

import http.client
import json
import threading
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

from src.store.models import (
    DocumentRecord,
    NormalizedNotebookSnapshot,
    NotebookRecord,
    SyncRunRecord,
    content_sha256,
)
from src.store.settings import StorePaths
from src.store.sqlite_store import SQLiteStore

from .backend import SQLiteResearchBackend
from .http import McpHttpServer, McpRequestHandler, ServerConfig
from .protocol import McpProtocolServer


ACCEPT_POST = "application/json, text/event-stream"
ACCEPT_GET = "text/event-stream"


def _json_request(
    port: int,
    method: str,
    body: dict[str, object] | None,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], object | None]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    payload = json.dumps(body) if body is not None else None
    request_headers = dict(headers or {})
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    connection.request(method, "/mcp", body=payload, headers=request_headers)
    response = connection.getresponse()
    raw_body = response.read()
    normalized_headers = {key: value for key, value in response.getheaders()}
    parsed_body = json.loads(raw_body) if raw_body else None
    connection.close()
    return response.status, normalized_headers, parsed_body


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _seed_store(root: Path) -> StorePaths:
    paths = StorePaths(
        data_dir=root,
        db_path=root / "db" / "notebook_mcp.sqlite3",
        snapshots_dir=root / "snapshots",
    )
    store = SQLiteStore(paths)
    store.initialize()

    notebook_id = "nlm:notebook:abc123"
    document_text = "NotebookLM-generated source summary about alignment research."
    snapshot = NormalizedNotebookSnapshot(
        notebook=NotebookRecord(
            id=notebook_id,
            origin="notebooklm",
            raw_id="abc123",
            title="AI Safety Research",
            url="https://notebooklm.google.com/notebook/abc123",
            source_count=1,
            artifact_count=0,
            last_synced_at="2026-04-18T20:00:00Z",
            metadata={"share_mode": "private"},
        ),
        sources=(),
        artifacts=(),
        documents=(
            DocumentRecord(
                id="nlm:document:abc123:source_summary:src789",
                notebook_id=notebook_id,
                origin_type="source",
                origin_id="nlm:source:abc123:src789",
                document_kind="source_summary",
                title="Example paper",
                text=document_text,
                url="https://example.com/paper",
                content_sha256=content_sha256(document_text),
                metadata={"source_type": "web"},
            ),
        ),
    )
    store.replace_notebook_snapshot(snapshot)

    started_run = SyncRunRecord(
        id=f"sync-{uuid.uuid4().hex[:8]}",
        notebook_id=notebook_id,
        status="running",
        started_at="2026-04-18T20:00:00Z",
    )
    completed_run = SyncRunRecord(
        id=started_run.id,
        notebook_id=notebook_id,
        status="success",
        started_at=started_run.started_at,
        completed_at="2026-04-18T20:01:00Z",
        source_count=1,
        artifact_count=0,
        document_count=1,
        chunk_count=1,
        summary="Synced 1 notebook document.",
    )
    store.record_sync_run_start(started_run)
    store.finalize_sync_run(completed_run, ())
    return paths


def _start_server(config: ServerConfig, paths: StorePaths) -> tuple[McpHttpServer, threading.Thread]:
    backend = SQLiteResearchBackend(paths=paths)
    protocol_server = McpProtocolServer(backend=backend)
    server = McpHttpServer(
        (config.host, config.port),
        McpRequestHandler,
        protocol_server=protocol_server,
        config=config,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _validate_local_dev(port: int) -> None:
    status, headers, body = _json_request(
        port,
        "POST",
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25"},
        },
        headers={"Accept": ACCEPT_POST},
    )
    _assert(status == 200, f"initialize failed: {status} {body}")
    session_id = headers.get("MCP-Session-Id")
    protocol_version = headers.get("MCP-Protocol-Version")
    _assert(bool(session_id), "initialize response missing MCP-Session-Id")
    _assert(protocol_version == "2025-11-25", "protocol version negotiation failed")

    common_headers = {
        "Accept": ACCEPT_POST,
        "MCP-Session-Id": session_id,
        "MCP-Protocol-Version": protocol_version,
    }

    status, _, body = _json_request(
        port,
        "POST",
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        headers=common_headers,
    )
    _assert(status == 200, f"tools/list failed: {status} {body}")
    tools = body["result"]["tools"]
    _assert(any(tool["name"] == "search" for tool in tools), "search tool missing")
    _assert(
        all(tool["annotations"]["readOnlyHint"] is True for tool in tools),
        "readOnlyHint missing on one or more tools",
    )

    status, _, body = _json_request(
        port,
        "POST",
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "search", "arguments": {"query": "alignment"}},
        },
        headers=common_headers,
    )
    _assert(status == 200, f"search failed: {status} {body}")
    search_payload = json.loads(body["result"]["content"][0]["text"])
    _assert(search_payload["results"], "search returned no results")

    document_id = search_payload["results"][0]["id"]
    status, _, body = _json_request(
        port,
        "POST",
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "fetch", "arguments": {"id": document_id}},
        },
        headers=common_headers,
    )
    _assert(status == 200, f"fetch failed: {status} {body}")
    fetch_payload = json.loads(body["result"]["content"][0]["text"])
    _assert(fetch_payload["id"] == document_id, "fetch returned wrong document")
    _assert(fetch_payload["metadata"]["notebook_id"] == "nlm:notebook:abc123", "fetch metadata missing notebook_id")

    status, _, body = _json_request(
        port,
        "POST",
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "list_notebooks", "arguments": {}},
        },
        headers=common_headers,
    )
    _assert(status == 200, f"list_notebooks failed: {status} {body}")
    notebooks = json.loads(body["result"]["content"][0]["text"])
    _assert(len(notebooks) == 1, "expected one notebook in local store")

    status, _, body = _json_request(
        port,
        "POST",
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {"name": "get_sync_status", "arguments": {"notebook_id": "nlm:notebook:abc123"}},
        },
        headers=common_headers,
    )
    _assert(status == 200, f"get_sync_status failed: {status} {body}")
    sync_payload = json.loads(body["result"]["content"][0]["text"])
    _assert(sync_payload["status"] == "success", "expected successful sync status")

    status, _, body = _json_request(
        port,
        "POST",
        {"jsonrpc": "2.0", "id": 7, "method": "ping", "params": {}},
        headers={"MCP-Session-Id": session_id, "MCP-Protocol-Version": protocol_version},
    )
    _assert(status == 400, "missing Accept header should be rejected")
    _assert(body["error"]["message"] == "Missing Accept header.", "unexpected missing Accept error")

    status, _, body = _json_request(
        port,
        "POST",
        [
            {"jsonrpc": "2.0", "id": 8, "method": "ping", "params": {}},
            {"jsonrpc": "2.0", "id": 9, "method": "ping", "params": {}},
        ],
        headers=common_headers,
    )
    _assert(status == 400, "batch POST should be rejected")
    _assert("single JSON-RPC object" in body["error"]["message"], "unexpected batch rejection message")

    status, _, _ = _json_request(
        port,
        "DELETE",
        None,
        headers={"MCP-Session-Id": session_id},
    )
    _assert(status == 204, f"DELETE session failed: {status}")

    status, _, body = _json_request(
        port,
        "POST",
        {"jsonrpc": "2.0", "id": 10, "method": "ping", "params": {}},
        headers=common_headers,
    )
    _assert(status == 404, "deleted session should return 404")
    _assert(body["error"]["message"] == "Unknown MCP session.", "unexpected deleted-session error")


def _validate_bearer_mode(port: int) -> None:
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-11-25"},
    }

    status, headers, body = _json_request(
        port,
        "POST",
        initialize,
        headers={"Accept": ACCEPT_POST},
    )
    _assert(status == 401, f"unauthenticated request should return 401, got {status}")
    _assert(headers.get("WWW-Authenticate") == 'Bearer realm="notebook-mcp"', "missing WWW-Authenticate challenge")
    _assert(body["error"]["message"] == "Missing bearer token.", "unexpected unauthorized error")

    status, headers, body = _json_request(
        port,
        "POST",
        initialize,
        headers={
            "Accept": ACCEPT_POST,
            "Authorization": "Bearer secret-token",
        },
    )
    _assert(status == 200, f"authorized initialize failed: {status} {body}")
    _assert(bool(headers.get("MCP-Session-Id")), "authorized initialize missing session id")


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        paths = _seed_store(Path(temp_dir))

        local_server, local_thread = _start_server(
            ServerConfig(host="127.0.0.1", port=0, auth_mode="local-dev"),
            paths,
        )
        try:
            _validate_local_dev(local_server.server_address[1])
        finally:
            local_server.shutdown()
            local_server.server_close()
            local_thread.join(timeout=5)

        bearer_server, bearer_thread = _start_server(
            ServerConfig(
                host="127.0.0.1",
                port=0,
                auth_mode="bearer",
                bearer_token="secret-token",
            ),
            paths,
        )
        try:
            _validate_bearer_mode(bearer_server.server_address[1])
        finally:
            bearer_server.shutdown()
            bearer_server.server_close()
            bearer_thread.join(timeout=5)

    print("Validated local-dev and bearer-auth streamable HTTP flows against the local SQLite backend.")


if __name__ == "__main__":
    main()
