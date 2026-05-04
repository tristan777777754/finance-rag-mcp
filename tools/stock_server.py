"""
MCP Server with finance tools (Sprint 2).

Tools (default fallback chain: Polygon.io → Alpha Vantage → unavailable):
- get_stock_price      : current price, 52-week range
- get_fundamentals     : P/E, EPS, market cap, revenue
- get_peers            : comparable company tickers
- get_earnings_calendar: upcoming earnings dates
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
                "market_cap": int(data["MarketCapitalization"]) if data.get("MarketCapitalization", "").isdigit() else None,
                "name": data.get("Name"),
                "pe_ratio": float(data["PERatio"]) if data.get("PERatio") not in (None, "", "None") else None,
                "pb_ratio": float(data["PriceToBookRatio"]) if data.get("PriceToBookRatio") not in (None, "", "None") else None,
                "eps": float(data["EPS"]) if data.get("EPS") not in (None, "", "None") else None,
                "revenue": int(data["RevenueTTM"]) if data.get("RevenueTTM", "").isdigit() else None,
                "roe": float(data["ReturnOnEquityTTM"]) if data.get("ReturnOnEquityTTM") not in (None, "", "None") else None,
                "data_source": "alpha_vantage",
            }

    yfinance_result = _get_fundamentals_from_yfinance(ticker)
    if yfinance_result:
        return yfinance_result

    return _unavailable(ticker, "get_fundamentals", "Polygon and Alpha Vantage did not return fundamentals.")


@app.tool()
def get_peers(ticker: str) -> dict:
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
    except Exception as e:
        return {"error": str(e), "data_source": "none"}


@app.tool()
def get_earnings_calendar(ticker: str) -> dict:
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
    except Exception as e:
        return {"error": str(e), "data_source": "none"}


@app.tool()
def get_financials(ticker: str, statement: str = "income") -> dict:
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
    except Exception as e:
        return {"error": str(e), "data_source": "none"}


# if __name__ == "__main__":
#     app.run()

if __name__ == "__main__":
    print(get_peers("AAPL"))
    print(get_earnings_calendar("AAPL"))
    print(get_financials("AAPL", "income"))
