# Stock Research AI Assistant

RAG + MCP side project for SEC filing research and live market data analysis.

## Overview

This project lets a user load SEC 10-K filings, ask natural-language questions, and receive grounded answers with document citations and market data context.

Core components:

- `app.py` - Streamlit chat UI
- `rag/` - PDF parsing, structure-aware chunking, ChromaDB ingestion, hybrid retrieval
- `tools/stock_server.py` - FastMCP finance tools with market data fallback behavior
- `agent/` - query routing and answer orchestration
- `eval/` - RAGAS evaluation pipeline
- `tests/query_eval_set.json` - labelled evaluation questions

## Requirements

- Python 3.12
- Conda environment: `finance_rag`
- API keys in `.env`

```bash
conda activate finance_rag
pip install -r requirements.txt
```

Create `.env` locally:

```bash
OPENAI_API_KEY=your_openai_key
POLYGON_API_KEY=your_polygon_key
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key
ENABLE_YFINANCE_FALLBACK=false
```

## Run

```bash
streamlit run app.py
```

## Ingest Filings

```bash
python rag/ingest.py
```

This parses the SEC filing PDFs in `data/pdfs/`, creates structure-aware chunks, embeds them with `BAAI/bge-small-en-v1.5`, and upserts them into local ChromaDB under `data/chroma/`.

## Evaluation

```bash
python eval/ragas_eval.py
```

## Finance Domain Notes

- Narrative filing text uses sliding-window chunking.
- Financial statement table sections are kept whole to avoid breaking rows and numeric context.
- Retrieval uses hybrid search: BM25 + vector search + Reciprocal Rank Fusion.
- Market data tools should prefer Polygon.io, then Alpha Vantage, with yfinance only as an optional last-resort fallback.
- MCP tool responses include `data_source` so downstream answers can cite the provider.
