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
    for page in pages:
        section = _detect_section(page["text"])
        is_table = _is_table_section(section)

        if is_table:
            # Whole page as one chunk — never split financial tables
            chunks.append(Chunk(
                text=page["text"].strip(),
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
