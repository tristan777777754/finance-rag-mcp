from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest


def _router_module(monkeypatch):
    """Import the router with a harmless local API key for client construction."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    module = importlib.import_module("agent.router")
    return importlib.reload(module)


def _mock_router_response(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


@pytest.mark.parametrize("query_type", ["RAG_ONLY", "MCP_ONLY", "HYBRID"])
def test_router_returns_only_valid_contract_values(monkeypatch, query_type):
    router = _router_module(monkeypatch)
    response = _mock_router_response(
        f'{{"query_type": "{query_type}", "reasoning": "Test routing reason"}}'
    )
    monkeypatch.setattr(router._CLIENT.chat.completions, "create", lambda **_: response)

    result = router.classify_query("Test query")

    assert result == {"query_type": query_type, "reasoning": "Test routing reason"}


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '{"query_type": "UNKNOWN", "reasoning": "invalid type"}',
        '{"query_type": "RAG_ONLY", "reasoning": ""}',
        '{"query_type": "MCP_ONLY"}',
    ],
)
def test_router_rejects_invalid_contract_values(monkeypatch, content):
    router = _router_module(monkeypatch)
    response = _mock_router_response(content)
    monkeypatch.setattr(router._CLIENT.chat.completions, "create", lambda **_: response)

    with pytest.raises(ValueError):
        router.classify_query("Test query")
