from __future__ import annotations

from src.index import EmbeddingBackend, HashingEmbeddingBackend, SemanticChunkIndex, SqliteFtsLexicalIndex
from src.retrieval.models import CanonicalChunk
from src.store.chunk_repository import SQLiteChunkRepository


class PersistedChunkReindexer:
    def __init__(
        self,
        repository: SQLiteChunkRepository,
        *,
        lexical_index: SqliteFtsLexicalIndex | None = None,
        embedding_backend: EmbeddingBackend | None = None,
        semantic_index: SemanticChunkIndex | None = None,
    ) -> None:
        self._repository = repository
        self._lexical_index = lexical_index or SqliteFtsLexicalIndex()
        resolved_backend = embedding_backend or HashingEmbeddingBackend()
        self._semantic_index = semantic_index or SemanticChunkIndex(resolved_backend)

    @property
    def lexical_index(self) -> SqliteFtsLexicalIndex:
        return self._lexical_index

    @property
    def semantic_index(self) -> SemanticChunkIndex:
        return self._semantic_index

    def refresh(
        self,
        *,
        notebook_id: str | None = None,
        document_id: str | None = None,
    ) -> tuple[CanonicalChunk, ...]:
        chunks = tuple(
            self._repository.iter_chunks(
                notebook_id=notebook_id,
                document_id=document_id,
            )
        )
        self._lexical_index.replace(list(chunks))
        self._semantic_index.replace(list(chunks))
        return chunks

    def close(self) -> None:
        self._lexical_index.close()
