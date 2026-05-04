"""
Hybrid retrieval: BM25 + dense vector search, fused with Reciprocal Rank Fusion (RRF).

Flow:
    1. Pre-filter by metadata (ticker, fiscal_year, section)
    2. BM25 keyword retrieval  ──┐
                                  ├──► RRF (k=60) ──► top-k chunks
    3. Dense vector retrieval  ──┘
"""

from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi
from rag.chroma_client import get_chroma_client

_CLIENT = get_chroma_client()
_MODEL = SentenceTransformer("BAAI/bge-small-en-v1.5")

def build_bm25_index(chunks) -> object:
    tokenized = [c.text.lower().split() for c in chunks]
    return BM25Okapi(tokenized)


def vector_search(
    query: str,
    collection_name: str = "sec_filings",
    metadata_filter: dict | None = None,
    top_k: int = 20,
) -> list[dict]:
    """
    Dense vector search against ChromaDB.

    Returns:
        List of result dicts: {"text": str, "metadata": dict, "score": float}
    """
    collection = _CLIENT.get_collection(collection_name)
    query_embedding = _MODEL.encode(query).tolist()
    
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=metadata_filter,
    )
    
    return [
        {"text": doc, "metadata": meta, "score": 1 - dist}
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )
    ]
  
  


def bm25_search(
    query: str,
    chunks,
    bm25_index,
    top_k: int = 20,
) -> list[dict]:
    """
    BM25 keyword search over pre-built index.

    Returns:
        List of result dicts: {"text": str, "metadata": dict, "score": float}
    """
    tokenized_query = query.lower().split()
    scores = bm25_index.get_scores(tokenized_query)
    
    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    
    return [
        {"text": chunks[i].text, "metadata": chunks[i].metadata, "score": scores[i]}
        for i in top_indices
    ]


def reciprocal_rank_fusion(
    *result_lists: list[dict],
    k: int = 60,
) -> list[dict]:
    """
    Merge multiple ranked result lists using RRF.

    RRF score = Σ 1 / (k + rank_i)

    Returns:
        Merged and re-ranked list of result dicts.
    """
    scores: dict[str, float] = {}
    docs: dict[str, dict] = {}

    for results in result_lists:
        for rank, result in enumerate(results):
            key = result["text"][:100]  # use text prefix as unique key
            scores[key] = scores.get(key, 0) + 1 / (k + rank + 1)
            docs[key] = result

    ranked = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
    return [{**docs[k], "rrf_score": scores[k]} for k in ranked]


def hybrid_search(
    query: str,
    chunks,
    bm25_index,
    metadata_filter: dict | None = None,
    top_k: int = 8,
) -> list[dict]:
    """
    Full hybrid search: BM25 + vector → RRF → top_k results.

    Args:
        query:           Natural-language query string.
        chunks:          All ingested Chunk objects (for BM25).
        bm25_index:      Pre-built BM25Okapi index.
        metadata_filter: e.g. {"ticker": "AAPL", "fiscal_year": "2024"}
        top_k:           Number of final results to return (default 8).

    Returns:
        List of top_k result dicts with text + metadata + rrf_score.
    """
    vector_results = vector_search(query, metadata_filter=metadata_filter, top_k=20)
    bm25_results = bm25_search(query, chunks, bm25_index, top_k=20)
    fused = reciprocal_rank_fusion(vector_results, bm25_results)
    return fused[:top_k]




if __name__ == "__main__":
    from rag.ingest import parse_pdf
    from rag.chunker import chunk_filing

    pages = parse_pdf("data/pdfs/AAPL_10K_2025.pdf")
    chunks = chunk_filing(pages, "AAPL", "10-K", "2025")
    bm25_index = build_bm25_index(chunks)

    results = hybrid_search("Apple revenue 2025", chunks, bm25_index, metadata_filter={"ticker": "AAPL"})
    for r in results:
        print(round(r["rrf_score"], 4), "|", r["metadata"]["section"][:30], "|", r["text"][:60])
