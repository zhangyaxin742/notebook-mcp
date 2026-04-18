from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from src.auth.config import AuthRuntimePaths
from src.auth.models import NotebookLMSession
from src.auth.service import NotebookLMAuthManager
from src.auth.storage import SessionStore
from src.notebooklm_client.connector import FailoverNotebookLMConnector
from src.notebooklm_client.endpoints import (
    EndpointDefinition,
    NotebookLMEndpointSet,
    ensure_endpoint_config,
)
from src.notebooklm_client.errors import (
    AuthExpiredError,
    EndpointDriftError,
    TransportError,
    UnsupportedShapeError,
)
from src.notebooklm_client.http_connector import NotebookLMHttpConnector


class StubBootstrapper:
    def __init__(self) -> None:
        self.bootstrap_calls = 0

    def bootstrap_login(self, timeout_seconds: int = 300, headless: bool = False) -> NotebookLMSession:
        self.bootstrap_calls += 1
        return valid_session()

    def is_available(self) -> bool:
        return True


class FakeResponse:
    def __init__(
        self,
        *,
        status: int,
        payload: str,
        url: str,
        content_type: str = "application/json",
    ) -> None:
        self.status = status
        self._payload = payload.encode("utf-8")
        self._url = url
        self.headers = {"Content-Type": content_type}

    def read(self) -> bytes:
        return self._payload

    def geturl(self) -> str:
        return self._url

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class SequencedConnector:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls = 0

    def probe(self):
        self.calls += 1
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def list_notebooks(self):
        self.calls += 1
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def get_notebook(self, notebook_id: str):
        raise NotImplementedError

    def list_sources(self, notebook_id: str):
        raise NotImplementedError

    def list_artifacts(self, notebook_id: str):
        raise NotImplementedError

    def get_artifact(self, notebook_id: str, artifact_id: str):
        raise NotImplementedError

    def fetch_notebook_bundle(self, notebook_id: str):
        raise NotImplementedError


def runtime_paths(root: Path) -> AuthRuntimePaths:
    return AuthRuntimePaths(
        data_root=root,
        auth_dir=root / "auth",
        logs_dir=root / "logs",
        browser_profile_dir=root / "auth" / "browser-profile",
        session_file=root / "auth" / "session.json",
    )


def valid_session() -> NotebookLMSession:
    return NotebookLMSession(
        cookies=(
            {
                "name": "__Secure-3PSID",
                "value": "scrubbed-cookie",
                "domain": ".google.com",
                "path": "/",
            },
        ),
        headers={"referer": "https://notebooklm.google.com/"},
        csrf_token="scrubbed-csrf",
        user_agent="NotebookMCPTest/1.0",
    )


def build_http_connector(root: Path) -> tuple[NotebookLMHttpConnector, StubBootstrapper]:
    paths = runtime_paths(root)
    session_store = SessionStore(paths)
    session_store.save(valid_session())
    bootstrapper = StubBootstrapper()
    auth_manager = NotebookLMAuthManager(
        paths=paths,
        session_store=session_store,
        bootstrapper=bootstrapper,
    )
    connector = NotebookLMHttpConnector(
        auth_manager=auth_manager,
        endpoints=NotebookLMEndpointSet(
            list_notebooks=EndpointDefinition(
                path="api/notebooks",
                method="GET",
                root_keys=("notebooks",),
            )
        ),
    )
    return connector, bootstrapper


