from __future__ import annotations

import argparse
from pathlib import Path

from src.store.settings import StorePaths

from .backend import NullResearchBackend, SQLiteResearchBackend, build_demo_backend
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
    parser.add_argument(
        "--null-backend",
        action="store_true",
        help="Run with the null backend instead of the SQLite-backed local store.",
    )
    parser.add_argument(
        "--data-dir",
        help="Override the local data root used by the SQLite-backed backend.",
    )
    parser.add_argument(
        "--db-path",
        help="Override the SQLite database path used by the SQLite-backed backend.",
    )
    parser.add_argument(
        "--auth-mode",
        choices=["local-dev", "bearer"],
        help="Security mode for HTTP access.",
    )
    parser.add_argument(
        "--allow-origin",
        action="append",
        default=[],
        help="Allowed browser Origin for bearer mode. May be repeated.",
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
            auth_mode=config.auth_mode,
            bearer_token=config.bearer_token,
            allowed_origins=config.allowed_origins,
        )
    if args.port is not None:
        config = ServerConfig(
            host=config.host,
            port=args.port,
            transport=config.transport,
            endpoint_path=config.endpoint_path,
            auth_mode=config.auth_mode,
            bearer_token=config.bearer_token,
            allowed_origins=config.allowed_origins,
        )
    if args.transport:
        config = ServerConfig(
            host=config.host,
            port=config.port,
            transport=args.transport,
            endpoint_path=config.endpoint_path,
            auth_mode=config.auth_mode,
            bearer_token=config.bearer_token,
            allowed_origins=config.allowed_origins,
        )
    if args.auth_mode:
        config = ServerConfig(
            host=config.host,
            port=config.port,
            transport=config.transport,
            endpoint_path=config.endpoint_path,
            auth_mode=args.auth_mode,
            bearer_token=config.bearer_token,
            allowed_origins=tuple(args.allow_origin) or config.allowed_origins,
        )
    elif args.allow_origin:
        config = ServerConfig(
            host=config.host,
            port=config.port,
            transport=config.transport,
            endpoint_path=config.endpoint_path,
            auth_mode=config.auth_mode,
            bearer_token=config.bearer_token,
            allowed_origins=tuple(args.allow_origin),
        )

    if args.demo_data and args.null_backend:
        raise SystemExit("Choose either --demo-data or --null-backend, not both.")

    if args.demo_data:
        backend = build_demo_backend()
    elif args.null_backend:
        backend = NullResearchBackend()
    else:
        data_dir = Path(args.data_dir) if args.data_dir else StorePaths.from_env().data_dir
        db_path = Path(args.db_path) if args.db_path else (data_dir / "db" / "notebook_mcp.sqlite3")
        paths = StorePaths(
            data_dir=data_dir,
            db_path=db_path,
            snapshots_dir=data_dir / "snapshots",
        )
        backend = SQLiteResearchBackend(paths=paths)

    protocol_server = McpProtocolServer(backend=backend)
    serve_streamable_http(protocol_server=protocol_server, config=config)


if __name__ == "__main__":
    main()
