# Graph Report - .  (2026-05-09)

## Corpus Check
- 26 files · ~150,656 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 251 nodes · 338 edges · 19 communities (17 shown, 2 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 36 edges (avg confidence: 0.79)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Agent Query Flow|Agent Query Flow]]
- [[_COMMUNITY_RAGAS Harness Internals|RAGAS Harness Internals]]
- [[_COMMUNITY_MCP Market Tools|MCP Market Tools]]
- [[_COMMUNITY_Architecture Rationale Docs|Architecture Rationale Docs]]
- [[_COMMUNITY_EDGAR Ingestion|EDGAR Ingestion]]
- [[_COMMUNITY_Analyst Synthesis Helpers|Analyst Synthesis Helpers]]
- [[_COMMUNITY_Azure Migration Plan|Azure Migration Plan]]
- [[_COMMUNITY_Filing Chunking|Filing Chunking]]
- [[_COMMUNITY_Streamlit MCP UI|Streamlit MCP UI]]
- [[_COMMUNITY_Hybrid Retrieval|Hybrid Retrieval]]
- [[_COMMUNITY_Project Memory and Filings|Project Memory and Filings]]
- [[_COMMUNITY_Evaluation Observability|Evaluation Observability]]
- [[_COMMUNITY_Evaluation Limitations|Evaluation Limitations]]
- [[_COMMUNITY_Agent Instructions|Agent Instructions]]
- [[_COMMUNITY_FastMCP Server|FastMCP Server]]

## God Nodes (most connected - your core abstractions)
1. `run_evaluation()` - 12 edges
2. `chunk_filing()` - 10 edges
3. `Analyst Orchestrator Run` - 10 edges
4. `get_fundamentals()` - 9 edges
5. `_run_mcp()` - 8 edges
6. `Hybrid Retrieval with BM25 Vector and RRF` - 8 edges
7. `Polygon Alpha Vantage yfinance Fallback Chain` - 8 edges
8. `ingest_from_edgar()` - 7 edges
9. `_unavailable()` - 7 edges
10. `run()` - 7 edges

## Surprising Connections (you probably didn't know these)
- `Microsoft AI and Cloud Strategy` --semantically_similar_to--> `Target Azure Architecture`  [INFERRED] [semantically similar]
  data/pdfs/MSFT_10K_2025.pdf → docs/azure_deployment_report.md
- `Azure AI Search Hybrid Retrieval Backend` --semantically_similar_to--> `Hybrid Retrieval with BM25 Vector and RRF`  [INFERRED] [semantically similar]
  docs/azure_deployment_report.md → graphify-out/converted/stock_research_pm_report_27b1b1ea.md
- `Query Router Hybrid RAG MCP Grounded Answer Visual` --references--> `Citation Schema for Filing and Market Sources`  [INFERRED]
  docs/assets/demo.gif → graphify-out/converted/stock_research_pm_report_27b1b1ea.md
- `Azure Blob Storage for SEC PDFs` --shares_data_with--> `Apple 2025 Form 10-K Filing`  [INFERRED]
  docs/azure_deployment_report.md → data/pdfs/AAPL_10K_2025.pdf
- `EDGAR Ingest Pipeline` --semantically_similar_to--> `PDF Ingest Filing Pipeline`  [INFERRED] [semantically similar]
  edgar.py → rag/ingest.py

## Hyperedges (group relationships)
- **SEC Filing Ingest Flow** — edgar_download_and_parse, chunker_chunk_filing, ingest_upsert_to_chroma [EXTRACTED 1.00]
- **Analyst Hybrid Answer Flow** — router_classify_query, analyst_run_rag, analyst_run_mcp [EXTRACTED 1.00]
- **RAGAS Observability Flow** — eval_run_pipeline, eval_detail_rows, concept_eval_observability [EXTRACTED 1.00]
- **RAG Pipeline Foundation** — stock_research_pm_report_structure_aware_chunking, stock_research_pm_report_hybrid_retrieval, stock_research_pm_report_citation_schema [EXTRACTED 1.00]
- **MCP Market Data Boundary** — stock_research_pm_report_mcp_fallback_chain, memory_structured_unavailable_market_data, readme_optional_yfinance_disabled [EXTRACTED 1.00]
- **Azure Cloud Migration Core** — azure_deployment_report_container_apps, azure_deployment_report_ai_search, azure_deployment_report_blob_storage [EXTRACTED 1.00]

## Communities (19 total, 2 thin omitted)

### Community 0 - "Agent Query Flow"
Cohesion: 0.09
Nodes (34): HYBRID Filing-Focused RAG Query Builder, Answer Text Normalizer, Fiscal Year Resolver, Analyst Orchestrator Run, Analyst RAG Retrieval Branch, Context-Grounded Financial Analyst Prompt, Chat Query Action, Download and Ingest Button Action (+26 more)

### Community 1 - "RAGAS Harness Internals"
Cohesion: 0.09
Nodes (29): _build_samples(), _context_preview(), _is_multi_company_sample(), _make_eval_embeddings(), _make_llm_judge(), _make_openai_client(), _merge_detail_rows(), _primary_ticker() (+21 more)

### Community 2 - "MCP Market Tools"
Cohesion: 0.13
Nodes (26): Select finance tools based on the user's market-data need.      The eval set cur, _run_mcp(), get_earnings_calendar(), _get_eps_from_polygon(), get_financials(), get_fundamentals(), _get_fundamentals_from_yfinance(), get_peers() (+18 more)

