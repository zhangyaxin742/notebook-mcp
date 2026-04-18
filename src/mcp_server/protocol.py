from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from .backend import BackendError, NotFoundError, ResearchBackend
from .tools import ToolSpec, ToolValidationError, build_tool_registry, validate_tool_arguments


JSONDict = dict[str, Any]
LATEST_PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_PROTOCOL_VERSIONS = (
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
)
SERVER_INFO = {
    "name": "notebook-mcp",
    "title": "Notebook MCP",
    "version": "0.1.0",
}


@dataclass(slots=True)
class SessionState:
    session_id: str
    protocol_version: str
    initialized: bool = False


class JsonRpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


class McpProtocolServer:
    def __init__(
        self,
        backend: ResearchBackend,
        tool_registry: Mapping[str, ToolSpec] | None = None,
    ) -> None:
        self._backend = backend
        self._tool_registry = dict(tool_registry or build_tool_registry())
        self._sessions: dict[str, SessionState] = {}

    def get_session(self, session_id: str) -> SessionState | None:
        return self._sessions.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None

    def handle_jsonrpc_message(
        self, message: Mapping[str, Any], session: SessionState | None
    ) -> tuple[JSONDict | None, SessionState | None]:
        if message.get("jsonrpc") != "2.0":
            raise JsonRpcError(-32600, "Invalid Request")

        if "method" not in message:
            return None, None

        request_id = message.get("id")
        method = message["method"]
        params = message.get("params")

        if request_id is None:
            self._handle_notification(method, params, session)
            return None, None

        result, new_session = self._handle_request(method, params, session)
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result,
        }, new_session

    def build_error_response(self, request_id: Any, error: JsonRpcError) -> JSONDict:
        body: JSONDict = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": error.code,
                "message": error.message,
            },
        }
        if error.data is not None:
            body["error"]["data"] = error.data
        return body

    def build_transport_error(self, code: int, message: str, data: Any = None) -> JSONDict:
        body: JSONDict = {
            "jsonrpc": "2.0",
            "id": None,
            "error": {
                "code": code,
                "message": message,
            },
        }
        if data is not None:
            body["error"]["data"] = data
        return body

    def negotiate_protocol_version(self, requested_version: str | None) -> str:
        if requested_version in SUPPORTED_PROTOCOL_VERSIONS:
            return str(requested_version)
        return LATEST_PROTOCOL_VERSION

    def _handle_request(
        self, method: str, params: Any, session: SessionState | None
    ) -> tuple[JSONDict, SessionState | None]:
        if method == "initialize":
            return self._handle_initialize(params)

        if method == "ping":
            return {}, None

        if session is None:
            raise JsonRpcError(-32000, "Missing MCP session.")

        if method == "tools/list":
            return {"tools": [tool.to_mcp_tool() for tool in self._tool_registry.values()]}, None

        if method == "tools/call":
            return self._handle_tool_call(params), None

        raise JsonRpcError(-32601, f"Method not found: {method}")

    def _handle_notification(
        self, method: str, params: Any, session: SessionState | None
    ) -> None:
        if method == "notifications/initialized":
            if session is not None:
                session.initialized = True
            return

    def _handle_initialize(self, params: Any) -> tuple[JSONDict, SessionState]:
        if not isinstance(params, Mapping):
            raise JsonRpcError(-32602, "Invalid params")

        requested_version = params.get("protocolVersion")
        negotiated_version = self.negotiate_protocol_version(
            requested_version if isinstance(requested_version, str) else None
        )
        session = SessionState(
            session_id=uuid.uuid4().hex,
            protocol_version=negotiated_version,
        )
        self._sessions[session.session_id] = session

        return {
            "protocolVersion": negotiated_version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
            "instructions": (
                "Read-only research tools over canonical NotebookLM data."
            ),
        }, session

    def _handle_tool_call(self, params: Any) -> JSONDict:
        if not isinstance(params, Mapping):
            raise JsonRpcError(-32602, "Invalid params")

        tool_name = params.get("name")
        if not isinstance(tool_name, str):
            raise JsonRpcError(-32602, "Tool name must be a string.")

        tool = self._tool_registry.get(tool_name)
        if tool is None:
            raise JsonRpcError(-32602, f"Unknown tool: {tool_name}")

        try:
            arguments = validate_tool_arguments(params.get("arguments"), tool.input_schema)
            return tool.handler(self._backend, arguments)
        except ToolValidationError as error:
            raise JsonRpcError(-32602, str(error)) from error
        except NotFoundError as error:
            raise JsonRpcError(-32004, str(error)) from error
        except BackendError as error:
            raise JsonRpcError(-32000, str(error)) from error
