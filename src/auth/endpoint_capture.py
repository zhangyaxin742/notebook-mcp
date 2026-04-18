from __future__ import annotations

from dataclasses import asdict, dataclass, field
from importlib import import_module
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from src.notebooklm_client._parsing import (
    extract_items,
    parse_raw_artifact,
    parse_raw_notebook,
    parse_raw_source,
)
from src.notebooklm_client.endpoints import (
    EndpointDefinition,
    NotebookLMEndpointSet,
    default_endpoint_config_path,
    endpoint_to_dict,
    write_endpoint_config,
)
from src.notebooklm_client.errors import UnsupportedShapeError

from .bootstrap import PlaywrightUnavailableError
from .models import NotebookLMSession, utc_now_iso
from .scrub import write_scrubbed_json
from .service import NotebookLMAuthManager


DISCOVERY_REPORT_NAME = "notebooklm_endpoint_discovery_report.json"
NOTEBOOK_LIST_FALLBACK_KEYS = ("notebooks", "items", "results", "data")
SOURCE_LIST_FALLBACK_KEYS = ("sources", "items", "results", "data")
ARTIFACT_LIST_FALLBACK_KEYS = ("artifacts", "items", "results", "data")


@dataclass(frozen=True)
class DiscoveredEndpointCandidate:
    endpoint_name: str
    method: str
    path: str
    query: dict[str, Any]
    root_keys: tuple[str, ...]
    source_url: str
    item_count: int
    confidence: int
    notebook_ids: tuple[str, ...] = ()
    artifact_ids: tuple[str, ...] = ()
    sample_notebook_url: str | None = None

    def to_endpoint_definition(self) -> EndpointDefinition:
        return EndpointDefinition(
            path=self.path,
            method=self.method,
            query=self.query,
            root_keys=self.root_keys,
        )


