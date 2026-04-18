from __future__ import annotations

import ipaddress
import json
import os
from hmac import compare_digest
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

from .protocol import (
    McpProtocolServer,
    JsonRpcError,
    SUPPORTED_PROTOCOL_VERSIONS,
    SessionState,
)


JSONDict = dict[str, Any]
DEFAULT_PROTOCOL_VERSION = "2025-03-26"


@dataclass(frozen=True, slots=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    transport: str = "streamable-http"
    endpoint_path: str = "/mcp"
    auth_mode: str = "local-dev"
    bearer_token: str | None = None
    allowed_origins: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "ServerConfig":
        host = os.getenv("NOTEBOOK_MCP_HOST", "127.0.0.1")
        port = int(os.getenv("NOTEBOOK_MCP_PORT", "8000"))
        transport = os.getenv("NOTEBOOK_MCP_TRANSPORT", "streamable-http")
        auth_mode = os.getenv("NOTEBOOK_MCP_AUTH_MODE", "local-dev")
        bearer_token = os.getenv("NOTEBOOK_MCP_BEARER_TOKEN")
        allowed_origins_raw = os.getenv("NOTEBOOK_MCP_ALLOWED_ORIGINS", "")
        allowed_origins = tuple(
            origin.strip()
            for origin in allowed_origins_raw.split(",")
            if origin.strip()
        )
        return cls(
            host=host,
            port=port,
            transport=transport,
            auth_mode=auth_mode,
            bearer_token=bearer_token,
            allowed_origins=allowed_origins,
        )


class McpHttpServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        request_handler_class: type[BaseHTTPRequestHandler],
        protocol_server: McpProtocolServer,
        config: ServerConfig,
    ) -> None:
        super().__init__(server_address, request_handler_class)
        self.protocol_server = protocol_server
        self.config = config


class McpRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "NotebookMCP/0.1"

    def do_GET(self) -> None:
        if not self._is_endpoint_request():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not self._validate_accept_header(required={"text/event-stream"}):
            return
        if not self._validate_origin():
            return
        if not self._authorize_request():
            return

        session = self._resolve_session(required=False)
        if session is None and self._has_session_header():
            self._send_json(
                HTTPStatus.NOT_FOUND,
                self.server.protocol_server.build_transport_error(
                    -32000,
                    "Unknown MCP session.",
                ),
            )
            return

        self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
        self.send_header("Allow", "POST, DELETE")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_DELETE(self) -> None:
        if not self._is_endpoint_request():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not self._validate_origin():
            return
        if not self._authorize_request():
            return

        session = self._resolve_session(required=True)
        if session is None:
            return

        self.server.protocol_server.delete_session(session.session_id)
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self) -> None:
        if not self._is_endpoint_request():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not self._validate_accept_header(
            required={"application/json", "text/event-stream"}
        ):
            return
        if not self._validate_origin():
            return
        if not self._authorize_request():
            return

        try:
            body = self._read_json_body()
        except ValueError as error:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                self.server.protocol_server.build_transport_error(-32700, str(error)),
            )
            return

        if isinstance(body, Mapping):
            messages = [body]
        else:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                self.server.protocol_server.build_transport_error(
                    -32600,
                    "Streamable HTTP expects a single JSON-RPC object per POST.",
                ),
            )
            return

        session = self._resolve_session(required=self._requires_session(messages))
        if self._requires_session(messages) and session is None:
            return

        if not self._validate_protocol_version(messages, session):
            return

        responses: list[JSONDict] = []
        created_session: SessionState | None = None

        for message in messages:
            if not isinstance(message, Mapping):
                responses.append(
                    self.server.protocol_server.build_error_response(
                        None, JsonRpcError(-32600, "Invalid Request")
                    )
                )
                continue

            request_id = message.get("id")
            try:
                response, new_session = self.server.protocol_server.handle_jsonrpc_message(
                    message, session
                )
            except JsonRpcError as error:
                responses.append(
                    self.server.protocol_server.build_error_response(request_id, error)
                )
                continue

            if new_session is not None:
                session = new_session
                created_session = new_session

            if response is not None:
                responses.append(response)

        if not responses:
            self.send_response(HTTPStatus.ACCEPTED)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        response_body = responses[0]

        headers: dict[str, str] = {}
        if created_session is not None:
            headers["MCP-Session-Id"] = created_session.session_id
            headers["MCP-Protocol-Version"] = created_session.protocol_version
        elif session is not None:
            headers["MCP-Protocol-Version"] = session.protocol_version

        self._send_json(HTTPStatus.OK, response_body, headers=headers)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _is_endpoint_request(self) -> bool:
        return self.path == self.server.config.endpoint_path

    def _has_session_header(self) -> bool:
        return self.headers.get("MCP-Session-Id") is not None

    def _read_json_body(self) -> Any:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("Missing Content-Length header.")

        length = int(raw_length)
        data = self.rfile.read(length)
        try:
            return json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Request body must be valid UTF-8 JSON.") from error

    def _resolve_session(
        self,
        required: bool,
    ) -> SessionState | None:
        header_value = self.headers.get("MCP-Session-Id")
        if header_value is None:
            if required:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    self.server.protocol_server.build_transport_error(
                        -32000,
                        "Missing MCP session.",
                    ),
                )
            return None

        session = self.server.protocol_server.get_session(header_value)
        if session is None:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                self.server.protocol_server.build_transport_error(
                    -32000,
                    "Unknown MCP session.",
                ),
            )
            return None
        return session

    def _requires_session(self, messages: Iterable[Mapping[str, Any] | Any]) -> bool:
        for message in messages:
            if not isinstance(message, Mapping):
                continue
            if "method" not in message:
                continue
            if message["method"] != "initialize":
                return True
        return False

    def _validate_protocol_version(
        self,
        messages: Iterable[Mapping[str, Any] | Any],
        session: SessionState | None,
    ) -> bool:
        if any(
            isinstance(message, Mapping) and message.get("method") == "initialize"
            for message in messages
        ):
            return True

        header_value = self.headers.get("MCP-Protocol-Version")
        effective_version = header_value or (session.protocol_version if session else None)
        if effective_version is None:
            effective_version = DEFAULT_PROTOCOL_VERSION

        if effective_version not in SUPPORTED_PROTOCOL_VERSIONS:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                self.server.protocol_server.build_transport_error(
                    -32000,
                    f"Unsupported MCP protocol version: {effective_version}",
                ),
            )
            return False

        return True

    def _validate_accept_header(self, required: set[str]) -> bool:
        header_value = self.headers.get("Accept")
        if header_value is None:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                self.server.protocol_server.build_transport_error(
                    -32000,
                    "Missing Accept header.",
                ),
            )
            return False

        accepted_values = {
            part.split(";", 1)[0].strip().lower()
            for part in header_value.split(",")
            if part.strip()
        }
        missing = sorted(value for value in required if value not in accepted_values)
        if missing:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                self.server.protocol_server.build_transport_error(
                    -32000,
                    "Accept header must include: " + ", ".join(missing),
                ),
            )
            return False
        return True

    def _validate_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if origin is None:
            return True

        parsed = urlparse(origin)
        normalized_origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        if self.server.config.auth_mode == "local-dev":
            origin_host = (parsed.hostname or "").lower()
            allowed_hosts = {"127.0.0.1", "localhost", "::1"}
            configured_host = self.server.config.host.lower()
            if configured_host not in {"0.0.0.0", "::"}:
                allowed_hosts.add(configured_host)
            is_allowed = origin_host in allowed_hosts
        else:
            is_allowed = normalized_origin in {
                value.rstrip("/") for value in self.server.config.allowed_origins
            }

        if not is_allowed:
            self._send_json(
                HTTPStatus.FORBIDDEN,
                self.server.protocol_server.build_transport_error(
                    -32000,
                    "Forbidden origin.",
                ),
            )
            return False

        return True

    def _authorize_request(self) -> bool:
        if self.server.config.auth_mode == "local-dev":
            if self._is_loopback_client():
                return True
            self._send_json(
                HTTPStatus.FORBIDDEN,
                self.server.protocol_server.build_transport_error(
                    -32000,
                    "Local development mode only accepts loopback clients.",
                ),
            )
            return False

        if self.server.config.auth_mode != "bearer":
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                self.server.protocol_server.build_transport_error(
                    -32000,
                    f"Unsupported auth mode: {self.server.config.auth_mode}",
                ),
            )
            return False

        expected_token = self.server.config.bearer_token
        if not expected_token:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                self.server.protocol_server.build_transport_error(
                    -32000,
                    "Bearer auth mode requires a configured bearer token.",
                ),
            )
            return False

        header_value = self.headers.get("Authorization")
        if not header_value or not header_value.startswith("Bearer "):
            self._send_unauthorized("Missing bearer token.")
            return False

        presented_token = header_value[len("Bearer ") :]
        if not compare_digest(presented_token, expected_token):
            self._send_unauthorized("Invalid bearer token.")
            return False

        return True

    def _is_loopback_client(self) -> bool:
        try:
            return ipaddress.ip_address(self.client_address[0]).is_loopback
        except ValueError:
            return False

    def _send_unauthorized(self, message: str) -> None:
        self._send_json(
            HTTPStatus.UNAUTHORIZED,
            self.server.protocol_server.build_transport_error(-32001, message),
            headers={"WWW-Authenticate": 'Bearer realm="notebook-mcp"'},
        )

    def _send_json(
        self,
        status: HTTPStatus,
        payload: Mapping[str, Any] | list[Mapping[str, Any]],
        headers: Mapping[str, str] | None = None,
    ) -> None:
        data = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)


def serve_streamable_http(protocol_server: McpProtocolServer, config: ServerConfig) -> None:
    if config.transport != "streamable-http":
        raise ValueError(f"Unsupported transport: {config.transport}")

    server = McpHttpServer(
        (config.host, config.port),
        McpRequestHandler,
        protocol_server=protocol_server,
        config=config,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
