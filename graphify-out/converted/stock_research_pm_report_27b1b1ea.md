<!-- converted from stock_research_pm_report.docx -->


Stock Research AI Assistant
RAG + MCP Side Project

Product & Technical Specification Report

Version 1.0  |  April 2026

# 1. Executive Summary
This document defines the complete product and technical specification for the Stock Research AI Assistant — a side project built around a RAG + MCP architecture. The system enables users to upload SEC financial filings (10-K / 10-Q), ask natural-language questions, and receive AI-generated analysis grounded in both document knowledge and live market data.

The project serves two goals: (1) building a genuinely useful finance research tool, and (2) demonstrating production-grade AI engineering skills for interview purposes. This report covers the product vision, MVP scope, technical requirements, sprint plan, and upgrade roadmap.

# 2. Product Vision & Goals
## 2.1 Problem Statement
Financial analysts spend hours manually cross-referencing SEC filings with live market data. Existing tools either provide raw document access with no intelligence layer, or market data dashboards with no connection to primary source documents. There is no unified tool that combines both.

## 2.2 Target Users
- Retail investors conducting fundamental research
- Finance students learning to read 10-K / 10-Q filings
- AI/ML engineers building a portfolio project for finance-domain roles

## 2.3 Core Value Proposition

# 3. MVP Scope
## 3.1 In-Scope (MVP)
- Upload and index Apple, Microsoft, Nvidia 10-K / 10-Q PDFs from SEC EDGAR
- Ask natural-language questions answered from indexed filings
- Live stock data lookup (price, P/E, 52-week range)
- AI-synthesized response combining filing knowledge + live data
- Source citation with document name, section, and page number
- Basic Streamlit web UI

## 3.2 Out-of-Scope (MVP)
- User authentication / multi-user support
- Automated filing ingestion (manual upload only)
- Portfolio tracking or buy/sell recommendations
- Mobile-optimised UI
- Support for non-US filings (e.g., IFRS reports)

## 3.3 MVP Success Criteria


# 4. System Architecture
## 4.1 High-Level Architecture
The system is composed of four primary layers that process every user query:


## 4.2 Query Flow
Step 1: User submits natural-language query via Streamlit UI.
Step 2: Query Router (LLM classifier) determines required data sources.
Step 3a (if RAG): Hybrid retriever runs BM25 + vector search with company/year metadata filter, then Reciprocal Rank Fusion reranks results.
Step 3b (if MCP): MCP Server calls appropriate finance tool (fundamentals, peers, calendar).
Step 4: Claude Sonnet receives merged context from both sources.
Step 5: LLM generates structured response with inline citations.
Step 6: Streamlit renders answer with source panel showing page references.

## 4.3 Technology Stack


# 5. Technical Requirements
## 5.1 RAG Pipeline Requirements
### 5.1.1 Document Ingestion
- Must parse SEC 10-K / 10-Q PDFs preserving section structure (Item 1, Item 1A, Item 7, Item 8, etc.)
- Must detect and separately process financial tables — tables must not be chunked mid-row
- Must store per-chunk metadata: company ticker, filing_type, fiscal_year, section_name, page_number
- Must support re-ingestion when a new filing version is uploaded (upsert, not duplicate)

### 5.1.2 Chunking Strategy
- Narrative sections (Item 1, 1A, 7): sliding window, 512 tokens, 80-token overlap
- Financial tables (Item 8 statements): whole-table chunks, no splitting, add table_type metadata
- MD&A mixed sections: paragraph-level splitting with parent-document context stored in metadata

### 5.1.3 Hybrid Retrieval
- Must run BM25 keyword retrieval AND dense vector retrieval in parallel
- Must fuse results using Reciprocal Rank Fusion (k=60)
- Must support pre-retrieval metadata filtering (company, year, section) before semantic search
- Top-k default: 8 chunks. Must be configurable.

## 5.2 MCP Server Requirements

- All tools must implement fallback chain: Polygon.io → Alpha Vantage → yfinance
- All tools must return structured JSON with data_source field indicating which provider responded
- Tools must enforce a 5-second timeout per external API call

