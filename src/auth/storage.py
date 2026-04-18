from __future__ import annotations

import json
from pathlib import Path

from .config import AuthRuntimePaths
from .models import NotebookLMSession


class SessionStore:
    def __init__(self, paths: AuthRuntimePaths) -> None:
        self._paths = paths

    @property
    def session_file(self) -> Path:
        return self._paths.session_file

    def load(self) -> NotebookLMSession | None:
        if not self.session_file.exists():
            return None
        with self.session_file.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return NotebookLMSession.from_dict(payload)

    def save(self, session: NotebookLMSession) -> Path:
        self._paths.ensure_directories()
        with self.session_file.open("w", encoding="utf-8") as handle:
            json.dump(session.to_dict(), handle, indent=2, sort_keys=True)
            handle.write("\n")
        return self.session_file

    def delete(self) -> None:
        if self.session_file.exists():
            self.session_file.unlink()
