# Stock Research AI Assistant

A finance-domain AI assistant built around a **RAG + MCP architecture**.

The project combines SEC filing retrieval with live market-data tools so users can ask questions such as:

- "What were Nvidia's main supply chain risks in its FY2025 10-K?"
- "What is Apple's current stock price and P/E ratio?"
- "Compare Nvidia's FY2025 gross margin with its current valuation."

The core idea is simple: **RAG handles historical filing knowledge, MCP handles live market data, and the agent decides when to use each source.**

## Why RAG + MCP

Financial research questions usually need two different types of information:

- **Primary-source document evidence** from SEC filings, such as revenue, segment performance, risk factors, MD&A commentary, and financial statements.
- **Current market data** such as price, valuation ratios, market cap, earnings dates, and peer comparisons.

Pure RAG is not enough because filings are historical and cannot answer live market questions. Pure API tooling is also not enough because market data APIs do not contain the detailed management commentary and risk disclosures inside 10-K filings.

This project uses both:

- **RAG pipeline**: parses SEC filings, creates finance-aware chunks, stores embeddings in ChromaDB, and retrieves evidence with hybrid search.
- **MCP server**: exposes finance tools through FastMCP and returns structured JSON with a `data_source` field.
- **Agent layer**: classifies each query as `RAG_ONLY`, `MCP_ONLY`, or `HYBRID`, then synthesizes an answer with citations.

## Architecture

```text
User Query
   |
   v
Query Router
   |
   +-- RAG_ONLY ------------------+
   |                              |
   v                              v
Hybrid RAG Retriever        MCP Finance Tools
BM25 + Vector + RRF         Polygon -> Alpha Vantage -> yfinance
   |                              |
   +--------------+---------------+
                  |
                  v
          Analyst Orchestrator
                  |
                  v
      Grounded answer with citations
```

## Project Structure

```text
.
├── app.py                     # Streamlit UI
├── edgar.py                   # SEC EDGAR download and ingestion helper
├── rag/
│   ├── chunker.py             # Structure-aware chunking
│   ├── ingest.py              # PDF -> chunks -> embeddings -> ChromaDB
│   ├── retriever.py           # Hybrid retrieval: BM25 + vector + RRF
│   └── chroma_client.py       # Shared ChromaDB client
├── tools/
│   └── stock_server.py        # FastMCP finance tools
├── agent/
│   ├── router.py              # Query classifier
│   └── analyst.py             # RAG/MCP orchestration and answer synthesis
├── eval/
│   └── ragas_eval.py          # RAGAS evaluation pipeline
├── tests/
│   └── query_eval_set.json    # Labelled evaluation queries
└── data/pdfs/                 # Demo SEC filing PDFs
```

## Key Design Decisions

### 1. Hybrid Retrieval Instead of Pure Vector Search

The retriever uses **BM25 + dense vector search + Reciprocal Rank Fusion**.

This matters in finance because exact terms like `EBITDA`, `Form 10-K`, `Item 7`, `Data Center`, or ticker-specific language are often better captured by keyword retrieval, while semantic retrieval is better for broad management commentary questions.

### 2. Structure-Aware Chunking

Narrative filing sections use sliding-window chunking, while financial statement table sections are kept as whole chunks.

This avoids a common finance RAG failure mode: fixed-size chunking can split financial tables mid-row, causing the model to lose the relationship between line items, years, and values.

### 3. MCP for Live Market Data

The MCP server exposes finance tools such as stock price and fundamentals lookup. Tool responses include `data_source`, so the answer layer can distinguish between filing evidence and live API data.

Market data fallback order:

```text
Polygon.io -> Alpha Vantage -> yfinance
```

`yfinance` is treated as an optional last-resort fallback because it is less reliable for production-style financial workflows.

### 4. Query Routing

The router classifies each query before retrieval:

- `RAG_ONLY`: filing-specific questions
- `MCP_ONLY`: live market-data questions
- `HYBRID`: questions requiring both filing evidence and market data

This keeps the system efficient and makes the data-source boundary explicit.

## Tech Stack

- **Frontend**: Streamlit
- **RAG**: ChromaDB, sentence-transformers, BM25
- **Embedding model**: `BAAI/bge-small-en-v1.5`
- **MCP**: FastMCP
- **Market data**: Polygon.io, Alpha Vantage, optional yfinance fallback
- **LLM orchestration**: OpenAI client
- **Evaluation**: RAGAS
- **PDF parsing**: pdfplumber

## Setup

```bash
conda activate finance_rag
pip install -r requirements.txt
```

Create a local `.env` file:

```bash
OPENAI_API_KEY=your_openai_key
POLYGON_API_KEY=your_polygon_key
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key
ENABLE_YFINANCE_FALLBACK=false
```

## Run the App

```bash
streamlit run app.py
```

## Ingest Demo Filings

```bash
python rag/ingest.py
```

This parses the PDF filings in `data/pdfs/`, chunks them, embeds them, and stores the vectors in local ChromaDB at `data/chroma/`.

## Run Evaluation

```bash
python eval/ragas_eval.py
```

The evaluation set includes RAG-only, MCP-only, and hybrid finance questions.

## Current Scope

The current project is a portfolio-grade MVP focused on:

- SEC 10-K filing analysis
- Hybrid document retrieval
- Live market-data tool calls
- Query routing between RAG and MCP
- Citation-aware answer generation
- RAGAS-based evaluation

Future improvements include broader SEC filing support, stronger table extraction, multi-company hybrid comparison, and production-grade MCP tool coverage.