## 5.3 Query Router Requirements
- Must classify every query into one of three types before retrieval: RAG_ONLY, MCP_ONLY, HYBRID
- Classification prompt must include few-shot examples for each type
- Router must return structured JSON with query_type and reasoning field
- HYBRID queries must trigger parallel retrieval from both RAG and MCP, not sequential

## 5.4 Citation Requirements
- Every RAG-sourced claim must include: document_name, filing_type, fiscal_year, section, page_number
- Every MCP-sourced data point must include: data_source, ticker, timestamp_utc
- LLM prompt must instruct model to use inline citation markers (e.g., [Source 1, p.42])
- UI must render citation panel alongside main answer


# 6. Sprint Plan
## Sprint 1 — Foundation & RAG Pipeline  (Week 1)

## Sprint 2 — MCP Server  (Week 2)

## Sprint 3 — Integration, Agent & UI  (Week 3)

## Sprint 4 — Evaluation, Optimisation & Documentation  (Week 4)


# 7. Post-MVP Upgrade Roadmap
## 7.1 Priority Upgrades (High Impact, Low Effort)

## 7.2 Medium-Term Enhancements

## 7.3 Advanced (V2)
- Automated SEC EDGAR polling to detect new filings (scheduled ingestion)
- Financial entity extraction pipeline to store numeric facts in structured DB alongside vector DB
- LLM-as-judge evaluation replacing RAGAS for more nuanced finance-domain scoring
- Expanded MCP tools: options chain data, analyst ratings aggregation, earnings surprise history


# 8. Risk Register

# 9. Interview Talking Points
## 9.1 Architecture Decisions

# 10. Appendix — Project File Structure
stock-research-assistant/
├── app.py                        # Streamlit UI
├── rag/
│   ├── ingest.py                 # PDF → section-aware chunk → embed → Chroma
│   ├── retriever.py              # Hybrid retrieval (BM25 + vector + RRF)
│   └── chunker.py                # Structure-aware chunking logic
├── mcp/
│   └── stock_server.py           # FastMCP server with 5 finance tools
├── agent/
│   ├── router.py                 # Query type classifier (RAG/MCP/HYBRID)
│   └── analyst.py                # Orchestrator: router → retrieval → synthesis
├── eval/
│   └── ragas_eval.py             # RAGAS evaluation pipeline
├── data/
│   └── pdfs/                     # SEC EDGAR filing PDFs
├── tests/
│   └── query_eval_set.json       # 20 labelled queries for evaluation
└── requirements.txt


