from __future__ import annotations

from typing import Any

from sentence_transformers import CrossEncoder

from app.config import settings


class Reranker:
    def __init__(self) -> None:
        self._model = CrossEncoder(
            settings.RERANKER_MODEL,
            device=settings.EFFECTIVE_RERANKER_DEVICE,
        )

    def rerank(self, query: str, chunks: list[Any]) -> list[Any]:
        if not chunks:
            return []

        pairs = [(query, str(getattr(chunk, "text", ""))) for chunk in chunks]
        scores = self._model.predict(pairs, convert_to_numpy=True, show_progress_bar=False)

        scored_chunks: list[Any] = []
        for chunk, score in zip(chunks, scores):
            chunk.reranker_score = float(score)
            scored_chunks.append(chunk)

        scored_chunks.sort(key=lambda c: c.reranker_score if c.reranker_score is not None else float("-inf"), reverse=True)
        return scored_chunks


reranker = Reranker()
