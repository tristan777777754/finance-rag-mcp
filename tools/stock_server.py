"""
MCP Server with finance tools (Sprint 2).

Tools (default fallback chain: Polygon.io → Alpha Vantage → unavailable):
- get_stock_price      : current price, 52-week range
- get_fundamentals     : P/E, EPS, market cap, revenue
- get_peers            : comparable company tickers
- get_earnings_calendar: upcoming earnings dates
- get_sec_filings_list : recent 10-K / 10-Q filings from SEC EDGAR
- get_financials       : income statement / balance sheet snapshots
"""

from fastmcp import FastMCP
import os
import requests
from dotenv import load_dotenv

load_dotenv()
app = FastMCP("stock-research")

POLYGON_KEY = os.getenv("POLYGON_API_KEY")
AV_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
ENABLE_YFINANCE_FALLBACK = os.getenv("ENABLE_YFINANCE_FALLBACK", "false").lower() == "true"


def _unavailable(ticker: str, tool_name: str, reason: str) -> dict:
    """
    Return a structured unavailable response instead of calling unstable sources.

    Args:
        ticker: Stock ticker symbol.
        tool_name: MCP tool name.
        reason: Human-readable reason for unavailable data.
    """
    return {
        "ticker": ticker.upper(),
        "tool": tool_name,
        "data_source": "unavailable",
        "error": reason,
    }


def _request_json(url: str, params: dict | None = None) -> dict | None:
    """Fetch JSON with a short timeout and return None on API/network failure."""
    try:
        response = requests.get(url, params=params, timeout=5)
        if response.status_code != 200:
            return None
        return response.json()
    except Exception:
        return None


def _request_text(url: str, params: dict | None = None) -> str | None:
    """Fetch text with a short timeout and return None on API/network failure."""
    try:
        response = requests.get(url, params=params, timeout=5)
        if response.status_code != 200:
            return None
        return response.text
    except Exception:
        return None


def _to_float(value: object) -> float | None:
    """Convert API string values to float, preserving missing values as None."""
    if value in (None, "", "None", "N/A", "-"):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _to_int(value: object) -> int | None:
    """Convert API string values to int, preserving missing values as None."""
    number = _to_float(value)
    return int(number) if number is not None else None


def _get_stock_price_from_yfinance(ticker: str) -> dict | None:
    """Optional local fallback only; disabled by default because Yahoo rate-limits batch evals."""
    if not ENABLE_YFINANCE_FALLBACK:
        return None

    try:
        import yfinance as yf

        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d")
        info = stock.info
        return {
            "ticker": ticker.upper(),
            "price": hist["Close"].iloc[-1] if not hist.empty else None,
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
            "data_source": "yfinance",
        }
    except Exception as exc:
        return {
            "ticker": ticker.upper(),
            "data_source": "yfinance",
            "error": str(exc),
        }


def _get_fundamentals_from_yfinance(ticker: str) -> dict | None:
    """Optional local fallback only; disabled by default because Yahoo rate-limits batch evals."""
    if not ENABLE_YFINANCE_FALLBACK:
        return None

    try:
        import yfinance as yf

        info = yf.Ticker(ticker).info
        return {
            "ticker": ticker.upper(),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "eps": info.get("trailingEps"),
            "revenue": info.get("totalRevenue"),
            "data_source": "yfinance",
        }
    except Exception as exc:
        return {
            "ticker": ticker.upper(),
            "data_source": "yfinance",
            "error": str(exc),
        }