— End of Document —
| Dimension | Value Delivered |
| --- | --- |
| Accuracy | Answers grounded in actual SEC filings — not hallucinated data |
| Speed | Seconds vs. hours of manual cross-referencing |
| Traceability | Every claim cites source page and section |
| Completeness | Live market data + historical filings in one interface |
| Metric | Target | Measurement Method |
| --- | --- | --- |
| RAG Faithfulness | >= 0.80 | RAGAS faithfulness score |
| RAG Answer Relevancy | >= 0.75 | RAGAS answer_relevancy score |
| Live Data Latency | < 3 seconds | MCP tool response time |
| End-to-end Query Time | < 10 seconds | Streamlit response time |
| Citation Accuracy | 100% of answers cite source | Manual review of 20 sample queries |
| Layer | Component | Responsibility |
| --- | --- | --- |
| Input | Query Router | Classify query as RAG / MCP / Hybrid |
| Retrieval — Documents | Hybrid RAG Pipeline | Section-aware chunking + BM25 + Vector search with metadata filtering |
| Retrieval — Market Data | MCP Server | Finance-aware tools calling Polygon.io / Alpha Vantage |
| Generation | Claude Sonnet 4.6 | Synthesise context from both retrieval layers into grounded analysis |
| Output | Streamlit UI | Display answer + citations + data source tags |
| Component | Tool / Library | Rationale |
| --- | --- | --- |
| Frontend | Streamlit | Fast prototype UI, Python-native |
| LLM | Claude Sonnet 4.6 (claude-sonnet-4-6) | Best-in-class instruction following + long context |
| RAG Framework | LlamaIndex | Native hybrid search, PDF node parsing, metadata filtering |
| Vector Database | ChromaDB | Local, free, no infra overhead for side project |
| Embedding Model | BAAI/bge-small-en-v1.5 | Free, local, strong MTEB benchmark on formal English text |
| Keyword Search | BM25 (rank_bm25) | Precision on financial entity names, ticker symbols |
| MCP Framework | FastMCP | Lightweight MCP server implementation |
| Market Data (Primary) | Polygon.io (free tier) | Stable API, reliable data, proper rate limits |
| Market Data (Fallback) | Alpha Vantage | Secondary fallback if Polygon quota exceeded |
| Market Data (Tertiary) | yfinance | Last-resort fallback only |
| Evaluation | RAGAS | Faithfulness + answer relevancy scoring |
| PDF Source | SEC EDGAR | Free, authoritative primary source |
| Tool Name | Parameters | Data Source | Required Fields |
| --- | --- | --- | --- |
| get_fundamentals | ticker: str | Polygon.io | price, P/E, P/B, EV/EBITDA, ROE, market_cap |
| get_price_history | ticker: str, period: str | Polygon.io | OHLCV daily data, 52-week high/low |
| get_earnings_calendar | ticker: str | Alpha Vantage | next earnings date, EPS estimate |
| compare_peers | tickers: list[str] | Polygon.io | side-by-side fundamentals for up to 5 tickers |
| get_sec_filings_list | ticker: str | SEC EDGAR API | list of available 10-K/10-Q with dates |
| Story ID | User Story | Acceptance Criteria | Effort |
| --- | --- | --- | --- |
| S1-01 | As a dev, I can ingest a 10-K PDF and have it chunked and stored in ChromaDB | ingest.py runs without error on AAPL 10-K; ChromaDB contains chunks with correct metadata schema | M |
| S1-02 | As a dev, I can run a query and retrieve relevant chunks using vector search | retriever.py returns top-8 chunks for 'revenue growth'; all chunks include page_number metadata | M |
| S1-03 | As a dev, section-aware chunking does not split financial tables mid-row | Balance Sheet and Income Statement chunks are whole-table; verified by manual inspection | L |
| S1-04 | As a dev, BM25 retrieval is implemented and fused with vector results | Hybrid retrieval returns different (better) results than vector-only on ticker-specific queries | M |
| Story ID | User Story | Acceptance Criteria | Effort |
| --- | --- | --- | --- |
| S2-01 | As a dev, MCP server exposes get_fundamentals tool for any US ticker | Tool returns P/E, P/B, EV/EBITDA, ROE for AAPL within 3 seconds; fallback chain tested | M |
| S2-02 | As a dev, MCP server exposes compare_peers tool | Tool returns side-by-side data for AAPL, MSFT, NVDA | S |
| S2-03 | As a dev, MCP server exposes get_earnings_calendar tool | Tool returns next earnings date for any S&P 500 ticker | S |
| S2-04 | As a dev, MCP server exposes get_sec_filings_list tool | Tool returns list of available 10-K/10-Q filings for a ticker from SEC EDGAR | M |
| S2-05 | As a dev, all MCP tools implement fallback chain | When Polygon.io fails, Alpha Vantage is tried; data_source field reflects actual provider used | M |
| Story ID | User Story | Acceptance Criteria | Effort |
| --- | --- | --- | --- |
| S3-01 | As a user, I can type a query and the system routes it correctly | Router correctly classifies 20 test queries spanning RAG_ONLY, MCP_ONLY, HYBRID types (>= 90% accuracy) | L |
| S3-02 | As a user, HYBRID queries retrieve from both RAG and MCP in parallel | Response time for HYBRID <= RAG_ONLY + 1 second (not sequential) | M |
| S3-03 | As a user, every answer cites its sources with page numbers or data timestamps | Manual review: 100% of answers include at least one citation; no hallucinated page numbers | M |
| S3-04 | As a user, I can upload a PDF via the Streamlit UI and ask questions about it | End-to-end: upload → ingest → query → cited answer works without terminal interaction | L |
| S3-05 | As a user, I can run a multi-company comparison query | Query 'Compare AAPL vs MSFT revenue growth' returns structured comparison using both filing data and live fundamentals | L |
| Story ID | User Story | Acceptance Criteria | Effort |
| --- | --- | --- | --- |
| S4-01 | As a dev, I can measure RAG quality using RAGAS | RAGAS faithfulness >= 0.80 and answer_relevancy >= 0.75 on 20-query eval set | M |
| S4-02 | As a dev, chunking strategy improvements are A/B tested | Structured chunk strategy vs. fixed-size shows improvement on RAGAS scores (documented) | L |
| S4-03 | As a dev, GitHub README includes architecture diagram, demo GIF, and setup instructions | Any engineer can clone and run the project in under 15 minutes following README | M |
| S4-04 | As a dev, I have written interview prep notes explaining each technical decision | Notes cover: chunking strategy, hybrid search rationale, MCP vs hardcoded API, eval methodology | S |
| Upgrade | Why | Estimated Effort |
| --- | --- | --- |
| Metadata filtering before vector search | Eliminates cross-company noise; required for multi-filing support | 1 day |
| Fallback chain for market data APIs | yfinance alone is unreliable in production; Polygon free tier is sufficient | 0.5 days |
| Few-shot examples in Query Router prompt | Improves routing accuracy from ~75% to ~90%+ on edge cases | 0.5 days |
| Upgrade | Why | Estimated Effort |
| --- | --- | --- |
| Multi-hop reasoning for peer comparison | Key demo differentiator: 'Compare AAPL vs MSFT vs GOOGL AI strategy vs valuation' | 3 days |
| Parent-document retrieval | Return surrounding context for small retrieved chunks — improves coherence | 1 day |
| Streaming response in UI | UX improvement for long synthesis responses | 0.5 days |
| Persistent ChromaDB across sessions | Currently re-ingests on restart; persistence enables production-like behaviour | 0.5 days |
| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| yfinance rate limiting / data failure | High | Medium | Implement fallback chain: Polygon.io → Alpha Vantage → yfinance |
| RAG hallucination on numeric data | Medium | High | Structure-aware chunking keeps tables intact; RAGAS evaluation gates release |
| Context window overflow for long queries | Medium | Medium | Metadata pre-filter reduces retrieved chunks; set hard cap of 8 chunks |
| SEC EDGAR PDF format changes | Low | Medium | Abstract PDF parser behind interface; swap implementation without changing RAG logic |
| ChromaDB performance at scale | Low | Low | Acceptable for side project scope; migration path to Qdrant/Weaviate documented |
| Question | Answer Summary |
| --- | --- |
| Why RAG instead of full-document in context? | 10-K filings are 150-250 pages, far exceeding practical context windows. RAG retrieves only the top-8 most relevant chunks, reducing cost by ~95% and improving precision. |
| Why Hybrid Search (BM25 + Vector)? | Vector search excels at semantic similarity but fails on exact financial terms (e.g., 'EBITDA margin Q3 FY2023'). BM25 handles keyword precision. RRF fusion combines both strengths. |
| Why structure-aware chunking instead of fixed-size? | Fixed-size chunks split financial tables mid-row, destroying numerical context. Section-aware chunking preserves table integrity and allows metadata filtering by document section. |
| Why MCP instead of hardcoded API calls? | MCP lets the LLM autonomously decide when to call a tool and with what parameters, enabling flexible agentic behaviour without brittle if/else routing logic. |
| How do you evaluate RAG quality? | RAGAS scores faithfulness (is the answer grounded in retrieved context?) and answer_relevancy (does it answer the question?). Target: faithfulness >= 0.80, relevancy >= 0.75. |
| What breaks first at scale? | ChromaDB and local embeddings. Migration path: swap ChromaDB for Qdrant/Weaviate and bge-small for a hosted embedding endpoint (Voyage AI or OpenAI). |