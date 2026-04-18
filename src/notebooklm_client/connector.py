from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, TypeVar

from src.auth.bootstrap import PlaywrightUnavailableError
from src.auth.service import NotebookLMAuthManager

from .errors import AuthExpiredError, NotebookLMConnectorError, TransportError
from .models import ConnectorHealth, RawArtifact, RawNotebook, RawNotebookBundle, RawSource


class RawNotebookLMConnector(Protocol):
    def probe(self) -> ConnectorHealth: ...

    def list_notebooks(self) -> list[RawNotebook]: ...

    def get_notebook(self, notebook_id: str) -> RawNotebook: ...

    def list_sources(self, notebook_id: str) -> list[RawSource]: ...

    def list_artifacts(self, notebook_id: str) -> list[RawArtifact]: ...

    def get_artifact(self, notebook_id: str, artifact_id: str) -> RawArtifact: ...

    def fetch_notebook_bundle(self, notebook_id: str) -> RawNotebookBundle: ...


ConnectorResult = TypeVar(
    "ConnectorResult",
    ConnectorHealth,
    RawNotebook,
    RawArtifact,
    RawNotebookBundle,
    list[RawNotebook],
    list[RawSource],
    list[RawArtifact],
)


class FailoverNotebookLMConnector:
    def __init__(
        self,
        *,
        http_connector: RawNotebookLMConnector,
        auth_manager: NotebookLMAuthManager,
        playwright_connector: RawNotebookLMConnector | None = None,
        auto_recover_auth: bool = True,
    ) -> None:
        self._http_connector = http_connector
        self._auth_manager = auth_manager
        self._playwright_connector = playwright_connector
        self._auto_recover_auth = auto_recover_auth

    def probe(self) -> ConnectorHealth:
        return self._call_with_failover(lambda connector: connector.probe())

    def list_notebooks(self) -> list[RawNotebook]:
        return self._call_with_failover(lambda connector: connector.list_notebooks())

    def get_notebook(self, notebook_id: str) -> RawNotebook:
        return self._call_with_failover(lambda connector: connector.get_notebook(notebook_id))

    def list_sources(self, notebook_id: str) -> list[RawSource]:
        return self._call_with_failover(lambda connector: connector.list_sources(notebook_id))

    def list_artifacts(self, notebook_id: str) -> list[RawArtifact]:
        return self._call_with_failover(lambda connector: connector.list_artifacts(notebook_id))

    def get_artifact(self, notebook_id: str, artifact_id: str) -> RawArtifact:
        return self._call_with_failover(
            lambda connector: connector.get_artifact(notebook_id, artifact_id)
        )

    def fetch_notebook_bundle(self, notebook_id: str) -> RawNotebookBundle:
        return self._call_with_failover(
            lambda connector: connector.fetch_notebook_bundle(notebook_id)
        )

    def _call_with_failover(
        self,
        operation: Callable[[RawNotebookLMConnector], ConnectorResult],
    ) -> ConnectorResult:
        try:
            return operation(self._http_connector)
        except AuthExpiredError as exc:
            if not self._auto_recover_auth:
                raise
            self._attempt_auth_recovery(exc)
            try:
                return operation(self._http_connector)
            except AuthExpiredError:
                if self._playwright_connector is not None:
                    return operation(self._playwright_connector)
                raise
        except TransportError as exc:
            if self._playwright_connector is not None and exc.retryable:
                return operation(self._playwright_connector)
            raise

    def _attempt_auth_recovery(self, original_error: NotebookLMConnectorError) -> None:
        try:
            self._auth_manager.bootstrap_login()
        except (PlaywrightUnavailableError, RuntimeError) as exc:
            raise AuthExpiredError(
                "NotebookLM auth recovery failed.",
                details={
                    "original_error": original_error.code,
                    "recovery_error": str(exc),
                },
            ) from exc
