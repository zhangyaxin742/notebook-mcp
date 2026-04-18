from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from retrieval.models import CanonicalChunk, CanonicalDocument


@dataclass(frozen=True)
class ChunkingPolicy:
    max_chars: int = 900
    overlap_chars: int = 150
    min_chunk_chars: int = 200

    def __post_init__(self) -> None:
        if self.max_chars <= 0:
            raise ValueError("max_chars must be positive.")
        if self.overlap_chars < 0:
            raise ValueError("overlap_chars must be zero or positive.")
        if self.overlap_chars >= self.max_chars:
            raise ValueError("overlap_chars must be smaller than max_chars.")
        if self.min_chunk_chars <= 0:
            raise ValueError("min_chunk_chars must be positive.")


@dataclass(frozen=True)
class _Span:
    text: str
    start: int
    end: int


def build_chunks(
    document: CanonicalDocument,
    policy: ChunkingPolicy | None = None,
) -> list[CanonicalChunk]:
    active_policy = policy or ChunkingPolicy()
    text = _normalize_text(document.text)
    if not text:
        return []

    spans = _collect_spans(text, active_policy.max_chars)
    chunks: list[CanonicalChunk] = []
    window: list[_Span] = []
    current_size = 0

    for span in spans:
        span_size = len(span.text)
        if window and current_size + span_size > active_policy.max_chars:
            chunks.append(_make_chunk(document, len(chunks), window))
            window = _overlap_window(window, active_policy.overlap_chars)
            current_size = sum(len(existing.text) for existing in window)

        window.append(span)
        current_size += span_size

    if window:
        if (
            chunks
            and current_size < active_policy.min_chunk_chars
            and len(chunks[-1].text) + current_size <= active_policy.max_chars
        ):
            merged = chunks.pop()
            previous_span = _Span(
                text=merged.text,
                start=merged.char_start or 0,
                end=merged.char_end or len(merged.text),
            )
            chunks.append(_make_chunk(document, len(chunks), [previous_span, *window]))
        else:
            chunks.append(_make_chunk(document, len(chunks), window))

    return chunks


def _normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").strip()


def _collect_spans(text: str, max_chars: int) -> list[_Span]:
    spans: list[_Span] = []
    paragraph_pattern = re.compile(r"\S(?:.*?\S)?(?=(?:\n{2,})|$)", re.DOTALL)

    for paragraph_match in paragraph_pattern.finditer(text):
        paragraph = paragraph_match.group(0)
        start = paragraph_match.start()
        if len(paragraph) <= max_chars:
            spans.append(_Span(text=paragraph, start=start, end=paragraph_match.end()))
            continue

        spans.extend(_split_large_paragraph(paragraph, start, max_chars))

    return spans


def _split_large_paragraph(paragraph: str, offset: int, max_chars: int) -> list[_Span]:
    spans: list[_Span] = []
    sentence_pattern = re.compile(r".+?(?:[.!?](?=\s)|$)", re.DOTALL)

    for sentence_match in sentence_pattern.finditer(paragraph):
        sentence = sentence_match.group(0).strip()
        if not sentence:
            continue

        start = offset + sentence_match.start()
        if len(sentence) <= max_chars:
            spans.append(_Span(text=sentence, start=start, end=offset + sentence_match.end()))
            continue

        spans.extend(_split_large_sentence(sentence, start, max_chars))

    return spans


def _split_large_sentence(sentence: str, offset: int, max_chars: int) -> list[_Span]:
    spans: list[_Span] = []
    words = list(re.finditer(r"\S+\s*", sentence))
    window: list[re.Match[str]] = []
    current_size = 0

    for word in words:
        word_text = word.group(0)
        if window and current_size + len(word_text) > max_chars:
            spans.append(
                _Span(
                    text="".join(match.group(0) for match in window).strip(),
                    start=offset + window[0].start(),
                    end=offset + window[-1].end(),
                )
            )
            window = []
            current_size = 0

        window.append(word)
        current_size += len(word_text)

    if window:
        spans.append(
            _Span(
                text="".join(match.group(0) for match in window).strip(),
                start=offset + window[0].start(),
                end=offset + window[-1].end(),
            )
        )

    return spans


def _overlap_window(window: list[_Span], overlap_chars: int) -> list[_Span]:
    if overlap_chars == 0:
        return []

    retained: list[_Span] = []
    retained_size = 0

    for span in reversed(window):
        retained.insert(0, span)
        retained_size += len(span.text)
        if retained_size >= overlap_chars:
            break

    return retained


def _make_chunk(
    document: CanonicalDocument,
    chunk_index: int,
    spans: list[_Span],
) -> CanonicalChunk:
    chunk_text = "\n\n".join(span.text.strip() for span in spans if span.text.strip())
    char_start = spans[0].start
    char_end = spans[-1].end

    return CanonicalChunk(
        id=f"nlm:chunk:{document.id}:{chunk_index}",
        document_id=document.id,
        notebook_id=document.notebook_id,
        chunk_index=chunk_index,
        text=chunk_text,
        char_start=char_start,
        char_end=char_end,
        token_count_estimate=len(re.findall(r"\w+", chunk_text)),
        content_sha256=hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
        metadata={
            "document_kind": document.document_kind,
            "document_title": document.title,
            "origin_type": document.origin_type,
            "origin_id": document.origin_id,
        },
    )

