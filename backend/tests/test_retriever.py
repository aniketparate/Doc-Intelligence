from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.bm25_index import bm25_service
from app.core.retriever import RetrievedChunk, Retriever


pytestmark = pytest.mark.asyncio


def _chunk(chunk_id: str, text: str, index: int = 0) -> RetrievedChunk:
    return RetrievedChunk(
        doc_id=str(uuid4()),
        project_id=str(uuid4()),
        user_id=str(uuid4()),
        chunk_id=chunk_id,
        text=text,
        window_text=f"window {text}",
        context_prefix="[doc] file.pdf | Page 1 | ",
        page_num=1,
        chunk_index=index,
        total_chunks=3,
        doc_type="text",
        source_filename="file.pdf",
    )


async def test_dense_retrieval_returns_ranked_results(monkeypatch):
    retriever = Retriever()

    monkeypatch.setattr("app.core.retriever.embedder.embed", lambda q: [0.1, 0.2, 0.3])

    async def _mock_search(collection_name, query_vector, limit, filters):
        _ = (collection_name, query_vector, limit, filters)
        return [
            {"score": 0.95, "payload": _chunk("a", "alpha").__dict__},
            {"score": 0.75, "payload": _chunk("b", "beta").__dict__},
        ]

    monkeypatch.setattr("app.core.retriever.vector_store.search", _mock_search)

    results = await retriever._dense_retrieval("project_x", "query", filters=None)

    assert len(results) == 2
    assert results[0].chunk_id == "a"
    assert results[0].dense_score == 0.95
    assert results[1].dense_score == 0.75


async def test_bm25_retrieves_exact_keyword_matches():
    chunks = [
        SimpleNamespace(text="penalty for late filing is five thousand rupees", chunk_id="c1"),
        SimpleNamespace(text="capital gains tax rate details", chunk_id="c2"),
        SimpleNamespace(text="filing deadline extension circular", chunk_id="c3"),
    ]
    index = bm25_service.build(chunks)

    ranked = bm25_service.search(index=index, query="penalty late filing", all_chunks=chunks, top_n=2)

    assert ranked
    assert ranked[0].chunk_id == "c1"


async def test_rrf_merges_and_deduplicates_correctly():
    retriever = Retriever()
    dense = [_chunk("c1", "alpha"), _chunk("c2", "beta")]
    sparse = [_chunk("c2", "beta"), _chunk("c3", "gamma")]

    merged = retriever._rrf_merge(dense_results=dense, sparse_results=sparse, k=60, merged_limit=20)

    chunk_ids = [c.chunk_id for c in merged]
    assert len(chunk_ids) == len(set(chunk_ids))
    assert set(chunk_ids) == {"c1", "c2", "c3"}
    assert merged[0].chunk_id == "c2"


async def test_reranker_improves_ordering(monkeypatch):
    retriever = Retriever()
    dense = [_chunk("c1", "alpha"), _chunk("c2", "beta"), _chunk("c3", "gamma")]
    sparse = []

    monkeypatch.setattr(retriever, "_dense_retrieval", AsyncMock(return_value=dense))
    monkeypatch.setattr(retriever, "_sparse_retrieval", AsyncMock(return_value=sparse))

    def _rerank(query, chunks):
        _ = query
        reordered = list(chunks)
        reordered[0], reordered[1] = reordered[1], reordered[0]
        for i, c in enumerate(reordered):
            c.reranker_score = 1.0 - (i * 0.1)
        return reordered

    monkeypatch.setattr("app.core.retriever.reranker.rerank", _rerank)

    class DummyDB:
        pass

    results = await retriever.retrieve(
        db=DummyDB(),
        collection_name="project_x",
        project_id=str(uuid4()),
        query="question",
        use_hyde=False,
        filters=None,
    )

    assert results
    assert results[0].chunk_id == "c2"
    assert results[0].reranker_score > results[1].reranker_score
