from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_DATA_DIR = Path(".local") / "notebook-mcp"
DEFAULT_BROWSER_PROFILE_DIR = DEFAULT_DATA_DIR / "auth" / "browser-profile"


@dataclass(frozen=True)
class AuthRuntimePaths:
    data_root: Path
    auth_dir: Path
    logs_dir: Path
    browser_profile_dir: Path
    session_file: Path

    def ensure_directories(self) -> None:
        self.auth_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.browser_profile_dir.mkdir(parents=True, exist_ok=True)


def _resolve_path(raw_value: str, cwd: Path) -> Path:
    candidate = Path(raw_value).expanduser()
    if not candidate.is_absolute():
        candidate = cwd / candidate
    return candidate.resolve()


def resolve_runtime_paths(cwd: Path | None = None) -> AuthRuntimePaths:
    runtime_cwd = cwd or Path.cwd()
    data_root = _resolve_path(
        os.getenv("NOTEBOOK_MCP_DATA_DIR", str(DEFAULT_DATA_DIR)),
        runtime_cwd,
    )
    browser_profile_dir = _resolve_path(
        os.getenv("NOTEBOOK_MCP_BROWSER_PROFILE_DIR", str(DEFAULT_BROWSER_PROFILE_DIR)),
        runtime_cwd,
    )
    auth_dir = data_root / "auth"
    logs_dir = data_root / "logs"
    return AuthRuntimePaths(
        data_root=data_root,
        auth_dir=auth_dir,
        logs_dir=logs_dir,
        browser_profile_dir=browser_profile_dir,
        session_file=auth_dir / "session.json",
    )
