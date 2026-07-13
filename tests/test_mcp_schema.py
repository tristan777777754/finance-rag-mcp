from __future__ import annotations

import sys
from types import SimpleNamespace

import tools.stock_server as server


def _assert_source(response: dict, source: str) -> None:
    assert response["ticker"] == "AAPL"
    assert response["data_source"] == source


def test_stock_price_uses_polygon_success(monkeypatch):
    monkeypatch.setattr(server, "POLYGON_KEY", "polygon-key")
    monkeypatch.setattr(server, "AV_KEY", None)
    monkeypatch.setattr(
        server,
        "_request_json",
        lambda *_args, **_kwargs: {"results": [{"c": 210.5, "o": 209.0, "h": 212.0, "l": 208.0, "v": 10}]},
    )

    response = server.get_stock_price("aapl")

    _assert_source(response, "polygon")
    assert response["price"] == 210.5


def test_stock_price_falls_back_to_alpha_vantage(monkeypatch):
    monkeypatch.setattr(server, "POLYGON_KEY", "polygon-key")
    monkeypatch.setattr(server, "AV_KEY", "alpha-key")
    monkeypatch.setattr(server, "ENABLE_YFINANCE_FALLBACK", False)
    responses = iter([
        {"results": []},
        {"Global Quote": {"05. price": "210.50", "02. open": "209.00", "03. high": "212.00", "04. low": "208.00", "06. volume": "10"}},
    ])
    monkeypatch.setattr(server, "_request_json", lambda *_args, **_kwargs: next(responses))

    response = server.get_stock_price("aapl")

    _assert_source(response, "alpha_vantage")


def test_stock_price_returns_unavailable_without_provider_data(monkeypatch):
    monkeypatch.setattr(server, "POLYGON_KEY", None)
    monkeypatch.setattr(server, "AV_KEY", None)
    monkeypatch.setattr(server, "ENABLE_YFINANCE_FALLBACK", False)

    response = server.get_stock_price("aapl")

    _assert_source(response, "unavailable")


def test_stock_price_uses_yfinance_as_optional_last_fallback(monkeypatch):
    monkeypatch.setattr(server, "POLYGON_KEY", None)
    monkeypatch.setattr(server, "AV_KEY", None)
    monkeypatch.setattr(server, "ENABLE_YFINANCE_FALLBACK", True)
    monkeypatch.setattr(
        server,
        "_get_stock_price_from_yfinance",
        lambda _ticker: {"ticker": "AAPL", "price": 210.5, "data_source": "yfinance"},
    )

    _assert_source(server.get_stock_price("aapl"), "yfinance")


def test_fundamentals_uses_polygon_success(monkeypatch):
    monkeypatch.setattr(server, "POLYGON_KEY", "polygon-key")
    monkeypatch.setattr(server, "AV_KEY", None)
    monkeypatch.setattr(server, "get_stock_price", lambda _ticker: {"price": 200.0})
    monkeypatch.setattr(server, "_get_eps_from_polygon", lambda _ticker: 10.0)
    monkeypatch.setattr(
        server,
        "_request_json",
        lambda *_args, **_kwargs: {"results": {"market_cap": 3_000_000_000_000, "name": "Apple Inc."}},
    )

    response = server.get_fundamentals("aapl")

    _assert_source(response, "polygon")
    assert response["pe_ratio"] == 20.0


def test_fundamentals_falls_back_to_alpha_vantage(monkeypatch):
    monkeypatch.setattr(server, "POLYGON_KEY", "polygon-key")
    monkeypatch.setattr(server, "AV_KEY", "alpha-key")
    monkeypatch.setattr(server, "ENABLE_YFINANCE_FALLBACK", False)
    responses = iter([
        {"results": None},
        {"Symbol": "AAPL", "MarketCapitalization": "3000000000000", "PERatio": "30.0", "EPS": "7.0"},
    ])
    monkeypatch.setattr(server, "_request_json", lambda *_args, **_kwargs: next(responses))

    response = server.get_fundamentals("aapl")

    _assert_source(response, "alpha_vantage")
    assert response["pe_ratio"] == 30.0


def test_fundamentals_returns_unavailable_without_provider_data(monkeypatch):
    monkeypatch.setattr(server, "POLYGON_KEY", None)
    monkeypatch.setattr(server, "AV_KEY", None)
    monkeypatch.setattr(server, "ENABLE_YFINANCE_FALLBACK", False)

    response = server.get_fundamentals("aapl")

    _assert_source(response, "unavailable")


def test_fundamentals_uses_yfinance_as_optional_last_fallback(monkeypatch):
    monkeypatch.setattr(server, "POLYGON_KEY", None)
    monkeypatch.setattr(server, "AV_KEY", None)
    monkeypatch.setattr(server, "ENABLE_YFINANCE_FALLBACK", True)
    monkeypatch.setattr(
        server,
        "_get_fundamentals_from_yfinance",
        lambda _ticker: {"ticker": "AAPL", "market_cap": 3_000_000_000_000, "data_source": "yfinance"},
    )

    _assert_source(server.get_fundamentals("aapl"), "yfinance")


