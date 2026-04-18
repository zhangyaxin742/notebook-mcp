from typing import TYPE_CHECKING, Any

from .models import CanonicalChunk, CanonicalDocument, SearchResult
from .repository import CanonicalDocumentRepository, InMemoryDocumentRepository

if TYPE_CHECKING:
    from .service import RetrievalService

__all__ = [
    "CanonicalChunk",
    "CanonicalDocument",
    "CanonicalDocumentRepository",
    "InMemoryDocumentRepository",
    "RetrievalService",
    "SearchResult",
]


def __getattr__(name: str) -> Any:
    if name == "RetrievalService":
        from .service import RetrievalService

        return RetrievalService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
