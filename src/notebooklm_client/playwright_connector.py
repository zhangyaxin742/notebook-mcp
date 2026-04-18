from __future__ import annotations

import json
from importlib import import_module
from typing import Any

from src.auth.models import NotebookLMSession
from src.auth.service import NotebookLMAuthManager

from ._parsing import extract_items, parse_raw_artifact, parse_raw_notebook, parse_raw_source
from .endpoints import EndpointDefinition, NotebookLMEndpointSet
from .errors import AuthExpiredError, EndpointDriftError, TransportError, UnsupportedShapeError
from .models import ConnectorHealth, RawArtifact, RawNotebook, RawNotebookBundle, RawSource


class PlaywrightNotebookLMConnector:
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
            transport="playwright",
            message="NotebookLM Playwright connector is healthy.",
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

    def _request_json(self, endpoint: EndpointDefinition, **context: Any) -> Any:
        session = self._require_valid_session()
        try:
            sync_api = import_module("playwright.sync_api")
        except ModuleNotFoundError as exc:
            raise TransportError(
                "Playwright is not installed; browser fallback is unavailable.",
                retryable=False,
            ) from exc

        sync_playwright = getattr(sync_api, "sync_playwright")
        request_body = endpoint.render_body(**context)
        request_url = endpoint.render_url(self._base_url, **context)
        script = """
        async ({url, method, headers, body}) => {
          const response = await fetch(url, {
            method,
            headers,
            credentials: 'include',
            body: body ? JSON.stringify(body) : undefined,
          });
          const text = await response.text();
          return {
            status: response.status,
            url: response.url,
            contentType: response.headers.get('content-type') || '',
            text,
          };
        }
        """

        with sync_playwright() as playwright:
            context_manager = playwright.chromium.launch_persistent_context(
                user_data_dir=str(self._auth_manager.paths.browser_profile_dir),
                headless=True,
            )
            try:
                page = context_manager.pages[0] if context_manager.pages else context_manager.new_page()
                page.goto(self._base_url, wait_until="domcontentloaded")
                response = page.evaluate(
                    script,
                    {
                        "url": request_url,
                        "method": endpoint.method.upper(),
                        "headers": self._request_headers(session),
                        "body": request_body,
                    },
                )
                self._refresh_session_from_browser(context_manager, page)
            finally:
                context_manager.close()

        status_code = int(response["status"])
        content_type = str(response["contentType"])
        text = str(response["text"])
        url = str(response["url"])

        if status_code in {401, 403}:
            raise AuthExpiredError(
                "NotebookLM rejected the Playwright-backed browser session.",
                details={"status_code": status_code, "url": url},
            )
        if status_code in {404, 405, 410}:
            raise EndpointDriftError(
                "NotebookLM endpoint appears to have changed.",
                details={"status_code": status_code, "url": url},
            )
        if status_code >= 500:
            raise TransportError(
                "NotebookLM browser-backed request failed.",
                details={"status_code": status_code, "url": url},
            )
        if "accounts.google.com" in url or "accounts.google.com" in text.lower():
            raise AuthExpiredError(
                "NotebookLM redirected the browser session to Google auth.",
                details={"status_code": status_code, "url": url},
            )
        if "text/html" in content_type.lower():
            raise EndpointDriftError(
                "NotebookLM returned HTML instead of JSON.",
                details={"status_code": status_code, "url": url},
            )
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise UnsupportedShapeError(
                "NotebookLM returned non-JSON content through Playwright fallback.",
                details={"status_code": status_code, "url": url},
            ) from exc

    def _refresh_session_from_browser(self, context_manager: Any, page: Any) -> None:
        cookies = [
            cookie
            for cookie in context_manager.cookies()
            if "google" in str(cookie.get("domain", "")).lower()
            or "notebooklm" in str(cookie.get("domain", "")).lower()
        ]
        try:
            user_agent = page.evaluate("() => navigator.userAgent")
        except Exception:
            user_agent = None
        if cookies:
            self._auth_manager.save_session(
                NotebookLMSession(
                    cookies=tuple(cookies),
                    headers={
                        "origin": "https://notebooklm.google.com",
                        "referer": f"{self._base_url}/",
                    },
                    user_agent=user_agent,
                    notebooklm_origin="https://notebooklm.google.com",
                )
            )

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
    def _request_headers(session: NotebookLMSession) -> dict[str, str]:
        headers = {
            "accept": "application/json",
            "origin": session.notebooklm_origin,
            "referer": session.headers.get("referer", "https://notebooklm.google.com/"),
            **session.headers,
        }
        if session.user_agent:
            headers["user-agent"] = session.user_agent
        if session.csrf_token:
            headers["x-csrf-token"] = session.csrf_token
        return headers