@dataclass(frozen=True)
class DiscoveryReport:
    generated_at: str
    base_url: str
    output_path: str
    report_path: str
    discovered_endpoints: dict[str, dict[str, Any]]
    captured_candidates: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class NotebookLMEndpointDiscoverer:
    def __init__(
        self,
        auth_manager: NotebookLMAuthManager,
        *,
        base_url: str = "https://notebooklm.google.com",
    ) -> None:
        self._auth_manager = auth_manager
        self._base_url = base_url.rstrip("/")

    def discover(
        self,
        *,
        output_path: Path | None = None,
        timeout_seconds: int = 45,
        headless: bool = True,
        bootstrap_login: bool = False,
    ) -> DiscoveryReport:
        validation = self._auth_manager.validate_session()
        if not validation.ok:
            if bootstrap_login:
                self._auth_manager.bootstrap_login(timeout_seconds=max(timeout_seconds, 60), headless=False)
            else:
                raise RuntimeError(
                    "NotebookLM endpoint discovery requires a valid session. "
                    "Run login first or pass bootstrap_login=True."
                )

        try:
            sync_api = import_module("playwright.sync_api")
        except ModuleNotFoundError as exc:
            raise PlaywrightUnavailableError(
                "Playwright is not installed; endpoint discovery is unavailable."
            ) from exc

        sync_playwright = getattr(sync_api, "sync_playwright")
        observed_candidates: list[DiscoveredEndpointCandidate] = []
        first_notebook_url: str | None = None
        warnings: list[str] = []

        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(self._auth_manager.paths.browser_profile_dir),
                headless=headless,
            )
            try:
                context.on(
                    "response",
                    lambda response: self._capture_response(
                        response=response,
                        observed_candidates=observed_candidates,
                        warnings=warnings,
                    ),
                )
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(f"{self._base_url}/", wait_until="domcontentloaded")
                page.wait_for_timeout(min(timeout_seconds, 15) * 1000)

                first_notebook_url = self._find_first_notebook_url(observed_candidates)
                if first_notebook_url:
                    page.goto(first_notebook_url, wait_until="domcontentloaded")
                    page.wait_for_timeout(min(timeout_seconds, 15) * 1000)

                self._refresh_session_from_browser(context, page)
            finally:
                context.close()

        endpoint_set, endpoint_warnings = self._build_endpoint_set(observed_candidates)
        warnings.extend(endpoint_warnings)
        if first_notebook_url is None:
            warnings.append(
                "No notebook URL was discovered automatically. The config may be missing notebook-scoped endpoints."
            )

        config_path = write_endpoint_config(
            base_url=self._base_url,
            endpoints=endpoint_set,
            path=output_path or default_endpoint_config_path(),
        )
        report_path = config_path.with_name(DISCOVERY_REPORT_NAME)
        report = DiscoveryReport(
            generated_at=utc_now_iso(),
            base_url=self._base_url,
            output_path=str(config_path),
            report_path=str(report_path),
            discovered_endpoints={
                name: endpoint_to_dict(candidate.to_endpoint_definition())
                for name, candidate in self._best_candidates_by_name(observed_candidates).items()
            },
            captured_candidates=[
                {
                    "endpoint_name": candidate.endpoint_name,
                    "method": candidate.method,
                    "path": candidate.path,
                    "query": candidate.query,
                    "root_keys": list(candidate.root_keys),
                    "source_url": candidate.source_url,
                    "item_count": candidate.item_count,
                    "confidence": candidate.confidence,
                    "notebook_ids": list(candidate.notebook_ids),
                    "artifact_ids": list(candidate.artifact_ids),
                    "sample_notebook_url": candidate.sample_notebook_url,
                }
                for candidate in observed_candidates
            ],
            warnings=warnings,
        )
        write_scrubbed_json(report_path, report.to_dict())
        return report

    def _capture_response(
        self,
        *,
        response: Any,
        observed_candidates: list[DiscoveredEndpointCandidate],
        warnings: list[str],
    ) -> None:
        try:
            request = response.request
            response_url = str(response.url)
            parsed_url = urlparse(response_url)
            if parsed_url.scheme not in {"https", "http"}:
                return
            if parsed_url.netloc != urlparse(self._base_url).netloc:
                return

            resource_type = str(getattr(request, "resource_type", ""))
            if resource_type not in {"fetch", "xhr"}:
                return

            status = int(response.status)
            if status >= 400:
                return

            headers = response.headers
            content_type = str(headers.get("content-type", ""))
            if "json" not in content_type.lower():
                return

            try:
                payload = response.json()
            except Exception:
                try:
                    payload = json.loads(response.text())
                except Exception:
                    return

            candidate = self._infer_candidate(
                method=str(request.method),
                parsed_url=parsed_url,
                payload=payload,
            )
            if candidate is not None:
                observed_candidates.append(candidate)
        except UnsupportedShapeError as exc:
            warnings.append(str(exc))
        except Exception:
            return

    def _infer_candidate(
        self,
        *,
        method: str,
        parsed_url: Any,
        payload: Any,
    ) -> DiscoveredEndpointCandidate | None:
        path = parsed_url.path
        path_lower = path.lower()
        query = parse_qs(parsed_url.query, keep_blank_values=True)
        normalized_query = {
            key: values if len(values) != 1 else values[0]
            for key, values in query.items()
        }

        if "source" in path_lower:
            source_list = self._try_source_list(payload, path=path, query=normalized_query)
            if source_list is not None:
                items, root_keys, notebook_ids = source_list
                templated = self._template_request(
                    path=path,
                    query=normalized_query,
                    notebook_ids=notebook_ids,
                )
                return DiscoveredEndpointCandidate(
                    endpoint_name="list_sources",
                    method=method.upper(),
                    path=templated["path"],
                    query=templated["query"],
                    root_keys=root_keys,
                    source_url=parsed_url.geturl(),
                    item_count=len(items),
                    confidence=90,
                    notebook_ids=tuple(notebook_ids),
                )

        if "artifact" in path_lower:
            artifact_list = self._try_artifact_list(payload, path=path, query=normalized_query)
            if artifact_list is not None:
                items, root_keys, notebook_ids = artifact_list
                artifact_ids = [item.raw_id for item in items if item.raw_id]
                templated = self._template_request(
                    path=path,
                    query=normalized_query,
                    notebook_ids=notebook_ids,
                    artifact_ids=artifact_ids,
                )
                endpoint_name = "get_artifact" if "{artifact_id}" in templated["path"] else "list_artifacts"
                confidence = 85 if endpoint_name == "list_artifacts" else 75
                return DiscoveredEndpointCandidate(
                    endpoint_name=endpoint_name,
                    method=method.upper(),
                    path=templated["path"],
                    query=templated["query"],
                    root_keys=root_keys if endpoint_name == "list_artifacts" else (),
                    source_url=parsed_url.geturl(),
                    item_count=len(items),
                    confidence=confidence,
                    notebook_ids=tuple(notebook_ids),
                    artifact_ids=tuple(artifact_ids),
                )

        notebook_list = self._try_notebook_list(payload)
        if notebook_list is not None:
            items, root_keys = notebook_list
            notebook_ids = [item.raw_id for item in items if item.raw_id]
            notebook_urls = [item.url for item in items if item.url]
            templated = self._template_request(
                path=path,
                query=normalized_query,
                notebook_ids=notebook_ids,
            )
            confidence = 100 if notebook_urls else 90
            return DiscoveredEndpointCandidate(
                endpoint_name="list_notebooks",
                method=method.upper(),
                path=templated["path"],
                query=templated["query"],
                root_keys=root_keys,
                source_url=parsed_url.geturl(),
                item_count=len(items),
                confidence=confidence,
                notebook_ids=tuple(notebook_ids),
                sample_notebook_url=next((url for url in notebook_urls if url), None),
            )

        notebook_detail = self._try_notebook_detail(payload)
        if notebook_detail is not None and self._contains_notebook_selector(path, normalized_query, notebook_detail.raw_id):
            templated = self._template_request(
                path=path,
                query=normalized_query,
                notebook_ids=[notebook_detail.raw_id] if notebook_detail.raw_id else [],
            )
            return DiscoveredEndpointCandidate(
                endpoint_name="get_notebook",
                method=method.upper(),
                path=templated["path"],
                query=templated["query"],
                root_keys=(),
                source_url=parsed_url.geturl(),
                item_count=1,
                confidence=80,
                notebook_ids=tuple([notebook_detail.raw_id] if notebook_detail.raw_id else ()),
                sample_notebook_url=notebook_detail.url,
            )

        source_list = self._try_source_list(payload, path=path, query=normalized_query)
        if source_list is not None:
            items, root_keys, notebook_ids = source_list
            templated = self._template_request(
                path=path,
                query=normalized_query,
                notebook_ids=notebook_ids,
            )
            return DiscoveredEndpointCandidate(
                endpoint_name="list_sources",
                method=method.upper(),
                path=templated["path"],
                query=templated["query"],
                root_keys=root_keys,
                source_url=parsed_url.geturl(),
                item_count=len(items),
                confidence=85,
                notebook_ids=tuple(notebook_ids),
            )

        artifact_list = self._try_artifact_list(payload, path=path, query=normalized_query)
        if artifact_list is not None:
            items, root_keys, notebook_ids = artifact_list
            artifact_ids = [item.raw_id for item in items if item.raw_id]
            templated = self._template_request(
                path=path,
                query=normalized_query,
                notebook_ids=notebook_ids,
                artifact_ids=artifact_ids,
            )
            endpoint_name = "get_artifact" if "{artifact_id}" in templated["path"] else "list_artifacts"
            confidence = 80 if endpoint_name == "list_artifacts" else 70
            return DiscoveredEndpointCandidate(
                endpoint_name=endpoint_name,
                method=method.upper(),
                path=templated["path"],
                query=templated["query"],
                root_keys=root_keys if endpoint_name == "list_artifacts" else (),
                source_url=parsed_url.geturl(),
                item_count=len(items),
                confidence=confidence,
                notebook_ids=tuple(notebook_ids),
                artifact_ids=tuple(artifact_ids),
            )

        artifact_detail = self._try_artifact_detail(payload)
        if artifact_detail is not None:
            templated = self._template_request(
                path=path,
                query=normalized_query,
                notebook_ids=[artifact_detail.notebook_key],
                artifact_ids=[artifact_detail.raw_id] if artifact_detail.raw_id else [],
            )
            if "{artifact_id}" in templated["path"] or "{artifact_id}" in json.dumps(templated["query"], sort_keys=True):
                return DiscoveredEndpointCandidate(
                    endpoint_name="get_artifact",
                    method=method.upper(),
                    path=templated["path"],
                    query=templated["query"],
                    root_keys=(),
                    source_url=parsed_url.geturl(),
                    item_count=1,
                    confidence=75,
                    notebook_ids=tuple([artifact_detail.notebook_key] if artifact_detail.notebook_key else ()),
                    artifact_ids=tuple([artifact_detail.raw_id] if artifact_detail.raw_id else ()),
                )

        return None

    def _build_endpoint_set(
        self,
        candidates: list[DiscoveredEndpointCandidate],
    ) -> tuple[NotebookLMEndpointSet, list[str]]:
        best = self._best_candidates_by_name(candidates)
        warnings: list[str] = []
        list_notebooks = best.get("list_notebooks")
        if list_notebooks is None:
            raise RuntimeError(
                "Endpoint discovery did not find a list_notebooks candidate. "
                "Open NotebookLM in a logged-in browser session and try again."
            )

        endpoint_set = NotebookLMEndpointSet(
            list_notebooks=list_notebooks.to_endpoint_definition(),
            get_notebook=best.get("get_notebook").to_endpoint_definition()
            if best.get("get_notebook")
            else None,
            list_sources=best.get("list_sources").to_endpoint_definition()
            if best.get("list_sources")
            else None,
            list_artifacts=best.get("list_artifacts").to_endpoint_definition()
            if best.get("list_artifacts")
            else None,
            get_artifact=best.get("get_artifact").to_endpoint_definition()
            if best.get("get_artifact")
            else None,
        )

        for name in ("get_notebook", "list_sources", "list_artifacts", "get_artifact"):
            if best.get(name) is None:
                warnings.append(
                    f"Endpoint discovery did not infer '{name}'. That connector capability may still need a manual config entry."
                )

        return endpoint_set, warnings

    @staticmethod
    def _best_candidates_by_name(
        candidates: list[DiscoveredEndpointCandidate],
    ) -> dict[str, DiscoveredEndpointCandidate]:
        best: dict[str, DiscoveredEndpointCandidate] = {}
        for candidate in candidates:
            current = best.get(candidate.endpoint_name)
            if current is None or (candidate.confidence, candidate.item_count) > (
                current.confidence,
                current.item_count,
            ):
                best[candidate.endpoint_name] = candidate
        return best

    @staticmethod
    def _try_notebook_list(payload: Any) -> tuple[list[Any], tuple[str, ...]] | None:
        if isinstance(payload, list):
            parsed = [parse_raw_notebook(item, base_url="https://notebooklm.google.com") for item in payload if isinstance(item, dict)]
            if parsed:
                return parsed, ()
            return None

        if not isinstance(payload, dict):
            return None

        for key in NOTEBOOK_LIST_FALLBACK_KEYS + tuple(payload.keys()):
            try:
                items = extract_items(payload, label="notebook list", root_keys=(key,), fallback_keys=())
            except UnsupportedShapeError:
                continue
            try:
                parsed = [
                    parse_raw_notebook(item, base_url="https://notebooklm.google.com")
                    for item in items
                ]
            except UnsupportedShapeError:
                continue
            if parsed:
                return parsed, (key,) if key in payload else ()
        return None

    @staticmethod
    def _try_notebook_detail(payload: Any) -> Any | None:
        if not isinstance(payload, dict):
            return None
        try:
            return parse_raw_notebook(payload, base_url="https://notebooklm.google.com")
        except UnsupportedShapeError:
            return None

    @staticmethod
    def _try_source_list(
        payload: Any,
        *,
        path: str,
        query: dict[str, Any],
    ) -> tuple[list[Any], tuple[str, ...], list[str]] | None:
        notebook_ids = NotebookLMEndpointDiscoverer._notebook_ids_from_request(path, query)
        if not notebook_ids and "source" not in path.lower():
            return None

        candidate_notebook_key = notebook_ids[0] if notebook_ids else "notebook"
        if isinstance(payload, list):
            try:
                parsed = [
                    parse_raw_source(
                        item,
                        notebook_key=candidate_notebook_key,
                        base_url="https://notebooklm.google.com",
                    )
                    for item in payload
                    if isinstance(item, dict)
                ]
            except UnsupportedShapeError:
                return None
            return (parsed, (), notebook_ids) if parsed else None

        if not isinstance(payload, dict):
            return None

        for key in SOURCE_LIST_FALLBACK_KEYS + tuple(payload.keys()):
            try:
                items = extract_items(payload, label="source list", root_keys=(key,), fallback_keys=())
            except UnsupportedShapeError:
                continue
            try:
                parsed = [
                    parse_raw_source(
                        item,
                        notebook_key=candidate_notebook_key,
                        base_url="https://notebooklm.google.com",
                    )
                    for item in items
                ]
            except UnsupportedShapeError:
                continue
            if parsed:
                return parsed, (key,) if key in payload else (), notebook_ids
        return None

    @staticmethod
    def _try_artifact_list(
        payload: Any,
        *,
        path: str,
        query: dict[str, Any],
    ) -> tuple[list[Any], tuple[str, ...], list[str]] | None:
        notebook_ids = NotebookLMEndpointDiscoverer._notebook_ids_from_request(path, query)
        if not notebook_ids and "artifact" not in path.lower():
            return None

        candidate_notebook_key = notebook_ids[0] if notebook_ids else "notebook"
        if isinstance(payload, list):
            try:
                parsed = [
                    parse_raw_artifact(
                        item,
                        notebook_key=candidate_notebook_key,
                        base_url="https://notebooklm.google.com",
                    )
                    for item in payload
                    if isinstance(item, dict)
                ]
            except UnsupportedShapeError:
                return None
            return (parsed, (), notebook_ids) if parsed else None

        if not isinstance(payload, dict):
            return None

        for key in ARTIFACT_LIST_FALLBACK_KEYS + tuple(payload.keys()):
            try:
                items = extract_items(payload, label="artifact list", root_keys=(key,), fallback_keys=())
            except UnsupportedShapeError:
                continue
            try:
                parsed = [
                    parse_raw_artifact(
                        item,
                        notebook_key=candidate_notebook_key,
                        base_url="https://notebooklm.google.com",
                    )
                    for item in items
                ]
            except UnsupportedShapeError:
                continue
            if parsed:
                return parsed, (key,) if key in payload else (), notebook_ids
        return None

    @staticmethod
    def _try_artifact_detail(payload: Any) -> Any | None:
        if not isinstance(payload, dict):
            return None
        notebook_key = str(
            payload.get("notebookId")
            or payload.get("notebook_id")
            or payload.get("notebookKey")
            or "notebook"
        )
        try:
            return parse_raw_artifact(
                payload,
                notebook_key=notebook_key,
                base_url="https://notebooklm.google.com",
            )
        except UnsupportedShapeError:
            return None

    @staticmethod
    def _notebook_ids_from_request(path: str, query: dict[str, Any]) -> list[str]:
        ids: list[str] = []
        segments = [segment for segment in path.split("/") if segment]
        for segment in segments:
            if NotebookLMEndpointDiscoverer._looks_like_entity_id(segment):
                ids.append(segment)
        for key, value in query.items():
            key_lower = key.lower()
            values = value if isinstance(value, list) else [value]
            if "notebook" not in key_lower:
                continue
            for item in values:
                text = str(item)
                if NotebookLMEndpointDiscoverer._looks_like_entity_id(text):
                    ids.append(text)
        return list(dict.fromkeys(ids))

    @staticmethod
    def _contains_notebook_selector(
        path: str,
        query: dict[str, Any],
        raw_id: str | None,
    ) -> bool:
        if raw_id is None:
            return False
        if raw_id in path:
            return True
        return raw_id in json.dumps(query, sort_keys=True)

    @staticmethod
    def _looks_like_entity_id(value: str) -> bool:
        stripped = value.strip()
        if len(stripped) < 6:
            return False
        return stripped.replace("-", "").replace("_", "").isalnum()

    @staticmethod
    def _template_request(
        *,
        path: str,
        query: dict[str, Any],
        notebook_ids: list[str] | None = None,
        artifact_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        templated_path = path
        templated_query = json.loads(json.dumps(query))
        replacements = [
            ("{notebook_id}", notebook_ids or []),
            ("{artifact_id}", artifact_ids or []),
        ]
        for placeholder, ids in replacements:
            for raw_id in ids:
                if not raw_id:
                    continue
                templated_path = templated_path.replace(raw_id, placeholder)
                templated_query = NotebookLMEndpointDiscoverer._replace_in_value(
                    templated_query,
                    raw_id,
                    placeholder,
                )
        return {"path": templated_path.lstrip("/"), "query": templated_query}

    @staticmethod
    def _replace_in_value(value: Any, needle: str, replacement: str) -> Any:
        if isinstance(value, dict):
            return {
                key: NotebookLMEndpointDiscoverer._replace_in_value(item, needle, replacement)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                NotebookLMEndpointDiscoverer._replace_in_value(item, needle, replacement)
                for item in value
            ]
        if isinstance(value, str):
            return value.replace(needle, replacement)
        return value

    @staticmethod
    def _find_first_notebook_url(
        candidates: list[DiscoveredEndpointCandidate],
    ) -> str | None:
        for candidate in candidates:
            if candidate.endpoint_name == "list_notebooks" and candidate.sample_notebook_url:
                return candidate.sample_notebook_url
            if candidate.endpoint_name == "get_notebook" and candidate.sample_notebook_url:
                return candidate.sample_notebook_url
        return None

    def _refresh_session_from_browser(self, context: Any, page: Any) -> None:
        cookies = [
            cookie
            for cookie in context.cookies()
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
                    notebooklm_origin=self._base_url,
                )
            )
