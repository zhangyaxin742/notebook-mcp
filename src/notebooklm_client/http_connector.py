from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.auth.models import NotebookLMSession
from src.auth.service import NotebookLMAuthManager

from ._parsing import extract_items, parse_raw_artifact, parse_raw_notebook, parse_raw_source
from .endpoints import EndpointDefinition, NotebookLMEndpointSet
from .errors import AuthExpiredError, EndpointDriftError, TransportError, UnsupportedShapeError
from .models import ConnectorHealth, RawArtifact, RawNotebook, RawNotebookBundle, RawSource


class NotebookLMHttpConnector:
    def __init__(
        self,
        *,
        auth_manager: NotebookLMAuthManager,
        endpoints: NotebookLMEndpointSet,
        base_url: str = "https://notebooklm.google.com",
    ) -> None:
        self._auth_manager = auth_manager
        self._endpoints = endpoints
        self._base_url = base_url

    def probe(self) -> ConnectorHealth:
        notebooks = self.list_notebooks()
        return ConnectorHealth(
            ok=True,
            transport="http",
            message="NotebookLM HTTP connector is healthy.",
            details={"notebook_count": len(notebooks)},
        )

    def list_notebooks(self) -> list[RawNotebook]:
        payload = self._request_json(self._endpoints.list_notebooks)
        items = extract_items(
            payload,
            label="notebook list",
            root_keys=self._endpoints.list_notebooks.root_keys,
            fallback_keys=("notebooks", "items", "results", "data"),
        )
        return [parse_raw_notebook(item, base_url=self._base_url) for item in items]

    def get_notebook(self, notebook_id: str) -> RawNotebook:
        if self._endpoints.get_notebook is None:
            for notebook in self.list_notebooks():
                if notebook.raw_id == notebook_id or notebook.entity_key == notebook_id:
                    return notebook
            raise EndpointDriftError(
                "Notebook detail endpoint is not configured and the notebook was not found."
            )
        payload = self._request_json(self._endpoints.get_notebook, notebook_id=notebook_id)
        if not isinstance(payload, dict):
            raise UnsupportedShapeError(
                "Notebook detail payload is not a JSON object.",
                details={"payload_type": type(payload).__name__},
            )
        return parse_raw_notebook(dict(payload), base_url=self._base_url)

    def list_sources(self, notebook_id: str) -> list[RawSource]:
        endpoint = self._require_endpoint(self._endpoints.list_sources, "list_sources")
        notebook = self.get_notebook(notebook_id)
        payload = self._request_json(endpoint, notebook_id=notebook_id)
        items = extract_items(
            payload,
            label="source list",
            root_keys=endpoint.root_keys,
            fallback_keys=("sources", "items", "results", "data"),
        )
        return [
            parse_raw_source(item, notebook_key=notebook.entity_key, base_url=self._base_url)
            for item in items
        ]

    def list_artifacts(self, notebook_id: str) -> list[RawArtifact]:
        endpoint = self._require_endpoint(self._endpoints.list_artifacts, "list_artifacts")
        notebook = self.get_notebook(notebook_id)
        payload = self._request_json(endpoint, notebook_id=notebook_id)
        items = extract_items(
            payload,
            label="artifact list",
            root_keys=endpoint.root_keys,
            fallback_keys=("artifacts", "items", "results", "data"),
        )
        return [
            parse_raw_artifact(item, notebook_key=notebook.entity_key, base_url=self._base_url)
            for item in items
        ]

    def get_artifact(self, notebook_id: str, artifact_id: str) -> RawArtifact:
        notebook = self.get_notebook(notebook_id)
        if self._endpoints.get_artifact is None:
            for artifact in self.list_artifacts(notebook_id):
                if artifact.raw_id == artifact_id or artifact.entity_key == artifact_id:
                    return artifact
            raise EndpointDriftError(
                "Artifact detail endpoint is not configured and the artifact was not found."
            )
        payload = self._request_json(
            self._endpoints.get_artifact,
            notebook_id=notebook_id,
            artifact_id=artifact_id,
        )
        if not isinstance(payload, dict):
            raise UnsupportedShapeError(
                "Artifact detail payload is not a JSON object.",
                details={"payload_type": type(payload).__name__},
            )
        return parse_raw_artifact(
            dict(payload),
            notebook_key=notebook.entity_key,
            base_url=self._base_url,
        )

    def fetch_notebook_bundle(self, notebook_id: str) -> RawNotebookBundle:
        notebook = self.get_notebook(notebook_id)
        sources = tuple(self.list_sources(notebook_id))
        artifacts = tuple(self.list_artifacts(notebook_id))
        return RawNotebookBundle(notebook=notebook, sources=sources, artifacts=artifacts)

    def _request_json(
        self,
        endpoint: EndpointDefinition,
        **context: Any,
    ) -> Any:
        session = self._require_valid_session()
        url = endpoint.render_url(self._base_url, **context)
        request_body = endpoint.render_body(**context)
        body_bytes = None
        if request_body is not None:
            body_bytes = json.dumps(request_body).encode("utf-8")

        headers = {
            "accept": "application/json",
            "origin": session.notebooklm_origin,
            "referer": session.headers.get("referer", f"{self._base_url}/"),
            **session.headers,
        }
        if session.user_agent:
            headers["user-agent"] = session.user_agent
        if session.csrf_token:
            headers["x-csrf-token"] = session.csrf_token
        headers["cookie"] = self._cookie_header(session)
        if body_bytes is not None:
            headers["content-type"] = "application/json"

        request = Request(
            url=url,
            headers=headers,
            method=endpoint.method.upper(),
            data=body_bytes,
        )
        try:
            with urlopen(request, timeout=endpoint.timeout_seconds) as response:
                raw_bytes = response.read()
                status_code = response.status
                content_type = response.headers.get("Content-Type", "")
                final_url = response.geturl()
        except HTTPError as exc:
            self._raise_for_http_error(exc)
        except URLError as exc:
            raise TransportError(
                "NotebookLM HTTP request failed.",
                details={"reason": str(exc.reason), "url": url},
            ) from exc

        text = raw_bytes.decode("utf-8", errors="replace")
        return self._parse_json_response(
            text=text,
            status_code=status_code,
            content_type=content_type,
            url=final_url,
        )

    def _parse_json_response(
        self,
        *,
        text: str,
        status_code: int,
        content_type: str,
        url: str,
    ) -> Any:
        lowered_text = text.lower()
        if "accounts.google.com" in url or "accounts.google.com" in lowered_text:
            raise AuthExpiredError(
                "NotebookLM returned a Google auth page instead of JSON.",
                details={"url": url, "status_code": status_code},
            )
        if "text/html" in content_type.lower():
            raise EndpointDriftError(
                "NotebookLM returned HTML instead of JSON.",
                details={"url": url, "status_code": status_code},
            )
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise UnsupportedShapeError(
                "NotebookLM returned non-JSON content.",
                details={"url": url, "status_code": status_code},
            ) from exc

    def _raise_for_http_error(self, exc: HTTPError) -> None:
        status_code = getattr(exc, "code", None)
        if status_code in {401, 403}:
            raise AuthExpiredError(
                "NotebookLM rejected the saved session.",
                details={"status_code": status_code, "url": exc.geturl()},
            ) from exc
        if status_code in {404, 405, 410}:
            raise EndpointDriftError(
                "NotebookLM endpoint appears to have changed.",
                details={"status_code": status_code, "url": exc.geturl()},
            ) from exc
        raise TransportError(
            "NotebookLM HTTP request returned an unexpected status.",
            details={"status_code": status_code, "url": exc.geturl()},
            retryable=status_code is not None and status_code >= 500,
        ) from exc

    def _require_valid_session(self) -> NotebookLMSession:
        validation = self._auth_manager.validate_session()
        if not validation.ok:
            raise AuthExpiredError(validation.message, details=validation.session_summary)
        session = self._auth_manager.load_session()
        if session is None:
            raise AuthExpiredError("NotebookLM session is missing.")
        return session

    @staticmethod
    def _require_endpoint(
        endpoint: EndpointDefinition | None,
        operation_name: str,
    ) -> EndpointDefinition:
        if endpoint is None:
            raise EndpointDriftError(
                f"{operation_name} is not configured for the NotebookLM connector."
            )
        return endpoint

    @staticmethod
    def _cookie_header(session: NotebookLMSession) -> str:
        cookies: list[str] = []
        for cookie in session.cookies:
            name = cookie.get("name")
            value = cookie.get("value")
            if name and value is not None:
                cookies.append(f"{name}={value}")
        return "; ".join(cookies)
