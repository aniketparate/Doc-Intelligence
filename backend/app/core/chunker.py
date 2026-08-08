from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import nltk
from nltk.tokenize import sent_tokenize
from sentence_transformers import SentenceTransformer

from app.config import settings


@dataclass(slots=True)
class Chunk:
    text: str
    window_text: str
    context_prefix: str
    page_num: int | None
    chunk_index: int
    total_chunks: int
    reranker_score: float | None = None


@dataclass(slots=True)
class _SentenceUnit:
    text: str
    page_num: int | None


@dataclass(slots=True)
class _Span:
    start: int
    end: int


class Chunker:
    def __init__(self) -> None:
        self._semantic_similarity_threshold = 0.7
        self._semantic_target_min_tokens = 256
        self._semantic_hard_max_tokens = 512
        self._fallback_chunk_size = 400
        self._fallback_overlap = 80
        self._embedder: SentenceTransformer | None = None

    def chunk(self, text_elements: list[Any], doc: Any) -> list[Chunk]:
        sentences = self._to_sentence_units(text_elements)
        if not sentences:
            return []

        semantic_spans = self._semantic_chunk_spans(sentences)
        if len(semantic_spans) < 3:
            spans = self._fallback_recursive_spans(sentences)
        else:
            spans = semantic_spans

        return self._build_chunks_from_spans(spans=spans, sentences=sentences, doc=doc)

    def _to_sentence_units(self, text_elements: list[Any]) -> list[_SentenceUnit]:
        self._ensure_nltk_punkt()

        out: list[_SentenceUnit] = []
        for element in text_elements:
            raw_text = (getattr(element, "text", "") or "").strip()
            if not raw_text:
                continue

            page_num = getattr(element, "page_num", None)
            for sentence in sent_tokenize(raw_text):
                clean_sentence = sentence.strip()
                if clean_sentence:
                    out.append(_SentenceUnit(text=clean_sentence, page_num=page_num))

        return out

    @staticmethod
    def _ensure_nltk_punkt() -> None:
        try:
            nltk.data.find("tokenizers/punkt_tab/english")
        except LookupError:
            try:
                nltk.download("punkt_tab", quiet=True)
            except Exception:
                pass

        try:
            nltk.data.find("tokenizers/punkt/english.pickle")
        except LookupError:
            try:
                nltk.download("punkt", quiet=True)
            except Exception:
                pass

    def _semantic_chunk_spans(self, sentences: list[_SentenceUnit]) -> list[_Span]:
        if not sentences:
            return []

        embeddings = self._encode_sentences([s.text for s in sentences])
        if embeddings is None:
            return []

        spans: list[_Span] = []
        current_start = 0
        current_tokens = self._token_count(sentences[0].text)

        for idx in range(1, len(sentences)):
            sim = self._cosine_similarity(embeddings[idx - 1], embeddings[idx])
            sentence_tokens = self._token_count(sentences[idx].text)

            should_merge = sim > self._semantic_similarity_threshold
            within_max = (current_tokens + sentence_tokens) <= self._semantic_hard_max_tokens

            if should_merge and within_max:
                current_tokens += sentence_tokens
                continue

            spans.append(_Span(start=current_start, end=idx - 1))
            current_start = idx
            current_tokens = sentence_tokens

        spans.append(_Span(start=current_start, end=len(sentences) - 1))

        spans = self._split_oversized_spans(spans, sentences, self._semantic_hard_max_tokens)
        spans = self._merge_small_semantic_spans(spans, sentences)

        return spans

    def _encode_sentences(self, sentences: list[str]):
        try:
            if self._embedder is None:
                self._embedder = SentenceTransformer(settings.EMBEDDING_MODEL, device=settings.EMBEDDING_DEVICE)
            return self._embedder.encode(
                sentences,
                batch_size=settings.EMBEDDING_BATCH_SIZE,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        except Exception:
            return None

    @staticmethod
    def _cosine_similarity(vec_a, vec_b) -> float:
        return float(vec_a @ vec_b)

    def _split_oversized_spans(self, spans: list[_Span], sentences: list[_SentenceUnit], max_tokens: int) -> list[_Span]:
        out: list[_Span] = []
        for span in spans:
            running_start = span.start
            running_tokens = 0

            for idx in range(span.start, span.end + 1):
                sentence_tokens = self._token_count(sentences[idx].text)
                if running_tokens > 0 and running_tokens + sentence_tokens > max_tokens:
                    out.append(_Span(start=running_start, end=idx - 1))
                    running_start = idx
                    running_tokens = sentence_tokens
                else:
                    running_tokens += sentence_tokens

            out.append(_Span(start=running_start, end=span.end))

        return out

    def _merge_small_semantic_spans(self, spans: list[_Span], sentences: list[_SentenceUnit]) -> list[_Span]:
        if not spans:
            return []

        merged: list[_Span] = []
        idx = 0
        while idx < len(spans):
            span = spans[idx]
            span_tokens = self._span_token_count(span, sentences)

            if span_tokens < self._semantic_target_min_tokens and idx < len(spans) - 1:
                next_span = spans[idx + 1]
                combined = _Span(start=span.start, end=next_span.end)
                combined_tokens = self._span_token_count(combined, sentences)
                if combined_tokens <= self._semantic_hard_max_tokens:
                    merged.append(combined)
                    idx += 2
                    continue

            merged.append(span)
            idx += 1

        return merged

    def _fallback_recursive_spans(self, sentences: list[_SentenceUnit]) -> list[_Span]:
        sentence_texts = [s.text for s in sentences]
        full_text = " ".join(sentence_texts)
        separators = ["\n\n", "\n", ". ", " "]

        split_texts = self._recursive_split_text(
            text=full_text,
            separators=separators,
            max_tokens=self._fallback_chunk_size,
        )

        chunks_with_overlap = self._apply_overlap(split_texts, overlap_tokens=self._fallback_overlap)

        spans: list[_Span] = []
        cursor = 0
        for chunk_text in chunks_with_overlap:
            chunk_sentences = [s.strip() for s in sent_tokenize(chunk_text) if s.strip()]
            if not chunk_sentences:
                continue

            start = cursor
            end = min(len(sentences) - 1, start + len(chunk_sentences) - 1)
            spans.append(_Span(start=start, end=end))

            cursor = max(start + 1, end + 1 - 2)
            if cursor >= len(sentences):
                break

        if not spans:
            spans = [_Span(start=0, end=len(sentences) - 1)]

        return self._split_oversized_spans(spans, sentences, self._fallback_chunk_size)

    def _recursive_split_text(self, text: str, separators: list[str], max_tokens: int) -> list[str]:
        if self._token_count(text) <= max_tokens:
            return [text.strip()]

        if not separators:
            return self._hard_split_by_tokens(text, max_tokens)

        sep = separators[0]
        parts = text.split(sep)
        if len(parts) == 1:
            return self._recursive_split_text(text, separators[1:], max_tokens)

        merged_parts: list[str] = []
        current = ""
        for part in parts:
            candidate = part if not current else f"{current}{sep}{part}"
            if self._token_count(candidate) <= max_tokens:
                current = candidate
            else:
                if current:
                    merged_parts.append(current.strip())
                current = part
        if current:
            merged_parts.append(current.strip())

        output: list[str] = []
        for part in merged_parts:
            if self._token_count(part) <= max_tokens:
                output.append(part)
            else:
                output.extend(self._recursive_split_text(part, separators[1:], max_tokens))
        return [item for item in output if item]

    def _hard_split_by_tokens(self, text: str, max_tokens: int) -> list[str]:
        tokens = self._tokenize(text)
        out: list[str] = []
        for idx in range(0, len(tokens), max_tokens):
            out.append(" ".join(tokens[idx : idx + max_tokens]))
        return out

    def _apply_overlap(self, chunks: list[str], overlap_tokens: int) -> list[str]:
        out: list[str] = []
        prev_tokens: list[str] = []

        for chunk in chunks:
            chunk_tokens = self._tokenize(chunk)
            if prev_tokens:
                chunk_tokens = prev_tokens[-overlap_tokens:] + chunk_tokens
            trimmed = chunk_tokens[: self._fallback_chunk_size]
            out.append(" ".join(trimmed))
            prev_tokens = self._tokenize(chunk)

        return out

    def _build_chunks_from_spans(self, spans: list[_Span], sentences: list[_SentenceUnit], doc: Any) -> list[Chunk]:
        chunks: list[Chunk] = []
        doc_type = str(getattr(doc, "doc_type", "") or "Unknown")
        filename = str(getattr(doc, "filename", "document"))

        for idx, span in enumerate(spans):
            sentence_slice = sentences[span.start : span.end + 1]
            text = " ".join(s.text for s in sentence_slice).strip()
            if not text:
                continue

            window_start = max(0, span.start - 2)
            window_end = min(len(sentences) - 1, span.end + 2)
            window_text = " ".join(sentences[i].text for i in range(window_start, window_end + 1)).strip()

            page_num = next((s.page_num for s in sentence_slice if s.page_num is not None), None)
            page_for_prefix = page_num if page_num is not None else 1
            context_prefix = f"[{doc_type}] {filename} | Page {page_for_prefix} | "

            chunks.append(
                Chunk(
                    text=text,
                    window_text=window_text,
                    context_prefix=context_prefix,
                    page_num=page_num,
                    chunk_index=idx,
                    total_chunks=0,
                )
            )

        total = len(chunks)
        return [
            Chunk(
                text=chunk.text,
                window_text=chunk.window_text,
                context_prefix=chunk.context_prefix,
                page_num=chunk.page_num,
                chunk_index=i,
                total_chunks=total,
                reranker_score=chunk.reranker_score,
            )
            for i, chunk in enumerate(chunks)
        ]

    def _span_token_count(self, span: _Span, sentences: list[_SentenceUnit]) -> int:
        return sum(self._token_count(sentences[i].text) for i in range(span.start, span.end + 1))

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"\S+", text)

    def _token_count(self, text: str) -> int:
        return len(self._tokenize(text))


chunker = Chunker()
