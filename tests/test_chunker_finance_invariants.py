from __future__ import annotations

from rag.chunker import chunk_filing


def test_financial_table_is_stored_once_as_a_complete_chunk():
    table_rows = "\n".join(
        f"Revenue line {index} | {index * 100} | {index * 90}" for index in range(1, 180)
    )
    pages = [
        {
            "page_number": 42,
            "text": "Item 8. Financial Statements\nConsolidated Statements of Operations\n" + table_rows,
            "tables": [table_rows],
        }
    ]

    chunks = chunk_filing(pages, "AAPL", "10-K", "2024")
    table_chunks = [chunk for chunk in chunks if chunk.metadata.get("table_index") == 1]

    assert len(chunks) == 1
    assert len(table_chunks) == 1
    table_chunk = table_chunks[0]
    assert "Revenue line 1 | 100 | 90" in table_chunk.text
    assert "Revenue line 179 | 17900 | 16110" in table_chunk.text
    assert table_chunk.metadata == {
        "ticker": "AAPL",
        "filing_type": "10-K",
        "fiscal_year": "2024",
        "page_number": 42,
        "section": "Item 8. Financial",
        "section_type": "table",
        "table_index": 1,
    }
