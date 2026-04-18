from __future__ import annotations

from typing import Any, Mapping, Protocol


RawNotebookBundle = Mapping[str, Any]


class NotebookConnector(Protocol):
    def fetch_notebook(self, notebook_id: str) -> RawNotebookBundle:
        """Return one raw NotebookLM notebook bundle for sync."""
