from __future__ import annotations

from typing import cast

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import settings


class Embedder:
    def __init__(self) -> None:
        self._model = SentenceTransformer(
            settings.EMBEDDING_MODEL,
            device=settings.EFFECTIVE_EMBEDDING_DEVICE,
        )
        self._batch_size = settings.EMBEDDING_BATCH_SIZE or 32

    @staticmethod
    def _l2_normalize(vectors: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        return vectors / norms

    def embed(self, text: str) -> list[float]:
        vectors = self._model.encode(
            [text],
            batch_size=self._batch_size,
            convert_to_numpy=True,
            normalize_embeddings=False,
            show_progress_bar=False,
        )
        normalized = self._l2_normalize(cast(np.ndarray, vectors))
        return normalized[0].astype(np.float32).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        vectors = self._model.encode(
            texts,
            batch_size=self._batch_size,
            convert_to_numpy=True,
            normalize_embeddings=False,
            show_progress_bar=False,
        )
        normalized = self._l2_normalize(cast(np.ndarray, vectors)).astype(np.float32)
        return normalized.tolist()


embedder = Embedder()
