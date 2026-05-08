# Stock Research AI Assistant — Azure Deployment Report

## 1. Executive Summary

這份 report 的目的，是把目前本機版的 Stock Research AI Assistant，轉換成一個可以部署到 Azure、可被外部使用者透過網址存取、也能在面試中清楚說明 cloud deployment 經驗的版本。

目前專案已經有很好的 AI engineering 核心：

- RAG：SEC filing ingestion、structure-aware chunking、Hybrid Search、citation
- MCP：finance tools、market data fallback chain、structured JSON output
- Agent：RAG_ONLY / MCP_ONLY / HYBRID router
- Evaluation：RAGAS per-question details、retrieval trace、tool trace
- UI：Streamlit demo flow

Azure 化的重點不是把整個本機資料夾原封不動丟上雲端，而是把本機元件拆成 cloud-native services：

```text
Local Streamlit + ChromaDB + local PDFs + .env
        |
        v
Azure Container Apps + Azure AI Search + Blob Storage + Key Vault + Azure OpenAI
```

建議採用分階段改造：先完成最小可展示 Azure demo，再逐步替換 retriever、storage、secrets、observability。這樣可以保留目前 repo 的核心價值，也能合理展示 Azure AI Engineer deployment 經驗。

---

## 2. Source Document Comparison

### 2.1 對照 `stock_research_pm_report.docx`

PM report 定義的 MVP 核心是：

- 使用者上傳 SEC 10-K / 10-Q PDF
- 系統進行 section-aware chunking 與 Hybrid Search
- live stock data 透過 MCP tools 查詢
- Claude / LLM 合成 grounded answer
- 回答必須包含 document citation 與 data source
- Sprint 4 要用 RAGAS 評估 faithfulness 與 answer relevancy

Azure deployment 應該延伸這個設計，而不是改變產品方向。

| PM report requirement | 本機版目前做法 | Azure 版建議 |
| --- | --- | --- |
| SEC PDF storage | `data/pdfs/` | Azure Blob Storage |
| Chunk + metadata | `rag/chunker.py` | 保留 Python chunking，輸出到 Azure AI Search |
| Hybrid retrieval | BM25 + ChromaDB vector + RRF | Azure AI Search hybrid search |
| Market data tools | FastMCP + Polygon / Alpha Vantage / yfinance fallback | FastMCP 部署到 Azure Container Apps |
| LLM synthesis | OpenAI / local env config | Azure OpenAI 或 Azure AI Foundry Models |
| Citation | section + page number / data_source | 保留 citation schema，metadata 存入 Azure AI Search |
| Evaluation | `eval/ragas_eval.py` | 保留本機與 CI 執行，可把 results 存 Blob |
| UI | Streamlit local | Streamlit container on Azure Container Apps |

結論：Azure 化是 PM report 的自然延伸，尤其 Azure AI Search 的 hybrid retrieval 與專案原本 BM25 + vector + RRF 的設計非常一致。

### 2.2 對照 `AGENTS.md`

`AGENTS.md` 強調幾個嚴格原則：

- 財務表格不能切斷，必須 whole-table chunk
- 永遠用 Hybrid Search，不用純向量搜尋
- 市場數據必須 fallback chain，不單靠 yfinance
- 每個 chunk 必須有 metadata
- MCP tool response 必須有 `data_source`

Azure 版必須保留這些原則。

| AGENTS.md rule | Azure deployment implication |
| --- | --- |
| table chunks must stay whole | 不應交給黑箱 document intelligence 自動亂切；仍由 `rag/chunker.py` 控制 chunking |
| Hybrid Search is mandatory | Azure AI Search index 必須同時有 text fields 與 vector fields |
| fallback chain required | Azure 上的 MCP server 仍保留 Polygon -> Alpha Vantage -> optional yfinance |
| metadata required | Azure AI Search schema 必須包含 `company`, `ticker`, `filing_type`, `fiscal_year`, `section`, `page_number`, `section_type`, `table_index` |
| `data_source` required | 所有 MCP tool output 與 UI citation panel 繼續顯示 `data_source` |

