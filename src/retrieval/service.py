from __future__ import annotations

from collections import defaultdict

from index.chunking import ChunkingPolicy, build_chunks
from index.embeddings import EmbeddingBackend, HashingEmbeddingBackend, SemanticChunkIndex
from index.lexical import SqliteFtsLexicalIndex

from .models import CanonicalChunk, CanonicalDocument, SearchResult
from .repository import CanonicalDocumentRepository


class RetrievalService:
    def __init__(
        self,
        repository: CanonicalDocumentRepository,
        *,
        chunking_policy: ChunkingPolicy | None = None,
        embedding_backend: EmbeddingBackend | None = None,
        lexical_weight: float = 0.6,
        semantic_weight: float = 0.4,
    ) -> None:
        if lexical_weight <= 0 or semantic_weight <= 0:
            raise ValueError("Hybrid ranking weights must be positive.")

        total_weight = lexical_weight + semantic_weight
        self._lexical_weight = lexical_weight / total_weight
        self._semantic_weight = semantic_weight / total_weight
        self._repository = repository
        self._chunking_policy = chunking_policy or ChunkingPolicy()
        self._embedding_backend = embedding_backend or HashingEmbeddingBackend()
        self._lexical_index = SqliteFtsLexicalIndex()
        self._semantic_index = SemanticChunkIndex(self._embedding_backend)
        self._documents_by_id: dict[str, CanonicalDocument] = {}
        self._chunks_by_id: dict[str, CanonicalChunk] = {}
        self._indexed = False

    def refresh(self) -> None:
        documents = tuple(self._repository.iter_documents())
        chunks: list[CanonicalChunk] = []
        documents_by_id: dict[str, CanonicalDocument] = {}

        for document in documents:
            documents_by_id[document.id] = document
            chunks.extend(build_chunks(document, self._chunking_policy))

        self._documents_by_id = documents_by_id
        self._chunks_by_id = {chunk.id: chunk for chunk in chunks}
        self._lexical_index.replace(chunks)
        self._semantic_index.replace(chunks)
        self._indexed = True

    def fetch(self, document_id: str) -> CanonicalDocument | None:
        return self._repository.get_document(document_id)

    def list_documents(
        self,
        *,
        notebook_id: str | None = None,
        document_kind: str | None = None,
    ) -> list[CanonicalDocument]:
        return list(
            self._repository.iter_documents(
                notebook_id=notebook_id,
                document_kind=document_kind,
            )
        )

    def search(
        self,
        query: str,
        *,
        notebook_id: str | None = None,
        document_kind: str | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        self._ensure_index()

        candidate_limit = max(limit * 4, 20)
        lexical_hits = self._lexical_index.search(
            query,
            notebook_id=notebook_id,
            document_kind=document_kind,
            limit=candidate_limit,
        )
        semantic_hits = self._semantic_index.search(
            query,
            notebook_id=notebook_id,
            document_kind=document_kind,
            limit=candidate_limit,
        )

        lexical_scores: dict[str, float] = defaultdict(float)
        semantic_scores: dict[str, float] = defaultdict(float)
        matched_chunks: dict[str, set[str]] = defaultdict(set)

        for hit in lexical_hits:
            lexical_scores[hit.document_id] = max(lexical_scores[hit.document_id], hit.score)
            matched_chunks[hit.document_id].add(hit.chunk_id)

        for hit in semantic_hits:
            semantic_scores[hit.document_id] = max(semantic_scores[hit.document_id], hit.score)
            matched_chunks[hit.document_id].add(hit.chunk_id)

        document_ids = sorted(
            set(lexical_scores) | set(semantic_scores),
            key=lambda document_id: (
                -self._hybrid_score(
                    lexical_scores.get(document_id, 0.0),
                    semantic_scores.get(document_id, 0.0),
                ),
                self._documents_by_id[document_id].title.lower(),
                document_id,
            ),
        )

        results: list[SearchResult] = []
        for document_id in document_ids[:limit]:
            document = self._documents_by_id[document_id]
            lexical_score = lexical_scores.get(document_id, 0.0)
            semantic_score = semantic_scores.get(document_id, 0.0)
            results.append(
                SearchResult(
                    id=document.id,
                    notebook_id=document.notebook_id,
                    title=document.title,
                    url=document.url,
                    document_kind=document.document_kind,
                    origin_type=document.origin_type,
                    origin_id=document.origin_id,
                    score=self._hybrid_score(lexical_score, semantic_score),
                    lexical_score=lexical_score,
                    semantic_score=semantic_score,
                    matched_chunk_ids=tuple(sorted(matched_chunks[document_id])),
                )
            )

        return results

    def search_notebook(
        self,
        notebook_id: str,
        query: str,
        *,
        document_kind: str | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        return self.search(
            query,
            notebook_id=notebook_id,
            document_kind=document_kind,
            limit=limit,
        )

    def close(self) -> None:
        self._lexical_index.close()

    def _ensure_index(self) -> None:
        if not self._indexed:
            self.refresh()

    def _hybrid_score(self, lexical_score: float, semantic_score: float) -> float:
        return (self._lexical_weight * lexical_score) + (self._semantic_weight * semantic_score)
