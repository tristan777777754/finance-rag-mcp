from __future__ import annotations

import socket

import pytest
import requests

from rag.chunker import Chunk


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    """Fail tests that accidentally access an external network service."""
    def _blocked(*_args, **_kwargs):
        raise AssertionError("External network access is forbidden in contract tests.")

    monkeypatch.setattr(requests.sessions.Session, "request", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket.socket, "connect", _blocked)


@pytest.fixture
def make_chunk():
    """Build a chunk with the citation metadata required by retrieval."""

    def _make_chunk(
        text: str,
        *,
        ticker: str = "AAPL",
        fiscal_year: str = "2024",
        section: str = "Item 8. Financial Statements",
        page_number: int = 42,
        section_type: str = "table",
    ) -> Chunk:
        return Chunk(
            text=text,
            metadata={
                "ticker": ticker,
                "filing_type": "10-K",
                "fiscal_year": fiscal_year,
                "section": section,
                "page_number": page_number,
                "section_type": section_type,
            },
        )

    return _make_chunk