def test_peers_success_and_unavailable_responses_include_data_source(monkeypatch):
    monkeypatch.setattr(server, "POLYGON_KEY", "polygon-key")
    fake_response = SimpleNamespace(status_code=200, json=lambda: {"sector": "Technology", "industry": "Hardware", "similar": ["MSFT"]})
    monkeypatch.setattr(server.requests, "get", lambda *_args, **_kwargs: fake_response)

    _assert_source(server.get_peers("aapl"), "polygon")

    monkeypatch.setattr(server, "POLYGON_KEY", None)
    _assert_source(server.get_peers("aapl"), "unavailable")


def test_peers_exception_response_includes_data_source(monkeypatch):
    monkeypatch.setattr(server, "POLYGON_KEY", "polygon-key")

    def raise_error(*_args, **_kwargs):
        raise RuntimeError("Polygon unavailable")

    monkeypatch.setattr(server.requests, "get", raise_error)
    _assert_source(server.get_peers("aapl"), "unavailable")


def test_earnings_calendar_success_and_unavailable_responses_include_data_source(monkeypatch):
    monkeypatch.setattr(server, "AV_KEY", "alpha-key")
    monkeypatch.setattr(server, "POLYGON_KEY", None)
    monkeypatch.setattr(
        server,
        "_request_text",
        lambda *_args, **_kwargs: "symbol,name,reportDate,fiscalDateEnding,estimate,currency\nAAPL,Apple,2026-08-01,2026-06-30,1.5,USD\n",
    )
    _assert_source(server.get_earnings_calendar("aapl"), "alpha_vantage")

    monkeypatch.setattr(server, "AV_KEY", None)
    _assert_source(server.get_earnings_calendar("aapl"), "unavailable")


def test_earnings_calendar_falls_back_to_polygon(monkeypatch):
    monkeypatch.setattr(server, "AV_KEY", None)
    monkeypatch.setattr(server, "POLYGON_KEY", "polygon-key")
    fake_response = SimpleNamespace(
        status_code=200,
        json=lambda: {"results": [{"fiscal_period": "FY", "fiscal_year": "2025", "filing_date": "2026-02-01"}]},
    )
    monkeypatch.setattr(server.requests, "get", lambda *_args, **_kwargs: fake_response)

    _assert_source(server.get_earnings_calendar("aapl"), "polygon")


def test_earnings_calendar_polygon_exception_includes_data_source(monkeypatch):
    monkeypatch.setattr(server, "AV_KEY", None)
    monkeypatch.setattr(server, "POLYGON_KEY", "polygon-key")

    def raise_error(*_args, **_kwargs):
        raise RuntimeError("Polygon unavailable")

    monkeypatch.setattr(server.requests, "get", raise_error)
    _assert_source(server.get_earnings_calendar("aapl"), "unavailable")


def test_sec_filings_success_and_error_responses_include_data_source(monkeypatch):
    fake_edgar = SimpleNamespace(get_filings=lambda _ticker, form_type: [{"date": "2026-01-01", "accession": form_type}])
    monkeypatch.setitem(sys.modules, "edgar", fake_edgar)
    _assert_source(server.get_sec_filings_list("aapl"), "sec_edgar")

    def raise_error(*_args, **_kwargs):
        raise RuntimeError("SEC unavailable")

    monkeypatch.setitem(sys.modules, "edgar", SimpleNamespace(get_filings=raise_error))
    response = server.get_sec_filings_list("aapl")
    _assert_source(response, "sec_edgar")
    assert "error" in response


def test_financials_success_and_unavailable_responses_include_data_source(monkeypatch):
    monkeypatch.setattr(server, "POLYGON_KEY", "polygon-key")
    fake_response = SimpleNamespace(
        status_code=200,
        json=lambda: {"results": [{"financials": {"income_statement": {"revenues": {"value": 391_000_000_000}}}}]},
    )
    monkeypatch.setattr(server.requests, "get", lambda *_args, **_kwargs: fake_response)
    _assert_source(server.get_financials("aapl"), "polygon")

    monkeypatch.setattr(server, "POLYGON_KEY", None)
    _assert_source(server.get_financials("aapl"), "unavailable")


def test_financials_exception_response_includes_data_source(monkeypatch):
    monkeypatch.setattr(server, "POLYGON_KEY", "polygon-key")

    def raise_error(*_args, **_kwargs):
        raise RuntimeError("Polygon unavailable")

    monkeypatch.setattr(server.requests, "get", raise_error)
    _assert_source(server.get_financials("aapl"), "unavailable")