@app.tool()
def get_stock_price(ticker: str) -> dict:
    ticker = ticker.upper()

    # Try Polygon.io first.
    if POLYGON_KEY:
        url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev"
        data = _request_json(url, params={"apiKey": POLYGON_KEY})
        results = data.get("results", []) if data else []
        if results:
            result = results[0]
            return {
                "ticker": ticker,
                "price": result.get("c"),
                "open": result.get("o"),
                "high": result.get("h"),
                "low": result.get("l"),
                "volume": result.get("v"),
                "data_source": "polygon",
            }

    # Fall back to Alpha Vantage official API.
    if AV_KEY:
        data = _request_json(
            "https://www.alphavantage.co/query",
            params={"function": "GLOBAL_QUOTE", "symbol": ticker, "apikey": AV_KEY},
        )
        quote = data.get("Global Quote", {}) if data else {}
        price = quote.get("05. price")
        if price:
            return {
                "ticker": ticker,
                "price": float(price),
                "open": float(quote["02. open"]) if quote.get("02. open") else None,
                "high": float(quote["03. high"]) if quote.get("03. high") else None,
                "low": float(quote["04. low"]) if quote.get("04. low") else None,
                "volume": int(quote["06. volume"]) if quote.get("06. volume") else None,
                "data_source": "alpha_vantage",
            }

    yfinance_result = _get_stock_price_from_yfinance(ticker)
    if yfinance_result:
        return yfinance_result

    return _unavailable(ticker, "get_stock_price", "Polygon and Alpha Vantage did not return price data.")

def _get_eps_from_polygon(ticker: str) -> float | None:
    """Fetch trailing EPS from Polygon financials endpoint (most recent annual filing)."""
    if not POLYGON_KEY:
        return None

    data = _request_json(
        "https://api.polygon.io/vX/reference/financials",
        params={"ticker": ticker, "timeframe": "annual", "limit": 1, "apiKey": POLYGON_KEY},
    )
    results = data.get("results", []) if data else []
    if results:
        income = results[0].get("financials", {}).get("income_statement", {})
        # Prefer diluted EPS, fall back to basic EPS.
        eps_data = income.get("diluted_earnings_per_share") or income.get("basic_earnings_per_share")
        if eps_data:
            return eps_data.get("value")
    return None


@app.tool()
def get_fundamentals(ticker: str) -> dict:
    ticker = ticker.upper()

    # Try Polygon first.
    if POLYGON_KEY:
        data = _request_json(
            f"https://api.polygon.io/v3/reference/tickers/{ticker}",
            params={"apiKey": POLYGON_KEY},
        )
        polygon_result = data.get("results") if data else None
        if polygon_result:
            price_data = get_stock_price(ticker)
            price = price_data.get("price")
            eps = _get_eps_from_polygon(ticker)
            pe_ratio = round(price / eps, 2) if price and eps and eps > 0 else None
            return {
                "ticker": ticker,
                "market_cap": polygon_result.get("market_cap"),
                "name": polygon_result.get("name"),
                "eps": eps,
                "pe_ratio": pe_ratio,
                "pb_ratio": None,
                "ev_to_ebitda": None,
                "roe": None,
                "dividend_yield": None,
                "52w_high": None,
                "52w_low": None,
                "data_source": "polygon",
            }

    # Fall back to Alpha Vantage official API.
    if AV_KEY:
        data = _request_json(
            "https://www.alphavantage.co/query",
            params={"function": "OVERVIEW", "symbol": ticker, "apikey": AV_KEY},
        )
        if data and data.get("Symbol"):
            return {
                "ticker": ticker,
                "market_cap": _to_int(data.get("MarketCapitalization")),
                "name": data.get("Name"),
                "pe_ratio": _to_float(data.get("PERatio")),
                "pb_ratio": _to_float(data.get("PriceToBookRatio")),
                "ev_to_ebitda": _to_float(data.get("EVToEBITDA")),
                "eps": _to_float(data.get("EPS")),
                "revenue": _to_int(data.get("RevenueTTM")),
                "roe": _to_float(data.get("ReturnOnEquityTTM")),
                "dividend_yield": _to_float(data.get("DividendYield")),
                "dividend_per_share": _to_float(data.get("DividendPerShare")),
                "52w_high": _to_float(data.get("52WeekHigh")),
                "52w_low": _to_float(data.get("52WeekLow")),
                "data_source": "alpha_vantage",
            }

    yfinance_result = _get_fundamentals_from_yfinance(ticker)
    if yfinance_result:
        return yfinance_result

    return _unavailable(ticker, "get_fundamentals", "Polygon and Alpha Vantage did not return fundamentals.")


