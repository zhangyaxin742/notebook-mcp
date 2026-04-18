from __future__ import annotations

import argparse

from .backend import NullResearchBackend, build_demo_backend
from .http import ServerConfig, serve_streamable_http
from .protocol import McpProtocolServer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the notebook-mcp Streamable HTTP server."
    )
    parser.add_argument("--host", help="HTTP bind host")
    parser.add_argument("--port", type=int, help="HTTP bind port")
    parser.add_argument(
        "--transport",
        choices=["streamable-http"],
        help="Transport to run",
    )
    parser.add_argument(
        "--demo-data",
        action="store_true",
        help="Load a small in-memory demo dataset for smoke testing.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = ServerConfig.from_env()

    if args.host:
        config = ServerConfig(
            host=args.host,
            port=config.port,
            transport=config.transport,
            endpoint_path=config.endpoint_path,
        )
    if args.port is not None:
        config = ServerConfig(
            host=config.host,
            port=args.port,
            transport=config.transport,
            endpoint_path=config.endpoint_path,
        )
    if args.transport:
        config = ServerConfig(
            host=config.host,
            port=config.port,
            transport=args.transport,
            endpoint_path=config.endpoint_path,
        )

    backend = build_demo_backend() if args.demo_data else NullResearchBackend()
    protocol_server = McpProtocolServer(backend=backend)
    serve_streamable_http(protocol_server=protocol_server, config=config)


if __name__ == "__main__":
    main()