關鍵判斷：不要為了「Azure 化」犧牲 finance-domain correctness。Azure 是 deployment layer，不是取代你目前 chunking / routing / fallback logic 的理由。

### 2.3 對照 `MEMORY.md`

`MEMORY.md` 顯示目前專案已經通過主要 RAGAS quality gate：

```text
Faithfulness: 0.9297
Answer Relevancy: 0.8600
Context Recall: 0.6007
```

這代表現在不應該先大改答案生成，而是先把 end-to-end demo 做完整，再做 Azure deploy。

Azure roadmap 應該尊重目前狀態：

| Current state from MEMORY.md | Azure strategy |
| --- | --- |
| faithfulness / relevancy 已達標 | 保留 agent synthesis prompt，不先大改 |
| context recall 未達 0.70 | Azure AI Search migration 後要重新跑 RAGAS，比較 Chroma vs Azure AI Search |
| multi-company HYBRID 尚未實作 | Azure demo 第一版先限制單 ticker |
| market data fields incomplete | Azure deployment 不會自動解決資料源欄位不足；仍需 structured unavailable |
| 建議下一步是 Streamlit demo | Azure S5 應接在 Streamlit end-to-end citation flow 後 |

---

## 3. Target Azure Architecture

### 3.1 High-Level Architecture

```text
User Browser
    |
    v
Azure Container Apps
    - Streamlit UI
    - Agent Orchestrator
    |
    +--> Azure OpenAI / Azure AI Foundry Models
    |       - query routing
    |       - answer synthesis
    |       - optional embedding generation
    |
    +--> Azure AI Search
    |       - SEC filing chunks
    |       - metadata filters
    |       - hybrid search
    |       - vector fields
    |
    +--> MCP Finance Server
    |       - deployed as a separate Container App
    |       - Polygon.io -> Alpha Vantage -> optional yfinance
    |
    +--> Azure Blob Storage
    |       - raw SEC PDFs
    |       - optional eval artifacts
    |
    +--> Azure Key Vault
    |       - API keys
    |       - service secrets
    |
    +--> Application Insights / Azure Monitor
            - latency
            - errors
            - tool calls
            - retrieval diagnostics
```

### 3.2 Why This Architecture Fits This Project

Azure AI Search 適合取代本機 ChromaDB + BM25 layer，因為它支援 full-text search、vector search、metadata filters，以及 hybrid query 的 RRF fusion。這正好對應本專案「財務術語 exact match + semantic retrieval」的核心需求。

Azure Container Apps 適合部署 Streamlit UI 和 MCP server，因為目前專案是 Python web app + tool server，不需要一開始就上 AKS。Container Apps 可以展示 containerization、microservice boundary、ingress、scaling、secrets 與 monitoring。

Blob Storage 適合保存 SEC PDFs，因為 PDF 是 unstructured object data，而且未來可以支援 user upload 或 automated EDGAR polling。

Key Vault 適合管理 Polygon、Alpha Vantage、Azure OpenAI、Azure AI Search 等 API keys，避免 production deployment 繼續依賴 `.env`。

---

## 4. Local-to-Azure Component Mapping

| 本機元件 | 目前位置 | Azure 目標 | 改造重點 |
| --- | --- | --- | --- |
| Streamlit UI | `app.py` | Azure Container Apps | 加 Dockerfile、health check、環境變數 |
| Agent orchestrator | `agent/analyst.py` | 與 UI 同 container 或獨立 API | 保留 router + synthesis；抽象 LLM client |
| Query router | `agent/router.py` | Azure OpenAI-backed router | 保留 RAG/MCP/HYBRID schema |
| PDF storage | `data/pdfs/` | Azure Blob Storage | 新增 storage adapter |
| Chunking | `rag/chunker.py` | 保留 Python implementation | 不交給 Azure 黑箱切表格 |
| ChromaDB | `rag/chroma_client.py` | Azure AI Search | 新增 retriever backend adapter |
| Hybrid retriever | `rag/retriever.py` | Azure AI Search hybrid query | 保留 local backend 作為 dev fallback |
| MCP server | `tools/stock_server.py` | Separate Container App | HTTP/MCP endpoint 化、secrets 改用 Key Vault |
| Evaluation | `eval/ragas_eval.py` | 本機 / CI / scheduled job | 支援 Azure retriever backend 對照測試 |
| `.env` | repo root | Azure Key Vault + Container Apps secrets | local dev 保留 `.env` |

