from __future__ import annotations

import json
import unittest

from src.mcp_server.backend import build_demo_backend
from src.mcp_server.protocol import JsonRpcError, LATEST_PROTOCOL_VERSION, McpProtocolServer
from src.mcp_server.validate_transport import main as validate_transport_main


class Terminal5McpProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = build_demo_backend()
        self.server = McpProtocolServer(backend=self.backend)

    def _initialize(self) -> tuple[dict[str, object], object]:
        response, session = self.server.handle_jsonrpc_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2099-01-01"},
            },
            None,
        )
        assert response is not None
        assert session is not None
        return response, session

    def test_initialize_negotiates_latest_supported_version(self) -> None:
        response, session = self._initialize()

        self.assertEqual(response["result"]["protocolVersion"], LATEST_PROTOCOL_VERSION)
        self.assertEqual(session.protocol_version, LATEST_PROTOCOL_VERSION)
        self.assertTrue(self.server.get_session(session.session_id))

    def test_tools_list_and_call_return_contract_shaped_payloads(self) -> None:
        _, session = self._initialize()

        list_response, _ = self.server.handle_jsonrpc_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
            session,
        )
        assert list_response is not None
        tools = list_response["result"]["tools"]
        tool_names = {tool["name"] for tool in tools}

        self.assertIn("search", tool_names)
        self.assertIn("fetch", tool_names)
        self.assertTrue(all(tool["annotations"]["readOnlyHint"] is True for tool in tools))

        search_response, _ = self.server.handle_jsonrpc_message(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "search", "arguments": {"query": "paper"}},
            },
            session,
        )
        assert search_response is not None
        search_payload = json.loads(search_response["result"]["content"][0]["text"])
        self.assertEqual(
            search_payload,
            {
                "results": [
                    {
                        "id": "nlm:document:abc123:source_summary:src789",
                        "title": "Example paper",
                        "url": "https://example.com/paper",
                    }
                ]
            },
        )

        fetch_response, _ = self.server.handle_jsonrpc_message(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "fetch",
                    "arguments": {"id": "nlm:document:abc123:source_summary:src789"},
                },
            },
            session,
        )
        assert fetch_response is not None
        fetch_payload = json.loads(fetch_response["result"]["content"][0]["text"])
        self.assertEqual(fetch_payload["id"], "nlm:document:abc123:source_summary:src789")
        self.assertEqual(fetch_payload["title"], "Example paper")
        self.assertEqual(fetch_payload["url"], "https://example.com/paper")
        self.assertEqual(
            fetch_payload["metadata"],
            {
                "document_kind": "source_summary",
                "notebook_id": "nlm:notebook:abc123",
                "origin_id": "nlm:source:abc123:src789",
                "origin_type": "source",
                "source_type": "web",
            },
        )

    def test_tool_validation_and_missing_session_surface_as_protocol_errors(self) -> None:
        _, session = self._initialize()

        with self.assertRaises(JsonRpcError) as invalid_args:
            self.server.handle_jsonrpc_message(
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {"name": "search", "arguments": {"query": "paper", "extra": True}},
                },
                session,
            )
        self.assertEqual(invalid_args.exception.code, -32602)
        self.assertIn("Unexpected field(s): extra.", invalid_args.exception.message)

        with self.assertRaises(JsonRpcError) as missing_session:
            self.server.handle_jsonrpc_message(
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/list",
                    "params": {},
                },
                None,
            )
        self.assertEqual(missing_session.exception.code, -32000)
        self.assertEqual(missing_session.exception.message, "Missing MCP session.")

    def test_validate_transport_smoke_covers_local_and_bearer_http_modes(self) -> None:
        validate_transport_main()


if __name__ == "__main__":
    unittest.main()
