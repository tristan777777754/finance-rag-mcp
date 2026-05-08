"""
SEC EDGAR auto-download pipeline.

Usage:
    from edgar import ingest_from_edgar
    ingest_from_edgar("AAPL", "2025")
"""

from __future__ import annotations
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

import requests
from bs4 import BeautifulSoup

from rag.chunker import chunk_filing
from rag.ingest import embed_chunks, upsert_to_chroma

# ---------------------------------------------------------------------------
# CIK lookup table (add more as needed)
# ---------------------------------------------------------------------------

CIK_MAP: dict[str, str] = {
    "AAPL": "320193",
    "MSFT": "789019",
    "NVDA": "1045810",
}

HEADERS = {"User-Agent": "tristan890620@gmail.com"}


def _extract_html_tables(soup: BeautifulSoup) -> list[str]:
    """
    Extract SEC HTML tables as tab-separated text.

    Financial tables must stay intact because line items, fiscal years, and
    values lose meaning when generic HTML text extraction flattens them.
    """
    financial_terms = (
        "total net sales",
        "net sales",
        "net income",
        "gross margin",
        "consolidated statements",
        "products and services performance",
        "segment operating performance",
    )
    extracted: list[str] = []

    for table in soup.find_all("table"):
        rows = []
        for row in table.find_all("tr"):
            cells = [
                cell.get_text(" ", strip=True)
                for cell in row.find_all(["th", "td"])
            ]
            cells = [cell for cell in cells if cell]
            if cells:
                rows.append("\t".join(cells))

        table_text = "\n".join(rows).strip()
        if not table_text:
            continue

        table_lower = table_text.lower()
        if any(term in table_lower for term in financial_terms):
            extracted.append(table_text)

    return extracted


def _table_pages(tables: list[str], start_page: int) -> list[dict]:
    """Represent extracted HTML tables as pseudo-pages for the chunker."""
    pages = []
    for i, table in enumerate(tables, start=start_page):
        first_line = table.splitlines()[0] if table.splitlines() else "Extracted financial table"
        pages.append({
            "page_number": i,
            "text": f"Item 8. Financial Statements and Supplementary Data\nExtracted financial table\n{first_line}",
            "tables": [table],
        })
    return pages


# ---------------------------------------------------------------------------
# Step 1: Get filing list from SEC EDGAR
# ---------------------------------------------------------------------------

def get_filings(ticker: str, form_type: str = "10-K") -> list[dict]:
    """
    Return list of filings for a ticker, sorted newest first.

    Each item: {"date": str, "year": str, "accession": str, "primary_doc": str}
    """
    cik = CIK_MAP.get(ticker.upper())
    if not cik:
        raise ValueError(f"CIK not found for ticker '{ticker}'. Add it to CIK_MAP.")

    url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
    r = requests.get(url, headers=HEADERS, timeout=10)
    r.raise_for_status()
    data = r.json()

    filings = data["filings"]["recent"]
    results = []
    for i, form in enumerate(filings["form"]):
        if form == form_type:
            date = filings["filingDate"][i]
            results.append({
                "date": date,
                "year": date[:4],
                "accession": filings["accessionNumber"][i],
                "primary_doc": filings["primaryDocument"][i],
            })
    return results


# ---------------------------------------------------------------------------
# Step 2: Download + parse HTML filing into pages
# ---------------------------------------------------------------------------

def download_and_parse(ticker: str, accession: str, primary_doc: str) -> list[dict]:
    """
    Download a SEC HTML filing and parse it into page dicts.

    Returns:
        [{"page_number": int, "text": str, "tables": []}]
    """
    cik = CIK_MAP[ticker.upper()]
    accession_clean = accession.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_clean}/{primary_doc}"

    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.content, "html.parser")
    for tag in soup(["script", "style", "ix:header", "ix:hidden"]):
        tag.decompose()

    extracted_tables = _extract_html_tables(soup)
    raw_text = soup.get_text(separator="\n")

    lines = []
    for line in raw_text.split("\n"):
        line = line.strip()
        if len(line) < 15:
            continue
        if "http" in line or "fasb.org" in line:
            continue
        if line.startswith(("false", "true")):
            continue
        lines.append(line)

    clean_text = "\n".join(lines)

    # Split into fake pages of ~3000 chars to match pdfplumber output format
    pages = []
    chunk_size = 3000
    for i, start in enumerate(range(0, len(clean_text), chunk_size)):
        pages.append({
            "page_number": i + 1,
            "text": clean_text[start:start + chunk_size],
            "tables": [],
        })
    pages.extend(_table_pages(extracted_tables, len(pages) + 1))
    return pages


# ---------------------------------------------------------------------------
# Step 3: Full pipeline — find filing → download → chunk → embed → Chroma
# ---------------------------------------------------------------------------

def ingest_from_edgar(ticker: str, year: str, form_type: str = "10-K") -> str:
    """
    Auto-download and ingest a SEC filing into ChromaDB.

    Args:
        ticker:    e.g. "AAPL"
        year:      e.g. "2025"
        form_type: "10-K" or "10-Q"

    Returns:
        Status message string.
    """
    ticker = ticker.upper()
    filings = get_filings(ticker, form_type)

    # Find the filing that matches the requested year
    match = next((f for f in filings if f["year"] == year), None)
    if not match:
        available = [f["year"] for f in filings]
        raise ValueError(f"No {form_type} found for {ticker} in {year}. Available: {available}")

    print(f"Found {ticker} {form_type} filed on {match['date']}, downloading...")
    pages = download_and_parse(ticker, match["accession"], match["primary_doc"])
    print(f"Parsed {len(pages)} pages.")

    chunks = chunk_filing(pages, ticker=ticker, filing_type=form_type, fiscal_year=year)
    print(f"Created {len(chunks)} chunks.")

    embeddings = embed_chunks(chunks)
    upsert_to_chroma(chunks, embeddings)

    return f"✅ Ingested {ticker} {form_type} {year} — {len(chunks)} chunks added to ChromaDB."


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    msg = ingest_from_edgar("AAPL", "2025")
    print(msg)
