from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.guardrails import ConfidenceScorer


pytestmark = pytest.mark.asyncio


def _chunk(text: str, score: float, source: str):
    return SimpleNamespace(text=text, reranker_score=score, source_filename=source)


def test_low_retrieval_score_triggers_refusal(monkeypatch):
    scorer = ConfidenceScorer()

    monkeypatch.setattr(scorer, "_chunk_agreement", lambda chunks: 0.0)
    monkeypatch.setattr(scorer, "_answer_coverage", lambda answer, chunks: 0.0)
    monkeypatch.setattr(scorer, "_source_count", lambda chunks: 0.0)

    chunks = [_chunk("irrelevant text", -20.0, "a.pdf")]
    result = scorer.score(answer="Completely unrelated", chunks=chunks)

    assert result.refused is True
    assert result.answer == "Not found in documents."


def test_confidence_breakdown_sums_correctly(monkeypatch):
    scorer = ConfidenceScorer()

    monkeypatch.setattr(scorer, "_has_absent_entity", lambda answer, chunks: False)

    chunks = [
        _chunk("Penalty is 5000 for late filing", 2.0, "a.pdf"),
        _chunk("Late filing penalty remains 5000", 1.9, "b.pdf"),
        _chunk("Filing deadline and penalty details", 1.8, "c.pdf"),
    ]
    result = scorer.score(answer="Penalty is 5000", chunks=chunks)

    breakdown = result.confidence_breakdown
    weighted_sum = (
        (breakdown["retrieval_score"] * 0.35)
        + (breakdown["chunk_agreement"] * 0.25)
        + (breakdown["answer_coverage"] * 0.25)
        + (breakdown["source_count"] * 0.15)
    )

    assert result.confidence == pytest.approx(weighted_sum, rel=1e-5)


def test_entity_hallucination_check_reduces_score(monkeypatch):
    scorer = ConfidenceScorer()

    chunks = [
        _chunk("The fee is 5000 under Section 234F", 2.0, "a.pdf"),
        _chunk("Section 234F details late filing fee", 1.5, "b.pdf"),
        _chunk("No mention of John Doe", 1.0, "c.pdf"),
    ]

    monkeypatch.setattr(scorer, "_has_absent_entity", lambda answer, chunks: False)
    no_penalty = scorer.score(answer="Fee is 5000", chunks=chunks)

    monkeypatch.setattr(scorer, "_has_absent_entity", lambda answer, chunks: True)
    with_penalty = scorer.score(answer="Fee is 5000 for John Doe", chunks=chunks)

    assert with_penalty.confidence == pytest.approx(max(0.0, no_penalty.confidence - 0.2), rel=1e-5)
