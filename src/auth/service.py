from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .bootstrap import PlaywrightLoginBootstrap
from .config import AuthRuntimePaths, resolve_runtime_paths
from .models import AuthValidationResult, NotebookLMSession
from .scrub import scrub_payload
from .storage import SessionStore


@dataclass(frozen=True)
class DoctorReport:
    session_path: str
    browser_profile_dir: str
    session_storage: dict[str, Any]
    session_validation: dict[str, Any]
    playwright_available: bool
    connector_probe: dict[str, Any] | None = None
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class NotebookLMAuthManager:
    def __init__(
        self,
        paths: AuthRuntimePaths | None = None,
        session_store: SessionStore | None = None,
        bootstrapper: PlaywrightLoginBootstrap | None = None,
    ) -> None:
        self.paths = paths or resolve_runtime_paths()
        self.session_store = session_store or SessionStore(self.paths)
        self.bootstrapper = bootstrapper or PlaywrightLoginBootstrap(
            self.paths,
            self.session_store,
        )

    def load_session(self) -> NotebookLMSession | None:
        return self.session_store.load()

    def save_session(self, session: NotebookLMSession) -> None:
        self.session_store.save(session)

    def validate_session(
        self,
        session: NotebookLMSession | None = None,
    ) -> AuthValidationResult:
        active_session = session or self.load_session()
        if active_session is None:
            return AuthValidationResult(
                ok=False,
                code="missing_session",
                message="No NotebookLM session file is present.",
            )
        if not active_session.has_auth_material():
            return AuthValidationResult(
                ok=False,
                code="missing_auth_material",
                message="The saved NotebookLM session does not contain auth cookies.",
                session_summary=active_session.summary(),
            )
        if active_session.is_expired(datetime.now(timezone.utc)):
            return AuthValidationResult(
                ok=False,
                code="auth_expired",
                message="The saved NotebookLM session appears to be expired.",
                session_summary=active_session.summary(),
            )
        return AuthValidationResult(
            ok=True,
            code="ok",
            message="NotebookLM session looks structurally valid.",
            session_summary=active_session.summary(),
        )

    def bootstrap_login(
        self,
        timeout_seconds: int = 300,
        headless: bool = False,
    ) -> NotebookLMSession:
        return self.bootstrapper.bootstrap_login(
            timeout_seconds=timeout_seconds,
            headless=headless,
        )

    def doctor(
        self,
        probe: Callable[[], Any] | None = None,
    ) -> DoctorReport:
        validation = self.validate_session()
        storage_info = self.session_store.describe_storage()
        connector_probe: dict[str, Any] | None = None
        warnings: list[str] = []
        if storage_info.get("warning"):
            warnings.append(str(storage_info["warning"]))
        if probe is not None:
            try:
                probe_result = probe()
            except Exception as exc:
                connector_probe = {
                    "ok": False,
                    "code": getattr(exc, "code", exc.__class__.__name__),
                    "message": str(exc),
                }
            else:
                connector_probe = {
                    "ok": True,
                    "result": scrub_payload(probe_result),
                }
        return DoctorReport(
            session_path=str(self.paths.session_file),
            browser_profile_dir=str(self.paths.browser_profile_dir),
            session_storage=scrub_payload(storage_info),
            session_validation=scrub_payload(validation.__dict__),
            playwright_available=self.bootstrapper.is_available(),
            connector_probe=connector_probe,
            warnings=tuple(warnings),
        )
