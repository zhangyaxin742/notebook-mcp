from __future__ import annotations

from src.index.chunking import ChunkingPolicy, build_chunks
from src.retrieval.models import CanonicalDocument
from src.store.models import ChunkRecord, DocumentRecord


def generate_chunk_records(
    documents: tuple[DocumentRecord, ...],
    *,
    policy: ChunkingPolicy | None = None,
) -> tuple[ChunkRecord, ...]:
    records: list[ChunkRecord] = []

    for document in documents:
        canonical_document = CanonicalDocument(
            id=document.id,
            notebook_id=document.notebook_id,
            origin_type=document.origin_type,
            origin_id=document.origin_id,
            document_kind=document.document_kind,
            title=document.title,
            text=document.text,
            url=document.url,
            content_sha256=document.content_sha256,
            metadata=dict(document.metadata),
        )
        chunk_records = [
            ChunkRecord(
                id=chunk.id,
                document_id=chunk.document_id,
                notebook_id=chunk.notebook_id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                token_count_estimate=chunk.token_count_estimate,
                content_sha256=chunk.content_sha256,
                metadata=dict(chunk.metadata),
            )
            for chunk in build_chunks(canonical_document, policy)
        ]
        records.extend(chunk_records)

    return tuple(sorted(records, key=lambda record: (record.document_id, record.chunk_index, record.id)))
