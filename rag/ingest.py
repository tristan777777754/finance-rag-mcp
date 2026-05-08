"""
PDF ingestion pipeline: SEC filing PDF → chunks → embeddings → Chroma.

Usage:
    python rag/ingest.py --pdf data/pdfs/AAPL_10K_2024.pdf \
                         --ticker AAPL --filing-type 10-K --fiscal-year 2024
"""

from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pdfplumber
from sentence_transformers import SentenceTransformer
from rag.chunker import chunk_filing
from rag.chroma_client import get_chroma_client
import re

def _clean_text(text: str) -> str:
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        if len(line.strip()) < 10:
            continue
        if re.search(r"\d{2}/\d{2}/\d{4},\s*\d{2}:\d{2}", line):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def parse_pdf(pdf_path: str) -> list[dict]:
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = _clean_text(page.extract_text() or "")
            tables = []
            for table in page.extract_tables():
                # Convert table (list of rows) to readable string
                rows = ["\t".join(str(cell) for cell in row if cell) for row in table if row]
                tables.append("\n".join(rows))
            pages.append({
                "page_number": i + 1,
                "text": text,
                "tables": tables,
            })
    return pages


_MODEL: SentenceTransformer | None = None


def _get_embedding_model() -> SentenceTransformer:
    """Load the embedding model only when embeddings are actually needed."""
    global _MODEL
    if _MODEL is None:
        _MODEL = SentenceTransformer("BAAI/bge-small-en-v1.5")
    return _MODEL

def embed_chunks(chunks) -> list[list[float]]:
    """
    Embed a list of Chunk objects using sentence-transformers.

    Returns:
        List of embedding vectors (one per chunk).
    """
    texts = [c.text for c in chunks]
    embeddings = _get_embedding_model().encode(texts, show_progress_bar=True)
    return embeddings.tolist()

_CHROMA_CLIENT = get_chroma_client()

def upsert_to_chroma(chunks, embeddings: list[list[float]], collection_name: str = "sec_filings") -> None:
    collection = _CHROMA_CLIENT.get_or_create_collection(collection_name)

    if chunks:
        first_metadata = chunks[0].metadata
        replace_filter = {
            "$and": [
                {"ticker": first_metadata["ticker"]},
                {"fiscal_year": first_metadata["fiscal_year"]},
                {"filing_type": first_metadata["filing_type"]},
            ]
        }
        collection.delete(where=replace_filter)
    
    ids = [
        f"{c.metadata['ticker']}_{c.metadata['filing_type']}_{c.metadata['fiscal_year']}_{i}"
        for i, c in enumerate(chunks)
    ]
    texts = [c.text for c in chunks]
    metadatas = [c.metadata for c in chunks]
    
    collection.upsert(
        ids=ids,
        documents=texts,
        embeddings=embeddings,
        metadatas=metadatas,
    )
    print(f"Upserted {len(chunks)} chunks into '{collection_name}'")

def ingest_filing(pdf_path: str, ticker: str, filing_type: str, fiscal_year: str) -> None:
    pages = parse_pdf(pdf_path)
    chunks = chunk_filing(pages, ticker, filing_type, fiscal_year)
    embeddings = embed_chunks(chunks)
    upsert_to_chroma(chunks, embeddings)



if __name__ == "__main__":
    filings = [
        ("data/pdfs/AAPL_10K_2025.pdf", "AAPL", "10-K", "2025"),
        ("data/pdfs/MSFT_10K_2025.pdf", "MSFT", "10-K", "2025"),
        ("data/pdfs/NVDA_10K_2025.pdf", "NVDA", "10-K", "2025"),
    ]
    for pdf_path, ticker, filing_type, fiscal_year in filings:
        print(f"\nIngesting {ticker}...")
        ingest_filing(pdf_path, ticker, filing_type, fiscal_year)