class Terminal2ConnectorTests(unittest.TestCase):
    def test_http_connector_classifies_auth_expired(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir_name:
            connector, _ = build_http_connector(Path(tempdir_name))

            auth_error = HTTPError(
                url="https://notebooklm.google.com/api/notebooks",
                code=401,
                msg="Unauthorized",
                hdrs={},
                fp=io.BytesIO(b""),
            )
            with patch("src.notebooklm_client.http_connector.urlopen", side_effect=auth_error):
                with self.assertRaises(AuthExpiredError):
                    connector.list_notebooks()

    def test_http_connector_classifies_endpoint_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir_name:
            connector, _ = build_http_connector(Path(tempdir_name))

            drift_error = HTTPError(
                url="https://notebooklm.google.com/api/notebooks",
                code=404,
                msg="Not Found",
                hdrs={},
                fp=io.BytesIO(b""),
            )
            with patch("src.notebooklm_client.http_connector.urlopen", side_effect=drift_error):
                with self.assertRaises(EndpointDriftError):
                    connector.list_notebooks()

    def test_http_connector_classifies_unsupported_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir_name:
            connector, _ = build_http_connector(Path(tempdir_name))

            response = FakeResponse(
                status=200,
                payload=json.dumps({"unexpected": []}),
                url="https://notebooklm.google.com/api/notebooks",
            )
            with patch("src.notebooklm_client.http_connector.urlopen", return_value=response):
                with self.assertRaises(UnsupportedShapeError):
                    connector.list_notebooks()

    def test_session_store_no_longer_writes_plain_json_on_windows(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir_name:
            root = Path(tempdir_name)
            store = SessionStore(runtime_paths(root))
            store.save(valid_session())
            session_text = store.session_file.read_text(encoding="utf-8")

            if os.name == "nt":
                self.assertIn('"storage_kind": "windows_dpapi"', session_text)
                self.assertNotIn("scrubbed-cookie", session_text)
                self.assertNotIn("scrubbed-csrf", session_text)
            else:
                self.assertIn('"storage_kind": "restricted_plaintext"', session_text)

    def test_failover_uses_playwright_on_retryable_transport_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir_name:
            paths = runtime_paths(Path(tempdir_name))
            bootstrapper = StubBootstrapper()
            auth_manager = NotebookLMAuthManager(
                paths=paths,
                session_store=SessionStore(paths),
                bootstrapper=bootstrapper,
            )
            fallback_payload = ["playwright-ok"]
            connector = FailoverNotebookLMConnector(
                http_connector=SequencedConnector(
                    [TransportError("retryable failure", details={"reason": "timeout"}, retryable=True)]
                ),
                auth_manager=auth_manager,
                playwright_connector=SequencedConnector([fallback_payload]),
            )

            self.assertEqual(connector.list_notebooks(), fallback_payload)

    def test_default_endpoint_config_bootstraps_to_runtime_path(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir_name:
            config_path = Path(tempdir_name) / "auth" / "notebooklm_endpoints.json"
            loaded = ensure_endpoint_config(config_path)
            self.assertTrue(config_path.exists())
            self.assertEqual(loaded.source_kind, "default_template")
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["endpoints"]["list_notebooks"]["path"], "api/notebooks")

    def test_failover_retries_after_auth_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir_name:
            paths = runtime_paths(Path(tempdir_name))
            session_store = SessionStore(paths)
            bootstrapper = StubBootstrapper()
            auth_manager = NotebookLMAuthManager(
                paths=paths,
                session_store=session_store,
                bootstrapper=bootstrapper,
            )
            connector = FailoverNotebookLMConnector(
                http_connector=SequencedConnector(
                    [
                        AuthExpiredError("expired"),
                        ["recovered-ok"],
                    ]
                ),
                auth_manager=auth_manager,
            )

            self.assertEqual(connector.list_notebooks(), ["recovered-ok"])
            self.assertEqual(bootstrapper.bootstrap_calls, 1)

    def test_failover_uses_playwright_after_auth_recovery_still_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir_name:
            paths = runtime_paths(Path(tempdir_name))
            session_store = SessionStore(paths)
            bootstrapper = StubBootstrapper()
            auth_manager = NotebookLMAuthManager(
                paths=paths,
                session_store=session_store,
                bootstrapper=bootstrapper,
            )
            connector = FailoverNotebookLMConnector(
                http_connector=SequencedConnector(
                    [
                        AuthExpiredError("expired"),
                        AuthExpiredError("still expired"),
                    ]
                ),
                auth_manager=auth_manager,
                playwright_connector=SequencedConnector([["playwright-fallback"]]),
            )

            self.assertEqual(connector.list_notebooks(), ["playwright-fallback"])
            self.assertEqual(bootstrapper.bootstrap_calls, 1)


if __name__ == "__main__":
    unittest.main()
