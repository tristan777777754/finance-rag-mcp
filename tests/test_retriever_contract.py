from __future__ import annotations

from rag.retriever import bm25_search, build_bm25_index, hybrid_search


def test_bm25_applies_metadata_filter_before_returning_results(make_chunk):
    target = make_chunk("Apple revenue was 391 billion dollars.")
    other_company = make_chunk(
        "Apple revenue was 999 billion dollars.", ticker="MSFT", fiscal_year="2025"
    )
    chunks = [other_company, target]
    index = build_bm25_index(chunks)

    results = bm25_search(
        "Apple revenue",
        chunks,
        index,
        metadata_filter={"$and": [{"ticker": "AAPL"}, {"fiscal_year": "2024"}]},
    )

    assert [result["metadata"]["ticker"] for result in results] == ["AAPL"]
    assert [result["metadata"]["fiscal_year"] for result in results] == ["2024"]


def test_hybrid_search_runs_both_retrievers_before_rrf(monkeypatch, make_chunk):
    import rag.retriever as retriever

    chunk = make_chunk("Apple total net sales were 391 billion dollars.")
    calls: list[str] = []

    def fake_vector_search(*args, **kwargs):
        calls.append("vector")
        assert kwargs["metadata_filter"] == {"ticker": "AAPL"}
        return [{"text": chunk.text, "metadata": chunk.metadata, "score": 0.9}]

    def fake_bm25_search(*args, **kwargs):
        calls.append("bm25")
        assert kwargs["metadata_filter"] == {"ticker": "AAPL"}
        return [{"text": chunk.text, "metadata": chunk.metadata, "score": 8.0}]

    def fake_rrf(vector_results, bm25_results):
        calls.append("rrf")
        assert calls[:2] == ["vector", "bm25"]
        return [{**vector_results[0], "rrf_score": 0.03}]

    monkeypatch.setattr(retriever, "vector_search", fake_vector_search)
    monkeypatch.setattr(retriever, "bm25_search", fake_bm25_search)
    monkeypatch.setattr(retriever, "reciprocal_rank_fusion", fake_rrf)

    results = hybrid_search(
        "Apple revenue",
        [chunk],
        object(),
        metadata_filter={"ticker": "AAPL"},
    )

    assert calls == ["vector", "bm25", "rrf"]
    assert results[0]["metadata"] == chunk.metadata
    for key in ("ticker", "filing_type", "fiscal_year", "section", "page_number"):
        assert key in results[0]["metadata"]