@app.tool()
def get_peers(ticker: str) -> dict:
    ticker = ticker.upper()
    if not POLYGON_KEY:
        return _unavailable(ticker, "get_peers", "Polygon API key is not configured.")

    try:
        url = f"https://api.polygon.io/v1/meta/symbols/{ticker}/company?apiKey={POLYGON_KEY}"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            d = r.json()
            return {
                "ticker": ticker,
                "sector": d.get("sector"),
                "industry": d.get("industry"),
                "similar": d.get("similar", []),
                "data_source": "polygon",
            }
    except Exception:
        return _unavailable(ticker, "get_peers", "Polygon peer lookup failed.")

    return _unavailable(ticker, "get_peers", "Polygon did not return peer data.")


@app.tool()
def get_earnings_calendar(ticker: str) -> dict:
    ticker = ticker.upper()

    if AV_KEY:
        text = _request_text(
            "https://www.alphavantage.co/query",
            params={"function": "EARNINGS_CALENDAR", "symbol": ticker, "horizon": "3month", "apikey": AV_KEY},
        )
        if text and "reportDate" in text:
            import csv
            from io import StringIO

            rows = list(csv.DictReader(StringIO(text)))
            if rows:
                first = rows[0]
                return {
                    "ticker": ticker,
                    "next_earnings_date": first.get("reportDate"),
                    "eps_estimate": _to_float(first.get("estimate")),
                    "fiscal_date_ending": first.get("fiscalDateEnding"),
                    "currency": first.get("currency"),
                    "data_source": "alpha_vantage",
                }

    if POLYGON_KEY:
        try:
            url = f"https://api.polygon.io/vX/reference/financials?ticker={ticker}&limit=1&apiKey={POLYGON_KEY}"
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                results = r.json().get("results", [])
                if results:
                    return {
                        "ticker": ticker,
                        "fiscal_period": results[0].get("fiscal_period"),
                        "fiscal_year": results[0].get("fiscal_year"),
                        "filing_date": results[0].get("filing_date"),
                        "data_source": "polygon",
                    }
        except Exception:
            return _unavailable(ticker, "get_earnings_calendar", "Polygon earnings lookup failed.")

    return _unavailable(ticker, "get_earnings_calendar", "No earnings calendar data returned by configured APIs.")


@app.tool()
def get_sec_filings_list(ticker: str, form_types: list[str] | None = None, limit: int = 10) -> dict:
    """
    Return recent SEC 10-K / 10-Q filing metadata from EDGAR.

    Args:
        ticker: Stock ticker symbol.
        form_types: SEC form types to include.
        limit: Maximum number of filings to return.
    """
    ticker = ticker.upper()
    form_types = form_types or ["10-K", "10-Q"]

    try:
        from edgar import get_filings

        filings: list[dict] = []
        for form_type in form_types:
            for filing in get_filings(ticker, form_type=form_type):
                filings.append({**filing, "form_type": form_type})

        filings = sorted(filings, key=lambda item: item["date"], reverse=True)[:limit]
        return {
            "ticker": ticker,
            "filings": filings,
            "data_source": "sec_edgar",
        }
    except Exception as exc:
        return {
            "ticker": ticker,
            "tool": "get_sec_filings_list",
            "data_source": "sec_edgar",
            "error": str(exc),
        }


@app.tool()
def get_financials(ticker: str, statement: str = "income") -> dict:
    ticker = ticker.upper()
    if not POLYGON_KEY:
        return _unavailable(ticker, "get_financials", "Polygon API key is not configured.")

    try:
        url = f"https://api.polygon.io/vX/reference/financials?ticker={ticker}&limit=1&apiKey={POLYGON_KEY}"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            results = r.json().get("results", [])
            if results:
                financials = results[0].get("financials", {})
                if statement == "income":
                    data = financials.get("income_statement", {})
                elif statement == "balance":
                    data = financials.get("balance_sheet", {})
                else:
                    data = financials.get("cash_flow_statement", {})
                clean = {k: v.get("value") for k, v in data.items()}
                return {"ticker": ticker, "statement": statement, "data": clean, "data_source": "polygon"}
    except Exception:
        return _unavailable(ticker, "get_financials", "Polygon financial statement lookup failed.")

    return _unavailable(ticker, "get_financials", "Polygon did not return financial statement data.")


# if __name__ == "__main__":
#     app.run()

if __name__ == "__main__":
    print(get_peers("AAPL"))
    print(get_earnings_calendar("AAPL"))
    print(get_financials("AAPL", "income"))
