from __future__ import annotations

from importlib import import_module
from time import monotonic

from .config import AuthRuntimePaths
from .models import NotebookLMSession, utc_now_iso
from .storage import SessionStore


class PlaywrightUnavailableError(RuntimeError):
    pass


class LoginBootstrapError(RuntimeError):
    pass


class PlaywrightLoginBootstrap:
    def __init__(
        self,
        paths: AuthRuntimePaths,
        session_store: SessionStore,
        notebooklm_url: str = "https://notebooklm.google.com/",
    ) -> None:
        self._paths = paths
        self._session_store = session_store
        self._notebooklm_url = notebooklm_url

    def is_available(self) -> bool:
        try:
            import_module("playwright.sync_api")
        except ModuleNotFoundError:
            return False
        return True

    def bootstrap_login(
        self,
        timeout_seconds: int = 300,
        headless: bool = False,
    ) -> NotebookLMSession:
        try:
            sync_api = import_module("playwright.sync_api")
        except ModuleNotFoundError as exc:
            raise PlaywrightUnavailableError(
                "Playwright is not installed; login bootstrap is unavailable."
            ) from exc

        self._paths.ensure_directories()
        sync_playwright = getattr(sync_api, "sync_playwright")

        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(self._paths.browser_profile_dir),
                headless=headless,
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(self._notebooklm_url, wait_until="domcontentloaded")
                deadline = monotonic() + timeout_seconds

                while monotonic() < deadline:
                    cookies = [
                        cookie
                        for cookie in context.cookies()
                        if "google" in str(cookie.get("domain", "")).lower()
                        or "notebooklm" in str(cookie.get("domain", "")).lower()
                    ]
                    current_url = page.url
                    if cookies and "accounts.google.com" not in current_url:
                        try:
                            user_agent = page.evaluate("() => navigator.userAgent")
                        except Exception:
                            user_agent = None
                        session = NotebookLMSession(
                            cookies=tuple(cookies),
                            headers={
                                "origin": "https://notebooklm.google.com",
                                "referer": self._notebooklm_url,
                            },
                            user_agent=user_agent,
                            notebooklm_origin="https://notebooklm.google.com",
                            updated_at=utc_now_iso(),
                            metadata={"bootstrap_url": current_url},
                        )
                        self._session_store.save(session)
                        return session
                    page.wait_for_timeout(1000)
            finally:
                context.close()

        raise LoginBootstrapError(
            "Timed out waiting for an authenticated NotebookLM browser session."
        )
