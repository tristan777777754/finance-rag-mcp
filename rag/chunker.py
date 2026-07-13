"""
Structure-aware chunking for SEC 10-K / 10-Q filings.

Strategy:
- Narrative sections (Item 1, 1A, 7): sliding window, 512 tokens, 80-token overlap
- Financial tables (Item 8):          whole-table chunks, no splitting
- MD&A mixed sections:                paragraph-level split with parent context
"""

from __future__ import annotations
from dataclasses import dataclass, field
import tiktoken
import re

_ENC = tiktoken.get_encoding("cl100k_base")

@dataclass
class Chunk:
    text: str
    metadata: dict = field(default_factory=dict)
    # metadata keys: ticker, filing_type, fiscal_year, section, section_type, page_number


def chunk_filing(pages, ticker, filing_type, fiscal_year):
    base_meta = {
        "ticker": ticker.upper(),
        "filing_type": filing_type,
        "fiscal_year": fiscal_year,
    }

    chunks = []
    current_section = ""
    for page in pages:
        detected_section = _detect_section(page["text"])
        if detected_section:
            current_section = detected_section
        section = current_section
        page_tables = page.get("tables") or []
        is_table = _is_table_section(section) or _has_financial_table(page["text"], page_tables)

        extracted_tables = [table_text for table_text in page_tables if table_text.strip()]
        for table_index, table_text in enumerate(extracted_tables, start=1):
            if table_text.strip():
                chunks.append(Chunk(
                    text=_format_table_chunk(page["text"], table_text, table_index),
                    metadata={**base_meta, "page_number": page["page_number"],
                              "section": section, "section_type": "table",
                              "table_index": table_index},
                ))

        if extracted_tables:
            # A complete extracted table is authoritative for this page.
            # Do not also create narrative chunks that can repeat table rows.
            continue

        if is_table:
            # Keep the whole page only when extraction found no usable table.
            chunks.append(Chunk(
                text=_format_page_with_tables(page["text"], extracted_tables),
                metadata={**base_meta, "page_number": page["page_number"],
                          "section": section, "section_type": "table"},
            ))
        else:
            section_type = "mda" if re.search(r"item\s+7", section, re.IGNORECASE) else "narrative"
            for piece in _split_tokens(page["text"], max_tokens=512, overlap=80):
                if piece.strip():
                    chunks.append(Chunk(
                        text=piece.strip(),
                        metadata={**base_meta, "page_number": page["page_number"],
                                  "section": section, "section_type": section_type},
                    ))
    return chunks


def _detect_section(text: str) -> str:
    """Return SEC section name if heading found, else empty string."""
    match = re.search(r"(item\s+\d+[a-zA-Z]?\.?\s+\w+)", text[:200], re.IGNORECASE)
    return match.group(1).strip() if match else ""

def _is_table_section(section: str) -> bool:
    """Item 8 contains financial statements — never split."""
    return bool(re.search(r"item\s+8\b", section, re.IGNORECASE))


def _has_financial_table(text: str, tables: list[str]) -> bool:
    """Detect financial statement tables even when the Item 8 heading is on a prior page."""
    combined = "\n".join([text, *tables])
    patterns = [
        r"consolidated statements? of",
        r"total net sales",
        r"net income",
        r"gross margin",
        r"segment operating performance",
        r"products and services performance",
    ]
    return any(re.search(pattern, combined, re.IGNORECASE) for pattern in patterns)


def _format_table_chunk(page_text: str, table_text: str, table_index: int) -> str:
    """Attach nearby page heading text to a whole extracted table."""
    heading = "\n".join(page_text.splitlines()[:8]).strip()
    return f"Extracted Table {table_index}\n{heading}\n\n{table_text}".strip()


def _format_page_with_tables(page_text: str, tables: list[str]) -> str:
    """Keep financial table pages intact with extracted tables appended."""
    table_block = "\n\n".join(
        f"Extracted Table {i}\n{table}"
        for i, table in enumerate(tables, start=1)
        if table.strip()
    )
    if table_block:
        return f"{page_text.strip()}\n\n{table_block}".strip()
    return page_text.strip()

def _token_len(text: str) -> int:
    return len(_ENC.encode(text))

def _split_tokens(text: str, max_tokens: int = 512, overlap: int = 80) -> list[str]:
    tokens = _ENC.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunks.append(_ENC.decode(tokens[start:end]))
        if end == len(tokens):
            break
        start += max_tokens - overlap
    return chunks


if __name__ == "__main__":
    fake_pages = [
        {"page_number": 7, "text": "Item 7. Management Discussion\n" + "Revenue grew significantly. " * 50, "tables": []},
        {"page_number": 40, "text": "Item 8. Financial Statements\n" + "Revenue: $391B  Net Income: $94B " * 50, "tables": []},
    ]

    chunks = chunk_filing(fake_pages, "AAPL", "10-K", "2024")
    for c in chunks:
        print(c.metadata["section_type"], "|", c.metadata["section"][:40])
