from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


DEFAULT_DATA_DIR = Path(".local/notebook-mcp")
DEFAULT_DB_PATH = Path("db/notebook_mcp.sqlite3")
DEFAULT_SNAPSHOTS_PATH = Path("snapshots")


@dataclass(frozen=True)
class StorePaths:
    data_dir: Path
    db_path: Path
    snapshots_dir: Path

    @classmethod
    def from_env(cls) -> "StorePaths":
        data_dir = Path(os.getenv("NOTEBOOK_MCP_DATA_DIR", DEFAULT_DATA_DIR))
        db_override = os.getenv("NOTEBOOK_MCP_DB_PATH")
        db_path = Path(db_override) if db_override else data_dir / DEFAULT_DB_PATH
        snapshots_dir = data_dir / DEFAULT_SNAPSHOTS_PATH
        return cls(data_dir=data_dir, db_path=db_path, snapshots_dir=snapshots_dir)

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