---

## 5. Recommended Migration Plan

### Phase 0 — 保留本機 MVP 穩定性

目標：不要一開始就把所有東西換成 Azure。先確認本機 end-to-end demo 是穩的。

建議完成：

- Streamlit query flow
- citation panel
- HYBRID response 顯示 filing evidence + market data
- local RAGAS baseline 保留

完成條件：

```text
streamlit run app.py
python eval/ragas_eval.py
```

都能穩定執行。

### Phase 1 — Containerize UI and MCP

目標：先讓專案可以在 Azure 上跑起來。

新增檔案建議：

```text
Dockerfile
.dockerignore
deploy/azure-container-apps.md
```

建議先部署兩個 container apps：

```text
stock-research-ui
stock-research-mcp
```

第一版可以先保留 ChromaDB 在 container 內或掛載 volume，但這只適合 demo，不適合長期 production。

面試價值：

> I containerized both the Streamlit UI and MCP finance server, then deployed them to Azure Container Apps with environment-based configuration.

### Phase 2 — Add Azure OpenAI Client Abstraction

目標：讓 LLM provider 可以從 local OpenAI / Claude 風格設定切換到 Azure OpenAI。

建議新增：

```text
agent/llm_client.py
```

設計重點：

- `LLM_PROVIDER=openai | azure_openai`
- local dev 可用 `.env`
- cloud deploy 使用 Container Apps secrets / Key Vault
- router 和 analyst 不直接依賴特定 provider SDK

面試價值：

> The model layer is provider-abstracted, so local prototyping and Azure enterprise deployment share the same orchestration logic.

### Phase 3 — Move PDFs to Azure Blob Storage

目標：不要讓 production PDF 靠 container filesystem。

建議新增：

```text
storage/blob_store.py
```

Blob path 建議：

```text
sec-filings/{ticker}/{fiscal_year}/{filing_type}/{document_name}.pdf
```

metadata 建議：

```text
ticker
company
fiscal_year
filing_type
filing_date
source_url
ingested_at_utc
```

Finance domain 注意：

- historical filing question 必須使用對應 fiscal year 的 SEC PDF，不要用 live API 猜歷史數字。
- 若同一家公司同一年有 amended filing，要保留 document version 或 accession number。

### Phase 4 — Replace ChromaDB with Azure AI Search Adapter

目標：把 retrieval backend cloud 化，同時保留 Hybrid Search 原則。

建議新增：

```text
rag/search_backend.py
rag/azure_search_backend.py
```

Azure AI Search index schema 建議：

```text
id: string
content: searchable string
content_vector: vector
ticker: filterable string
company: filterable string
filing_type: filterable string
fiscal_year: filterable int
section: filterable/searchable string
section_type: filterable string
page_number: filterable int
table_index: filterable int
document_name: filterable string
source_blob_url: string
chunk_type: filterable string
```

Query behavior：

```text
text query: BM25 / full-text
vector query: embedding similarity
filter: ticker + fiscal_year + filing_type when available
fusion: Azure AI Search hybrid RRF
top_k: default 8
```

Finance domain 注意：

- table chunks 不可在 upload 到 Azure AI Search 前被重新切斷。
- `section`, `page_number`, `fiscal_year` 必須可 filter / retrievable，否則 citation 會壞。
- Migration 後一定要跑 RAGAS A/B：Chroma local vs Azure AI Search。

### Phase 5 — Secrets and Observability

目標：讓 demo 接近 production。

Key Vault 應管理：

