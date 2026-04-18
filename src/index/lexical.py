from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from src.retrieval.models import CanonicalChunk


@dataclass(frozen=True)
class LexicalChunkHit:
    chunk_id: str
    document_id: str
    score: float


class SqliteFtsLexicalIndex:
    def __init__(self) -> None:
        self._connection = sqlite3.connect(":memory:")
        self._connection.row_factory = sqlite3.Row
        self._create_schema()

    def replace(self, chunks: list[CanonicalChunk]) -> None:
        ordered_chunks = sorted(chunks, key=lambda chunk: (chunk.document_id, chunk.chunk_index, chunk.id))
        rows = [
            (
                chunk.id,
                chunk.document_id,
                chunk.notebook_id,
                str(chunk.metadata.get("document_kind", "")),
                str(chunk.metadata.get("document_title", "")),
                chunk.text,
            )
            for chunk in ordered_chunks
        ]

        with self._connection:
            self._connection.execute("DELETE FROM chunk_fts")
            self._connection.executemany(
                """
                INSERT INTO chunk_fts (
                    chunk_id,
                    document_id,
                    notebook_id,
                    document_kind,
                    title,
                    text
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def search(
        self,
        query: str,
        *,
        notebook_id: str | None = None,
        document_kind: str | None = None,
        limit: int = 20,
    ) -> list[LexicalChunkHit]:
        match_query = _build_match_query(query)
        if not match_query:
            return []

        rows = self._connection.execute(
            """
            SELECT
                chunk_id,
                document_id,
                bm25(chunk_fts, 8.0, 1.0) AS rank
            FROM chunk_fts
            WHERE chunk_fts MATCH ?
              AND (? IS NULL OR notebook_id = ?)
              AND (? IS NULL OR document_kind = ?)
            ORDER BY rank ASC, document_id ASC, chunk_id ASC
            LIMIT ?
            """,
            (
                match_query,
                notebook_id,
                notebook_id,
                document_kind,
                document_kind,
                limit,
            ),
        ).fetchall()

        hits: list[LexicalChunkHit] = []
        for row in rows:
            raw_rank = float(row["rank"])
            hits.append(
                LexicalChunkHit(
                    chunk_id=str(row["chunk_id"]),
                    document_id=str(row["document_id"]),
                    score=_normalize_rank(raw_rank),
                )
            )

        return hits

    def close(self) -> None:
        self._connection.close()

    def _create_schema(self) -> None:
        self._connection.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
                chunk_id UNINDEXED,
                document_id UNINDEXED,
                notebook_id UNINDEXED,
                document_kind UNINDEXED,
                title,
                text,
                tokenize = 'unicode61 remove_diacritics 2'
            )
            """
        )


def _build_match_query(query: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9_]+", query.lower())
    return " ".join(f"{token}*" for token in tokens)


def _normalize_rank(rank: float) -> float:
    return 1.0 / (1.0 + abs(rank))
