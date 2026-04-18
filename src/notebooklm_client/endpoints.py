from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
from typing import Any
from urllib.parse import urlencode, urljoin

from src.auth.config import resolve_runtime_paths


def _render_template(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return value.format(**context)
    if isinstance(value, dict):
        return {str(key): _render_template(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [_render_template(item, context) for item in value]
    if isinstance(value, tuple):
        return tuple(_render_template(item, context) for item in value)
    return value


@dataclass(frozen=True)
class EndpointDefinition:
    path: str
    method: str = "GET"
    query: dict[str, Any] = field(default_factory=dict)
    body: dict[str, Any] | None = None
    root_keys: tuple[str, ...] = ()
    timeout_seconds: float = 30.0

    def render_url(self, base_url: str, **context: Any) -> str:
        rendered_path = _render_template(self.path, context)
        query = _render_template(self.query, context)
        url = urljoin(base_url.rstrip("/") + "/", str(rendered_path).lstrip("/"))
        if query:
            return f"{url}?{urlencode(query, doseq=True)}"
        return url

    def render_body(self, **context: Any) -> dict[str, Any] | None:
        if self.body is None:
            return None
        return _render_template(self.body, context)


@dataclass(frozen=True)
class NotebookLMEndpointSet:
    list_notebooks: EndpointDefinition
    get_notebook: EndpointDefinition | None = None
    list_sources: EndpointDefinition | None = None
    list_artifacts: EndpointDefinition | None = None
    get_artifact: EndpointDefinition | None = None


@dataclass(frozen=True)
class LoadedEndpointConfig:
    base_url: str
    endpoints: NotebookLMEndpointSet
    source_path: Path


def default_endpoint_config_path() -> Path:
    return resolve_runtime_paths().auth_dir / "notebooklm_endpoints.json"


def _endpoint_from_dict(payload: dict[str, Any]) -> EndpointDefinition:
    path = payload.get("path")
    if not isinstance(path, str) or not path.strip():
        raise ValueError("Endpoint config entry must contain a non-empty string path.")
    method = payload.get("method", "GET")
    query = payload.get("query") or {}
    body = payload.get("body")
    root_keys = payload.get("root_keys") or ()
    timeout_seconds = payload.get("timeout_seconds", 30.0)
    if not isinstance(query, dict):
        raise ValueError("Endpoint query must be a JSON object when provided.")
    if body is not None and not isinstance(body, dict):
        raise ValueError("Endpoint body must be a JSON object or null.")
    if not isinstance(root_keys, list | tuple):
        raise ValueError("Endpoint root_keys must be an array when provided.")
    return EndpointDefinition(
        path=path,
        method=str(method),
        query=dict(query),
        body=dict(body) if body is not None else None,
        root_keys=tuple(str(key) for key in root_keys),
        timeout_seconds=float(timeout_seconds),
    )


def load_endpoint_config(path: Path | None = None) -> LoadedEndpointConfig | None:
    config_path = path or default_endpoint_config_path()
    if not config_path.exists():
        return None

    with config_path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError("Endpoint config file must contain a JSON object.")

    raw_endpoints = payload.get("endpoints")
    if not isinstance(raw_endpoints, dict):
        raise ValueError("Endpoint config must contain an 'endpoints' object.")
    if "list_notebooks" not in raw_endpoints:
        raise ValueError("Endpoint config must define endpoints.list_notebooks.")

    base_url = payload.get("base_url", "https://notebooklm.google.com")
    if not isinstance(base_url, str) or not base_url.strip():
        raise ValueError("Endpoint config base_url must be a non-empty string.")

    def optional_endpoint(name: str) -> EndpointDefinition | None:
        raw_value = raw_endpoints.get(name)
        if raw_value is None:
            return None
        if not isinstance(raw_value, dict):
            raise ValueError(f"Endpoint config entry '{name}' must be a JSON object.")
        return _endpoint_from_dict(raw_value)

    return LoadedEndpointConfig(
        base_url=base_url,
        endpoints=NotebookLMEndpointSet(
            list_notebooks=_endpoint_from_dict(raw_endpoints["list_notebooks"]),
            get_notebook=optional_endpoint("get_notebook"),
            list_sources=optional_endpoint("list_sources"),
            list_artifacts=optional_endpoint("list_artifacts"),
            get_artifact=optional_endpoint("get_artifact"),
        ),
        source_path=config_path,
    )
