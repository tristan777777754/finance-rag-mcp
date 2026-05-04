"""
Orchestrator: router → parallel retrieval (RAG + MCP) → Claude synthesis.

Flow:
    1. classify_query()  → query_type
    2a. RAG_ONLY  → hybrid_search()
    2b. MCP_ONLY  → MCP tool calls
    2c. HYBRID    → both in parallel
    3. Claude Sonnet synthesises answer with inline citations
"""

from __future__ import annotations
from openai import OpenAI
from dotenv import load_dotenv
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from agent.router import classify_query
from rag.chroma_client import get_chroma_client
from rag.retriever import build_bm25_index, hybrid_search
from tools.stock_server import get_stock_price, get_fundamentals, get_financials

load_dotenv()
_CLIENT = OpenAI()

def _run_rag(query: str, ticker: str, fiscal_year: str) -> list[dict]:
    # Get chunks from Chroma for this ticker+year (for BM25)
    client = get_chroma_client()
    col = client.get_collection("sec_filings")
    res = col.get(where={"$and": [{"ticker": ticker}, {"fiscal_year": fiscal_year}]})

    from rag.chunker import Chunk
    chunks = [Chunk(text=t, metadata=m) for t, m in zip(res["documents"], res["metadatas"])]

    if not chunks:
        raise ValueError(f"No chunks found in ChromaDB for ticker={ticker}, fiscal_year={fiscal_year}")

    bm25_index = build_bm25_index(chunks)

    return hybrid_search(
        query, chunks, bm25_index,
        metadata_filter={"$and": [{"ticker": ticker}, {"fiscal_year": fiscal_year}]}
    )
def _run_mcp(ticker: str) -> list[dict]:
    return [
        get_stock_price(ticker),
        get_fundamentals(ticker),
    ]

def run(
    query: str,
    ticker: str = "AAPL",
    fiscal_year: str = "2025",
    query_type_override: str | None = None,
) -> dict:
    classification = (
        {"query_type": query_type_override, "reasoning": "Query type provided by evaluation label."}
        if query_type_override
        else classify_query(query)
    )
    query_type = classification["query_type"]

    rag_results, mcp_results = [], []

    if query_type in ("RAG_ONLY", "HYBRID"):
        rag_results = _run_rag(query, ticker, fiscal_year)   # fiscal_year

    if query_type in ("MCP_ONLY", "HYBRID"):
        mcp_results = _run_mcp(ticker)

 

    # Build context
    context_parts = []
    for i, r in enumerate(rag_results):
        context_parts.append(f"[Doc {i+1} | {r['metadata'].get('section','?')} | p.{r['metadata'].get('page_number','?')}]\n{r['text']}")
    for m in mcp_results:
        context_parts.append(f"[Live Data]\n{m}")

    context = "\n\n".join(context_parts)

    response = _CLIENT.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a financial analyst. Answer using only the provided context. Cite sources with [Doc X] or [Live Data]."},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"},
        ],
    )

    return {
        "query_type": query_type,
        "answer": response.choices[0].message.content,
        "sources": rag_results,
        "mcp_data": mcp_results,
    }

if __name__ == "__main__":
    result = run("What was Apple's revenue in 2025?", ticker="AAPL")
    print(f"[{result['query_type']}]", result["answer"])

    result = run("What is Apple's current stock price?", ticker="AAPL")
    print(f"[{result['query_type']}]", result["answer"])
