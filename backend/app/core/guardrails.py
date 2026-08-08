from __future__ import annotations

import math
import re
from dataclasses import dataclass
from itertools import combinations
from typing import Any

import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

from app.config import settings
from app.core.embedder import embedder


@dataclass
class GuardrailResult:
    answer: str
    confidence: float
    confidence_breakdown: dict[str, float]
    refused: bool


@dataclass
class RefusalResponse(GuardrailResult):
    pass


class ConfidenceScorer:
    def __init__(self) -> None:
        self._weights = {
            "retrieval_score": 0.35,
            "chunk_agreement": 0.25,
            "answer_coverage": 0.25,
            "source_count": 0.15,
        }
        self._ensure_nltk_resources()
        self._stopwords = set(stopwords.words("english"))

    def evaluate(self, answer: str, chunks: list[Any]) -> GuardrailResult:
        breakdown = self._compute_breakdown(answer=answer, chunks=chunks)

        confidence = 0.0
        for key, weight in self._weights.items():
            confidence += breakdown[key] * weight

        if self._has_absent_entity(answer=answer, chunks=chunks):
            confidence -= 0.2

        confidence = self._clamp01(confidence)

        if confidence < settings.CONFIDENCE_REFUSAL_THRESHOLD:
            return RefusalResponse(
                answer="Not found in documents.",
                confidence=confidence,
                confidence_breakdown=breakdown,
                refused=True,
            )

        if confidence < settings.CONFIDENCE_LOW_THRESHOLD:
            return GuardrailResult(
                answer=f"[Low confidence] {answer}",
                confidence=confidence,
                confidence_breakdown=breakdown,
                refused=False,
            )

        return GuardrailResult(
            answer=answer,
            confidence=confidence,
            confidence_breakdown=breakdown,
            refused=False,
        )

    def score(self, answer: str, chunks: list[Any]) -> GuardrailResult:
        return self.evaluate(answer=answer, chunks=chunks)

    def _compute_breakdown(self, answer: str, chunks: list[Any]) -> dict[str, float]:
        return {
            "retrieval_score": self._retrieval_score(chunks),
            "chunk_agreement": self._chunk_agreement(chunks),
            "answer_coverage": self._answer_coverage(answer=answer, chunks=chunks),
            "source_count": self._source_count(chunks),
        }

    def _retrieval_score(self, chunks: list[Any]) -> float:
        top = chunks[:3]
        if not top:
            return 0.0

        normalized_scores: list[float] = []
        for chunk in top:
            raw = float(getattr(chunk, "reranker_score", 0.0) or 0.0)
            normalized_scores.append(self._sigmoid(raw))

        return self._clamp01(sum(normalized_scores) / len(normalized_scores))

    def _chunk_agreement(self, chunks: list[Any]) -> float:
        top = chunks[:3]
        if len(top) < 2:
            return 0.0

        vectors = embedder.embed_batch([str(getattr(chunk, "text", "")) for chunk in top])
        if len(vectors) < 2:
            return 0.0

        sims: list[float] = []
        for i, j in combinations(range(len(vectors)), 2):
            sim = self._dot(vectors[i], vectors[j])
            # Map cosine similarity from [-1, 1] to [0, 1].
            sims.append((sim + 1.0) / 2.0)

        if not sims:
            return 0.0
        return self._clamp01(sum(sims) / len(sims))

    def _answer_coverage(self, answer: str, chunks: list[Any]) -> float:
        tokens = [t.lower() for t in word_tokenize(answer or "") if t.strip()]
        filtered = [t for t in tokens if (t not in self._stopwords and re.search(r"[a-z0-9]", t))]

        if not filtered:
            return 0.0

        source_text = " ".join(str(getattr(chunk, "text", "")) for chunk in chunks).lower()
        covered = sum(1 for token in filtered if token in source_text)
        return self._clamp01(covered / len(filtered))

    @staticmethod
    def _source_count(chunks: list[Any]) -> float:
        sources = {str(getattr(chunk, "source_filename", "")).strip() for chunk in chunks if getattr(chunk, "source_filename", None)}
        if len(sources) >= 2:
            return 1.0
        if len(sources) == 1:
            return 0.5
        return 0.0

    def _has_absent_entity(self, answer: str, chunks: list[Any]) -> bool:
        entities = self._extract_entities(answer)
        if not entities:
            return False

        source_text = " ".join(str(getattr(chunk, "text", "")) for chunk in chunks).lower()
        for entity in entities:
            if entity.lower() not in source_text:
                return True
        return False

    @staticmethod
    def _extract_entities(answer: str) -> set[str]:
        text = answer or ""
        entities: set[str] = set()

        number_pattern = re.compile(r"\b\d+(?:[.,]\d+)?\b")
        date_pattern = re.compile(
            r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|"
            r"January|February|March|April|June|July|August|September|October|November|December)"
            r"\s+\d{1,2},?\s+\d{4})\b",
            flags=re.IGNORECASE,
        )
        cap_name_pattern = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\b")

        entities.update(number_pattern.findall(text))
        entities.update(date_pattern.findall(text))
        entities.update(cap_name_pattern.findall(text))

        # Remove obvious non-entities from capitalized matches.
        filtered = {e.strip() for e in entities if e and e.strip() and e.strip().lower() not in {"not", "found", "documents"}}
        return filtered

    @staticmethod
    def _dot(vec_a: list[float], vec_b: list[float]) -> float:
        return float(sum(a * b for a, b in zip(vec_a, vec_b)))

    @staticmethod
    def _sigmoid(value: float) -> float:
        if value >= 0:
            z = math.exp(-value)
            return 1.0 / (1.0 + z)
        z = math.exp(value)
        return z / (1.0 + z)

    @staticmethod
    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @staticmethod
    def _ensure_nltk_resources() -> None:
        for resource_path, package in (
            ("tokenizers/punkt_tab/english", "punkt_tab"),
            ("tokenizers/punkt/english.pickle", "punkt"),
            ("corpora/stopwords", "stopwords"),
        ):
            try:
                nltk.data.find(resource_path)
            except LookupError:
                try:
                    nltk.download(package, quiet=True)
                except Exception:
                    pass


confidence_scorer = ConfidenceScorer()
