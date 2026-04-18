from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.notebooklm_client.connector import FailoverNotebookLMConnector
from src.notebooklm_client.endpoints import (
    EndpointDefinition,
    NotebookLMEndpointSet,
    load_endpoint_config,
)
from src.notebooklm_client.http_connector import NotebookLMHttpConnector
from src.notebooklm_client.playwright_connector import PlaywrightNotebookLMConnector

from .service import NotebookLMAuthManager


def _build_endpoints(args: argparse.Namespace) -> tuple[str, NotebookLMEndpointSet] | None:
    config_path = Path(args.endpoint_config) if args.endpoint_config else None
    loaded_config = load_endpoint_config(config_path)
    if loaded_config is not None:
        return loaded_config.base_url, loaded_config.endpoints

    if not args.list_notebooks_path:
        return None

    return "https://notebooklm.google.com", NotebookLMEndpointSet(
        list_notebooks=EndpointDefinition(path=args.list_notebooks_path),
        get_notebook=EndpointDefinition(path=args.get_notebook_path) if args.get_notebook_path else None,
        list_sources=EndpointDefinition(path=args.list_sources_path) if args.list_sources_path else None,
        list_artifacts=EndpointDefinition(path=args.list_artifacts_path) if args.list_artifacts_path else None,
        get_artifact=EndpointDefinition(path=args.get_artifact_path) if args.get_artifact_path else None,
    )


def _build_probe_connector(
    args: argparse.Namespace,
    auth_manager: NotebookLMAuthManager,
) -> FailoverNotebookLMConnector | None:
    built = _build_endpoints(args)
    if built is None:
        return None
    base_url, endpoints = built

    http_connector = NotebookLMHttpConnector(
        auth_manager=auth_manager,
        endpoints=endpoints,
        base_url=base_url,
    )
    fallback_connector = None
    if args.playwright_fallback:
        fallback_connector = PlaywrightNotebookLMConnector(
            auth_manager=auth_manager,
            endpoints=endpoints,
            base_url=base_url,
        )
    return FailoverNotebookLMConnector(
        http_connector=http_connector,
        auth_manager=auth_manager,
        playwright_connector=fallback_connector,
        auto_recover_auth=args.auto_recover_auth,
    )


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="NotebookLM auth utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    login_parser = subparsers.add_parser("login", help="Bootstrap NotebookLM login")
    login_parser.add_argument("--headless", action="store_true")
    login_parser.add_argument("--timeout-seconds", type=int, default=300)

    subparsers.add_parser("validate", help="Validate the saved NotebookLM session")

    doctor_parser = subparsers.add_parser("doctor", help="Run auth and connector checks")
    doctor_parser.add_argument("--endpoint-config")
    doctor_parser.add_argument("--list-notebooks-path")
    doctor_parser.add_argument("--get-notebook-path")
    doctor_parser.add_argument("--list-sources-path")
    doctor_parser.add_argument("--list-artifacts-path")
    doctor_parser.add_argument("--get-artifact-path")
    doctor_parser.add_argument("--playwright-fallback", action="store_true")
    doctor_parser.add_argument("--auto-recover-auth", action="store_true")

    args = parser.parse_args()
    auth_manager = NotebookLMAuthManager()

    if args.command == "login":
        session = auth_manager.bootstrap_login(
            timeout_seconds=args.timeout_seconds,
            headless=args.headless,
        )
        _print_json(auth_manager.validate_session(session).__dict__)
        return 0

    if args.command == "validate":
        _print_json(auth_manager.validate_session().__dict__)
        return 0

    connector = _build_probe_connector(args, auth_manager)
    probe = connector.probe if connector is not None else None
    _print_json(auth_manager.doctor(probe=probe).to_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