```text
AZURE_OPENAI_API_KEY
AZURE_OPENAI_ENDPOINT
AZURE_SEARCH_API_KEY
AZURE_SEARCH_ENDPOINT
POLYGON_API_KEY
ALPHA_VANTAGE_API_KEY
```

Application Insights / Azure Monitor 應追蹤：

```text
query_id
query_type
ticker
fiscal_year
retrieval_latency_ms
mcp_latency_ms
llm_latency_ms
total_latency_ms
retrieved_chunk_count
called_tools
data_source
error_type
```

面試價值：

> I added observability around retrieval, tool calls, and answer synthesis so failures can be diagnosed as retrieval, API, or generation issues.

---

## 6. Suggested Azure Sprint Plan

### S5 — Azure Deployment Foundation

| Story ID | User Story | Acceptance Criteria | Effort |
| --- | --- | --- | --- |
| S5-01 | As a dev, I can run the app in Docker | `docker build` and `docker run` start Streamlit successfully | M |
| S5-02 | As a dev, I can deploy Streamlit to Azure Container Apps | Public URL loads app and accepts a query | M |
| S5-03 | As a dev, I can deploy MCP server separately | UI can call MCP endpoint from Azure | M |
| S5-04 | As a dev, secrets are not stored in repo or image | API keys come from Container Apps secrets / Key Vault | S |

### S6 — Azure RAG Backend

| Story ID | User Story | Acceptance Criteria | Effort |
| --- | --- | --- | --- |
| S6-01 | As a dev, PDFs are stored in Blob Storage | Ingestion can read PDF from Blob path | M |
| S6-02 | As a dev, chunks are indexed into Azure AI Search | Index contains chunks with required metadata | L |
| S6-03 | As a dev, Azure backend supports hybrid retrieval | Query returns top-k chunks using text + vector + filters | L |
| S6-04 | As a dev, Azure Search and local Chroma can be A/B tested | RAGAS can run with `RAG_BACKEND=local` or `azure_search` | M |

### S7 — Production-Style Demo

| Story ID | User Story | Acceptance Criteria | Effort |
| --- | --- | --- | --- |
| S7-01 | As a user, I can use the app from a public Azure URL | End-to-end RAG_ONLY / MCP_ONLY / HYBRID works | M |
| S7-02 | As a dev, I can observe failures | Logs show retrieval/tool/LLM latency and errors | M |
| S7-03 | As a dev, I can limit public demo usage | Basic auth or access control prevents uncontrolled usage | M |
| S7-04 | As a candidate, I can explain Azure architecture in interview | README + interview notes include Azure deployment diagram | S |

---

## 7. What Not to Move to Azure First

不要第一輪就做這些：

- AKS
- complex VNet / Private Link architecture
- full CI/CD pipeline
- multi-user auth
- advanced valuation engine
- n8n automation
- fully automated SEC EDGAR polling

原因：這些會分散主線。你目前最有價值的主線是 finance-domain RAG + MCP + Azure deployment。先把 demo URL 和 Azure AI Search migration 做出來，面試說服力就夠強。

---

## 8. Risks and Finance-Domain Traps

### 8.1 Azure Search migration may change retrieval behavior

ChromaDB + custom BM25 + custom finance boost 與 Azure AI Search hybrid ranking 不會完全一樣。遷移後必須用 RAGAS 跑 A/B，而不是只看 app 能不能回答。

Mitigation：

```text
RAG_BACKEND=local python eval/ragas_eval.py
RAG_BACKEND=azure_search python eval/ragas_eval.py
```

比較：

- faithfulness
- answer_relevancy
- context_recall
- low-score question ids
- retrieved context metadata

### 8.2 Table chunk integrity must remain under your control

財報表格是本專案最重要的 finance-domain 差異化。即使使用 Azure，也不應讓 generic document pipeline 自動切表格。

Mitigation：

- `rag/chunker.py` 仍是唯一 chunking source of truth
- Azure AI Search 只存已處理好的 chunks
- table chunks 加 `chunk_type=financial_table`

### 8.3 Public demo can burn API quota

部署成 public URL 後，任何人都可能消耗：

