import streamlit as st
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from edgar import get_filings, ingest_from_edgar, CIK_MAP
from agent.analyst import run

st.set_page_config(page_title="Stock Research AI", layout="wide")
st.markdown(
    """
    <style>
    html, body, [class*="st-"], .stMarkdown, .stChatMessage {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        font-style: normal;
    }

    .stMarkdown em,
    .stMarkdown i {
        font-style: normal;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("Stock Research AI Assistant")
st.caption("RAG + MCP | SEC 10-K Analysis")

# ---------------------------------------------------------------------------
# Sidebar - filing selector
# ---------------------------------------------------------------------------
st.sidebar.header("Load a Filing")

ticker = st.sidebar.selectbox("Company", list(CIK_MAP.keys()))

# Dynamically fetch available years for selected ticker
@st.cache_data(show_spinner=False)
def fetch_years(ticker: str) -> list[str]:
    filings = get_filings(ticker, "10-K")
    return [f["year"] for f in filings]

years = fetch_years(ticker)
year = st.sidebar.selectbox("Fiscal Year", years)

if st.sidebar.button("Download & Ingest", type="primary"):
    with st.sidebar:
        with st.spinner(f"Downloading {ticker} 10-K {year}..."):
            try:
                msg = ingest_from_edgar(ticker, year)
                st.success(msg)
                st.session_state["active_ticker"] = ticker
                st.session_state["active_year"] = year
            except Exception as e:
                st.error(str(e))

# Show currently loaded filing
if "active_ticker" in st.session_state:
    st.sidebar.markdown(
        f"**Loaded:** {st.session_state['active_ticker']} "
        f"10-K {st.session_state['active_year']}"
    )

# ---------------------------------------------------------------------------
# Chat interface
# ---------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state["messages"] = []

# Render chat history
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

query = st.chat_input("Ask a question about the filing...")

if query:
    if "active_ticker" not in st.session_state:
        st.warning("Please select a company and year, then click **Download & Ingest** first.")
    else:
        # Show user message
        st.session_state["messages"].append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.markdown(query)

        # Run analyst
        with st.chat_message("assistant"):
            with st.spinner("Analysing..."):
                result = run(
                    query,
                    ticker=st.session_state["active_ticker"],
                    fiscal_year=st.session_state["active_year"],
                )

            st.markdown(f"`{result['query_type']}`")
            st.markdown(result["answer"])

            if result["sources"]:
                with st.expander("Sources"):
                    for i, s in enumerate(result["sources"]):
                        st.markdown(
                            f"**[Doc {i+1}]** "
                            f"{s['metadata'].get('section','?')} | "
                            f"p.{s['metadata'].get('page_number','?')}"
                        )
                        st.caption(s["text"][:200])

            if result["mcp_data"]:
                with st.expander("Live Market Data"):
                    for d in result["mcp_data"]:
                        st.json(d)

        st.session_state["messages"].append({"role": "assistant", "content": result["answer"]})