### Community 3 - "Architecture Rationale Docs"
Cohesion: 0.09
Nodes (25): Core Finance RAG Design Principles, Query Router Hybrid RAG MCP Grounded Answer Visual, Demo GIF Streamlit Walkthrough, Structure-Aware Chunking Interview Rationale, Hybrid Search Interview Rationale, MCP Tool Boundary Interview Rationale, One-Minute Finance RAG MCP Pitch, Structured Unavailable Market Data Response (+17 more)

### Community 4 - "EDGAR Ingestion"
Cohesion: 0.12
Nodes (21): fetch_years(), download_and_parse(), _extract_html_tables(), get_filings(), ingest_from_edgar(), SEC EDGAR auto-download pipeline.  Usage:     from edgar import ingest_from_edga, Download a SEC HTML filing and parse it into page dicts.      Returns:         [, Auto-download and ingest a SEC filing into ChromaDB.      Args:         ticker: (+13 more)

### Community 5 - "Analyst Synthesis Helpers"
Cohesion: 0.13
Nodes (16): _build_rag_query(), _clean_answer_text(), Orchestrator: router → parallel retrieval (RAG + MCP) → Claude synthesis.  Flow:, Normalize model output for Streamlit display.      The model occasionally emits, Prefer the fiscal year explicitly mentioned in the user query.      The Streamli, Build a filing-focused retrieval query.      HYBRID questions often include live, _resolve_fiscal_year(), run() (+8 more)

### Community 6 - "Azure Migration Plan"
Cohesion: 0.12
Nodes (18): Azure AI Search Hybrid Retrieval Backend, Azure Blob Storage for SEC PDFs, Azure Container Apps for Streamlit and MCP, Azure Key Vault for API Secrets, Local Chroma vs Azure AI Search RAGAS A/B Test, Application Insights Retrieval and Tool Observability, Target Azure Architecture, S5 Azure Deployment Foundation (+10 more)

### Community 7 - "Filing Chunking"
Cohesion: 0.18
Nodes (14): Chunk, chunk_filing(), _detect_section(), _format_page_with_tables(), _format_table_chunk(), _has_financial_table(), _is_table_section(), Structure-aware chunking for SEC 10-K / 10-Q filings.  Strategy: - Narrative sec (+6 more)

### Community 8 - "Streamlit MCP UI"
Cohesion: 0.19
Nodes (16): Analyst MCP Tool Branch, Cached Filing Year Selector, Streamlit Stock Research UI, MCP data_source Response Contract, Ticker to CIK Map, Get EDGAR Filings, Get Earnings Calendar Tool, Get Financials Tool (+8 more)

### Community 9 - "Hybrid Retrieval"
Cohesion: 0.2
Nodes (13): bm25_search(), _finance_boost(), _get_embedding_model(), hybrid_search(), Hybrid retrieval: BM25 + dense vector search, fused with Reciprocal Rank Fusion, Apply small domain boosts for SEC sections and financial-statement tables., Full hybrid search: BM25 + vector → RRF → top_k results.      Args:         quer, Load the embedding model lazily to keep non-vector diagnostics fast. (+5 more)

### Community 10 - "Project Memory and Filings"
Cohesion: 0.17
Nodes (12): Apple Geographic Reportable Segments, Apple 2025 Form 10-K Filing, Apple 2025 Risk Factors, Senior RAGAS Harness Engineer Mode, Current Project State Memory, RAGAS Harness Fixes Summary, Latest RAGAS Scores, Portfolio-Grade SEC 10-K Research MVP (+4 more)

### Community 11 - "Evaluation Observability"
Cohesion: 0.47
Nodes (6): Evaluation Observability Principle, RAGAS Sample Splitter, Per-Question Evaluation Details, RAGAS Evaluation Runner, Evaluation Pipeline Wrapper, Unsupported Capability Filter

### Community 12 - "Evaluation Limitations"
Cohesion: 0.67
Nodes (3): Per-Question RAGAS Evaluation Methodology, Multi-Company HYBRID Gap, Unsupported Capability Policy

## Knowledge Gaps
- **99 isolated node(s):** `SEC EDGAR auto-download pipeline.  Usage:     from edgar import ingest_from_edga`, `Extract SEC HTML tables as tab-separated text.      Financial tables must stay i`, `Represent extracted HTML tables as pseudo-pages for the chunker.`, `Return list of filings for a ticker, sorted newest first.      Each item: {"date`, `Download a SEC HTML filing and parse it into page dicts.      Returns:         [` (+94 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_run_rag()` connect `Analyst Synthesis Helpers` to `Hybrid Retrieval`, `Filing Chunking`?**
  _High betweenness centrality (0.069) - this node is a cross-community bridge._
- **Why does `chunk_filing()` connect `Filing Chunking` to `EDGAR Ingestion`?**
  _High betweenness centrality (0.048) - this node is a cross-community bridge._
- **Why does `ingest_from_edgar()` connect `EDGAR Ingestion` to `Filing Chunking`?**
  _High betweenness centrality (0.043) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `chunk_filing()` (e.g. with `ingest_from_edgar()` and `ingest_filing()`) actually correct?**
  _`chunk_filing()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `_run_mcp()` (e.g. with `get_sec_filings_list()` and `get_earnings_calendar()`) actually correct?**
  _`_run_mcp()` has 5 INFERRED edges - model-reasoned connections that need verification._
- **What connects `SEC EDGAR auto-download pipeline.  Usage:     from edgar import ingest_from_edga`, `Extract SEC HTML tables as tab-separated text.      Financial tables must stay i`, `Represent extracted HTML tables as pseudo-pages for the chunker.` to the rest of the system?**
  _99 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Agent Query Flow` be split into smaller, more focused modules?**
  _Cohesion score 0.09 - nodes in this community are weakly interconnected._