- Azure OpenAI tokens
- Polygon quota
- Alpha Vantage quota
- Azure Search queries

Mitigation：

- demo 加 basic auth 或 invite-only
- 設定 query limit
- 記錄 user/session usage
- 對 MCP unavailable response 保持穩定

### 8.4 Live market data cannot answer historical filing facts

問 Apple FY2024 total net sales 時，應從 SEC filing answer，不應用 current market data API。

Mitigation：

- Router 保留 fiscal-year filing rules
- HYBRID prompt 明確分開 filing evidence 與 live market data
- MCP output citation 與 RAG citation 分開顯示

---

## 9. Minimal Code Change Checklist

第一輪最小改造建議：

```text
Dockerfile
.dockerignore
agent/llm_client.py
rag/search_backend.py
rag/azure_search_backend.py
storage/blob_store.py
deploy/azure-container-apps.md
```

現有檔案需小改：

```text
app.py
agent/router.py
agent/analyst.py
rag/ingest.py
rag/retriever.py
eval/ragas_eval.py
requirements.txt
README.md
docs/interview_notes.md
```

不建議大改：

```text
rag/chunker.py
tools/stock_server.py fallback semantics
eval unsupported/data-unavailable logic
```

這些目前已經承載重要 domain correctness，不應為了 cloud deploy 破壞。

---

## 10. Interview Narrative

你可以這樣講：

```text
I first built the project locally to validate the core finance-domain AI architecture:
structure-aware SEC filing chunking, hybrid retrieval, MCP market-data tools, query routing,
and RAGAS evaluation.

Then I designed an Azure deployment path. The Streamlit UI and MCP server are containerized
and deployed to Azure Container Apps. Raw SEC filings move from local data/pdfs to Blob Storage.
The local ChromaDB retrieval layer is replaced by Azure AI Search, while preserving hybrid
BM25 + vector retrieval and metadata filtering. Secrets move from .env to Key Vault, and
Application Insights tracks retrieval, tool-call, and LLM latency.

The key design decision is that Azure is the deployment and managed infrastructure layer,
but the finance-domain correctness remains in the application code: table-aware chunking,
metadata preservation, source citations, and market-data fallback handling.
```

中文理解版：

```text
我不是只是把 app 丟到 Azure 上，而是把本機 AI 系統拆成雲端服務。
Container Apps 跑 UI 和 MCP server，Blob Storage 存 SEC PDFs，Azure AI Search 做 hybrid retrieval，
Azure OpenAI 做 routing / synthesis，Key Vault 管 secrets，Application Insights 做 observability。
但財報表格切塊、metadata、citation、fallback chain 這些 finance-domain correctness 還是由我的程式控制。
```

---

## 11. Recommended Final Roadmap

建議接下來順序：

1. 完成 Streamlit end-to-end citation demo
2. 新增 Dockerfile，讓本機 container 能跑
3. 部署 Streamlit 到 Azure Container Apps
4. 把 MCP server 拆成第二個 container app
5. 新增 Azure OpenAI client abstraction
6. 把 PDF storage adapter 改成支援 Blob Storage
7. 新增 Azure AI Search backend
8. 跑 local Chroma vs Azure AI Search 的 RAGAS A/B
9. 把 Azure architecture 補進 README 和 interview notes

這條路線最平衡：既能維持目前 repo 的 AI 工程深度，也能增加 Azure deployment 經驗，符合 AI Engineer 職缺常見要求。

---

## 12. References

- Azure AI Search hybrid search: https://learn.microsoft.com/en-us/azure/search/hybrid-search-overview
- Azure AI Search RRF ranking: https://learn.microsoft.com/en-us/azure/search/hybrid-search-ranking
- Azure Container Apps: https://learn.microsoft.com/en-us/azure/container-apps/
- Azure Blob Storage: https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blobs-overview
- Azure OpenAI in Azure AI Foundry Models: https://learn.microsoft.com/en-us/azure/ai-foundry/openai/overview
- Azure Key Vault: https://learn.microsoft.com/en-us/azure/key-vault/
- Application Insights overview: https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview
