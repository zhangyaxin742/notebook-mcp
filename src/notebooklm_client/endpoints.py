from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode, urljoin


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
