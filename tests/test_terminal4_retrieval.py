import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from index.chunking import ChunkingPolicy, build_chunks
from retrieval import CanonicalDocument, InMemoryDocumentRepository, RetrievalService


class StubEmbeddingBackend:
    dimensions = 2

    def embed_documents(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> tuple[float, ...]:
        return self._embed(text)

    def _embed(self, text: str) -> tuple[float, ...]:
        normalized = text.lower()
        if "semantic neighbor query" in normalized:
            return (1.0, 0.0)
        if "vector databases primer" in normalized:
            return (1.0, 0.0)
        if "hybrid ranking query" in normalized:
            return (0.0, 1.0)
        if "retrieval briefing" in normalized:
            return (0.0, 1.0)
        return (0.0, 0.0)


def make_document(
    *,
    document_id: str,
    notebook_id: str,
    document_kind: str,
    title: str,
    text: str,
    url: str,
) -> CanonicalDocument:
    origin_suffix = document_id.split(":")[-1]
    return CanonicalDocument(
        id=document_id,
        notebook_id=notebook_id,
        origin_type="source" if document_kind == "source_summary" else "artifact",
        origin_id=f"nlm:origin:{origin_suffix}",
        document_kind=document_kind,
        title=title,
        text=text,
        url=url,
        content_sha256=(origin_suffix[0] * 64)[:64],
        metadata={"fixture": True},
    )


class Terminal4RetrievalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.documents = [
            make_document(
                document_id="nlm:document:notebook-a:source_summary:paper-1",
                notebook_id="nlm:notebook:notebook-a",
                document_kind="source_summary",
                title="Vector Databases Primer",
                text=(
                    "Vector search improves semantic retrieval for long research notes.\n\n"
                    "Embeddings help rank related content even when exact keywords differ."
                ),
                url="https://example.com/vector-primer",
            ),
            make_document(
                document_id="nlm:document:notebook-a:artifact_text:brief-1",
                notebook_id="nlm:notebook:notebook-a",
                document_kind="artifact_text",
                title="Retrieval Briefing",
                text=(
                    "Hybrid ranking combines lexical matching with semantic similarity.\n\n"
                    "FTS is useful when exact terminology matters."
                ),
                url="notebooklm://notebook/notebook-a/artifact/briefing_doc/brief-1",
            ),
            make_document(
                document_id="nlm:document:notebook-b:source_summary:paper-2",
                notebook_id="nlm:notebook:notebook-b",
                document_kind="source_summary",
                title="Climate Policy Notes",
                text="Carbon border adjustments and industrial policy are central to this notebook.",
                url="https://example.com/climate-policy",
            ),
        ]
        self.repository = InMemoryDocumentRepository(self.documents)
        self.service = RetrievalService(
            self.repository,
            embedding_backend=StubEmbeddingBackend(),
        )

    def tearDown(self) -> None:
        self.service.close()

    def test_chunking_policy_emits_canonical_chunk_ids_and_provenance(self) -> None:
        long_document = make_document(
            document_id="nlm:document:notebook-a:artifact_text:long-1",
            notebook_id="nlm:notebook:notebook-a",
            document_kind="artifact_text",
            title="Long Retrieval Notes",
            text=(
                "A" * 90
                + ". "
                + "B" * 90
                + ".\n\n"
                + "C" * 90
                + ". "
                + "D" * 90
                + "."
            ),
            url="notebooklm://notebook/notebook-a/artifact/note/long-1",
        )

        chunks = build_chunks(
            long_document,
            ChunkingPolicy(max_chars=150, overlap_chars=25, min_chunk_chars=50),
        )

        self.assertGreaterEqual(len(chunks), 2)
        for index, chunk in enumerate(chunks):
            with self.subTest(chunk_id=chunk.id):
                self.assertEqual(chunk.id, f"nlm:chunk:{long_document.id}:{index}")
                self.assertEqual(chunk.document_id, long_document.id)
                self.assertEqual(chunk.notebook_id, long_document.notebook_id)
                self.assertEqual(chunk.metadata["document_kind"], long_document.document_kind)
                self.assertEqual(chunk.metadata["origin_id"], long_document.origin_id)
                self.assertGreater(chunk.token_count_estimate or 0, 0)
                self.assertLess(chunk.char_start or 0, chunk.char_end or 0)

        for previous, current in zip(chunks, chunks[1:]):
            with self.subTest(previous=previous.id, current=current.id):
                self.assertLessEqual(previous.char_start or 0, current.char_start or 0)
                self.assertLess(current.char_start or 0, previous.char_end or 0)

    def test_search_returns_semantic_only_matches_with_stable_fields(self) -> None:
        results = self.service.search("semantic neighbor query", limit=5)

        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.id, "nlm:document:notebook-a:source_summary:paper-1")
        self.assertEqual(result.notebook_id, "nlm:notebook:notebook-a")
        self.assertEqual(result.document_kind, "source_summary")
        self.assertEqual(result.origin_type, "source")
        self.assertEqual(result.origin_id, "nlm:origin:paper-1")
        self.assertGreater(result.semantic_score, 0.0)
        self.assertEqual(result.lexical_score, 0.0)
        self.assertGreater(result.score, 0.0)
        self.assertTrue(result.matched_chunk_ids)

    def test_search_notebook_and_document_kind_filters(self) -> None:
        notebook_results = self.service.search_notebook(
            "nlm:notebook:notebook-a",
            "hybrid ranking query",
            limit=5,
        )
        self.assertEqual([result.id for result in notebook_results], ["nlm:document:notebook-a:artifact_text:brief-1"])

        filtered_results = self.service.search(
            "retrieval",
            notebook_id="nlm:notebook:notebook-a",
            document_kind="artifact_text",
            limit=5,
        )
        self.assertEqual([result.id for result in filtered_results], ["nlm:document:notebook-a:artifact_text:brief-1"])

    def test_fetch_and_list_documents_read_from_canonical_repository(self) -> None:
        fetched = self.service.fetch("nlm:document:notebook-a:artifact_text:brief-1")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.title, "Retrieval Briefing")
        self.assertEqual(
            [document.id for document in self.service.list_documents(notebook_id="nlm:notebook:notebook-a")],
            [
                "nlm:document:notebook-a:artifact_text:brief-1",
                "nlm:document:notebook-a:source_summary:paper-1",
            ],
        )


if __name__ == "__main__":
    unittest.main()
