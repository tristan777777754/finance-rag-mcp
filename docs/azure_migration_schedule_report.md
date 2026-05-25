# Stock Research AI Assistant — Azure Migration Schedule Report

## 1. Executive Summary

這份 report 的目的，是把目前本機版 Stock Research AI Assistant 遷移到 Azure 的工作拆成可執行 sprint 排程。

目前專案已完成 finance-domain AI assistant 的核心能力：

- RAG：SEC filing chunking、Hybrid Search、citation-aware retrieval
- MCP：market data tools、fallback chain、structured JSON output
- Agent：RAG_ONLY / MCP_ONLY / HYBRID query routing
- Evaluation：RAGAS aggregate + per-question details
- UI：Streamlit demo flow

Azure 化的策略不是一次把整個系統重寫，而是採用分階段遷移：

```text
Local Streamlit + ChromaDB + local PDFs + .env
        |
        v
Dockerized app
        |
        v
Azure Container Apps
        |
        v
Azure OpenAI + Blob Storage + Azure AI Search + Key Vault + Monitor
```

第一個目標應該是取得一個可展示的 Azure public demo URL。之後才逐步把 retrieval backend、PDF storage、secrets、observability 換成 Azure managed services。

---

## 2. Current Project Baseline

### 2.1 Product Baseline

目前產品定位是股票研究 AI 助理，使用者可以：

- 查詢 SEC filing 裡的 historical financial facts
- 查詢 live market data
- 問需要 filing evidence + market data 的 HYBRID 問題
- 查看 filing citation 與 MCP `data_source`

### 2.2 Quality Baseline

最新 RAGAS 狀態：

```text
Faithfulness:      0.9297
Answer Relevancy:  0.8600
Context Recall:    0.6007
Evaluated:         47
Failed:            0
```

判斷：

- `faithfulness` 已達 MVP target。
- `answer_relevancy` 已達 MVP target。
- `context_recall` 尚未達 0.70，但目前已知原因包含 retrieval gaps、eval mismatch、unsupported valuation capability，不應在 Azure 遷移前大改 generation prompt。

### 2.3 Important Constraints

Azure 遷移過程必須保留以下 finance-domain constraints：

- Financial tables must remain whole-table chunks.
- Retrieval must remain hybrid, not vector-only.
- Historical filing questions must use SEC filing context, not live market APIs.
- MCP tool output must always include `data_source`.
- Chunk metadata must preserve `ticker`, `company`, `filing_type`, `fiscal_year`, `section`, `page_number`.
- `yfinance` must remain optional last-resort fallback, not primary evaluation source.

---

## 3. Target Azure Architecture

目標 Azure 架構：

```text
User Browser
    |
    v
Azure Container Apps
    - Streamlit UI
    - Agent Orchestrator
    |
    +--> Azure OpenAI
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
    |       - separate Container App
    |       - Polygon.io -> Alpha Vantage -> optional yfinance
    |
    +--> Azure Blob Storage
    |       - raw SEC PDFs
    |       - optional eval artifacts
    |
    +--> Azure Key Vault / Container Apps Secrets
    |       - API keys
    |       - service secrets
    |
    +--> Application Insights / Azure Monitor
            - latency
            - errors
            - retrieval diagnostics
            - tool-call diagnostics
```

---

## 4. Migration Principles

### 4.1 Do First

先做：

1. Dockerize current Streamlit demo.
2. Deploy Streamlit to Azure Container Apps.
3. Split MCP server into separate Container App.
4. Add Azure OpenAI provider abstraction.
5. Move raw PDFs to Blob Storage.
6. Add Azure AI Search backend adapter.
7. Run RAGAS A/B test between local and Azure retrieval.

### 4.2 Do Not Do First

第一輪不要做：

- AKS
- complex VNet / Private Link
- full CI/CD pipeline
- multi-user auth
- advanced valuation engine
- automated SEC EDGAR polling
- full rewrite of `rag/chunker.py`

理由：這些會分散主線。現在最有面試價值的路線，是先把 finance-domain RAG + MCP MVP 變成可部署、可展示、可解釋的 Azure demo。

---

## 5. Sprint Schedule

## S5 — Azure Deployment Foundation

### Goal

讓目前本機 Streamlit app 可以用 Docker 跑起來，並部署到 Azure Container Apps。

### Work Packets

#### S5-01 Dockerize Streamlit Demo

Owned files:

```text
Dockerfile
.dockerignore
requirements.txt
```

Acceptance criteria:

```bash
docker build -t stock-research-ai .
docker run --env-file .env -p 8501:8501 stock-research-ai
```

Expected result:

- `http://localhost:8501` 可以開啟。
- AAPL FY2024 net sales 問題可以回答 `$391,035 million`。
- MCP current price 題有 `data_source`。
- HYBRID 題同時顯示 filing citation 與 live market data。

Risks:

- Container 內 embedding model 下載時間過長。
- ChromaDB local path 在 container 內路徑不同。
- `.env` 未正確傳入導致 API calls unavailable。

#### S5-02 Azure Container Apps Deployment Notes

Owned files:

```text
deploy/azure-container-apps.md
README.md
```

Acceptance criteria:

- 文件包含 image build、push、Container Apps 建立、env vars / secrets 設定。
- 文件清楚說明第一版仍使用 local ChromaDB / bundled demo data。
- 文件列出必要環境變數。

#### S5-03 Deploy Streamlit UI to Azure

Owned files:

```text
deploy/azure-container-apps.md
app.py
```

Acceptance criteria:

- Azure public URL 可以開啟 Streamlit UI。
- RAG_ONLY demo query 可以回答並顯示 citation。
- App logs 中可以看到 query type 與基本錯誤訊息。

#### S5-04 Secrets via Azure Configuration

Owned files:

```text
deploy/azure-container-apps.md
README.md
```

Acceptance criteria:

- API keys 不存在 image 或 repo。
- Container Apps 使用 secrets / environment variables。
- local dev 仍可使用 `.env`。

### S5 Done Criteria

```text
Streamlit app can run locally in Docker and load from an Azure Container Apps public URL.
```

---

## S6 — MCP Split and Azure OpenAI Provider

### Goal

把 MCP market-data server 拆成獨立 Azure service，並讓 LLM provider 可以切換到 Azure OpenAI。

### Work Packets

#### S6-01 Deploy MCP Server Separately

Owned files:

```text
tools/stock_server.py
deploy/azure-container-apps.md
```

Acceptance criteria:

- MCP finance server 可以獨立部署成 Azure Container App。
- UI / Agent 可以透過 env var 指向 MCP endpoint。
- MCP responses 保留 `data_source`。

Risks:

- MCP protocol / HTTP exposure 方式需要額外 adapter。
- Free-tier API latency 可能造成 timeout。

#### S6-02 Add LLM Client Abstraction

Owned files:

```text
agent/llm_client.py
agent/router.py
agent/analyst.py
```

Acceptance criteria:

```text
LLM_PROVIDER=openai
LLM_PROVIDER=azure_openai
```

兩種設定都可以跑 router / analyst。

Design:

- `agent/router.py` 不直接依賴特定 SDK。
- `agent/analyst.py` 不直接讀 Azure-specific env vars。
- Azure OpenAI endpoint / deployment name 由 env vars 控制。

#### S6-03 Azure Smoke Test

Owned files:

```text
tests/
docs/azure_deployment_report.md
```

Acceptance criteria:

在 Azure public URL 測試：

```text
RAG_ONLY:
What was Apple's total net sales in fiscal year 2024?

MCP_ONLY:
What is Apple's current stock price?

HYBRID:
Compare Apple's reported revenue with its current valuation.
```

Expected result:

- RAG_ONLY 有 filing citation。
- MCP_ONLY 有 `data_source`。
- HYBRID 同時有 filing source 與 market data source。

### S6 Done Criteria

```text
UI and MCP are deployed as separate services, and LLM calls can use Azure OpenAI through provider configuration.
```

---

## S7 — Blob Storage and Azure AI Search Backend

### Goal

把 PDF storage 與 retrieval backend 雲端化，同時保留 local backend 作為 dev fallback。

### Work Packets

#### S7-01 Add Blob Storage Adapter

Owned files:

```text
storage/blob_store.py
rag/ingest.py
requirements.txt
```

Acceptance criteria:

- Raw SEC PDFs 可以上傳到 Blob Storage。
- Ingestion 可以從 Blob path 讀取 PDF。
- Blob path 使用一致命名：

```text
sec-filings/{ticker}/{fiscal_year}/{filing_type}/{document_name}.pdf
```

Required metadata:

```text
ticker
company
fiscal_year
filing_type
filing_date
source_url
ingested_at_utc
```

Finance-domain warning:

同一家公司同一年若有 amended filing，未來需要 accession number 或 document version，避免誤用舊版 filing。

#### S7-02 Add Search Backend Interface

Owned files:

```text
rag/search_backend.py
rag/retriever.py
eval/ragas_eval.py
```

Acceptance criteria:

```bash
RAG_BACKEND=local python eval/ragas_eval.py
```

仍可使用目前 local ChromaDB + BM25 retriever。

Design:

- local backend preserves current behavior.
- Azure backend can be added without rewriting analyst layer.
- Evaluation harness can switch backend by env var.

#### S7-03 Add Azure AI Search Backend

Owned files:

```text
rag/azure_search_backend.py
rag/ingest.py
requirements.txt
```

Acceptance criteria:

- Azure AI Search index contains chunk content and required metadata.
- Azure AI Search supports text + vector query.
- Query supports metadata filters for `ticker`, `fiscal_year`, `filing_type`.

Suggested index schema:

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

#### S7-04 Azure Hybrid Retrieval Validation

Owned files:

```text
eval/ragas_eval.py
docs/azure_deployment_report.md
```

Acceptance criteria:

```bash
RAG_BACKEND=local python eval/ragas_eval.py
RAG_BACKEND=azure_search python eval/ragas_eval.py
```

Compare:

- faithfulness
- answer_relevancy
- context_recall
- low-score question ids
- retrieved context metadata

### S7 Done Criteria

```text
Raw PDFs can live in Blob Storage, chunks can be indexed in Azure AI Search, and evaluation can compare local vs Azure retrieval.
```

---

## S8 — Production-Style Demo and Documentation

### Goal

讓 Azure demo 更接近 production-style portfolio project，並補齊面試敘事。

### Work Packets

#### S8-01 Add Observability

Owned files:

```text
agent/analyst.py
rag/retriever.py
tools/stock_server.py
```

Acceptance criteria:

Logs include:

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

#### S8-02 Add Public Demo Protection

Owned files:

```text
app.py
deploy/azure-container-apps.md
```

Acceptance criteria:

- Public demo has basic auth or simple access gate.
- API quota usage is less likely to be burned by anonymous traffic.
- Failure mode remains user-friendly.

#### S8-03 Update README and Interview Notes

Owned files:

```text
README.md
docs/interview_notes.md
docs/azure_deployment_report.md
```

Acceptance criteria:

- README includes Azure architecture summary.
- Interview notes include Azure deployment narrative.
- Documentation explains why Azure AI Search preserves hybrid retrieval.
- Documentation explains why chunking remains application-controlled.

### S8 Done Criteria

```text
Azure demo is usable, protected, observable, and documented well enough for interview discussion.
```

---

## 6. Recommended Timeline

### Week 1

Focus:

- Dockerfile
- `.dockerignore`
- local Docker smoke test
- first Azure Container Apps deployment

Outcome:

```text
The app can run from an Azure public URL.
```

### Week 2

Focus:

- Split MCP service
- Add Azure OpenAI abstraction
- Azure RAG_ONLY / MCP_ONLY / HYBRID smoke tests

Outcome:

```text
The app has clearer cloud service boundaries.
```

### Week 3

Focus:

- Blob Storage adapter
- Search backend interface
- Azure AI Search indexing

Outcome:

```text
The data layer starts moving from local filesystem/Chroma to Azure services.
```

### Week 4

Focus:

- RAGAS A/B testing
- observability
- public demo access control
- README / interview documentation

Outcome:

```text
The Azure version is demonstrable, measurable, and explainable.
```

---

## 7. Validation Gates

### Local Container Gate

```bash
docker build -t stock-research-ai .
docker run --env-file .env -p 8501:8501 stock-research-ai
```

Required:

- Streamlit app loads.
- RAG_ONLY query returns filing citation.
- MCP_ONLY query returns `data_source`.
- HYBRID query uses both retrieval and tool output.

### Azure App Gate

Required:

- Public URL loads.
- Required secrets are configured outside image.
- Logs show startup success.
- At least three demo queries work.

### Retrieval Migration Gate

```bash
RAG_BACKEND=local python eval/ragas_eval.py
RAG_BACKEND=azure_search python eval/ragas_eval.py
```

Required:

- Azure backend does not silently degrade citation metadata.
- Azure backend preserves hybrid retrieval behavior.
- Low-score deltas are reviewed per question, not only aggregate.

### Production Demo Gate

Required:

- Public demo has basic access control.
- API failures return structured unavailable responses.
- Observability shows whether failures are retrieval, MCP, LLM, or API related.

---

## 8. Main Risks

### 8.1 Azure AI Search Ranking Drift

Risk:

Azure AI Search hybrid ranking will not match local ChromaDB + BM25 + custom boost exactly.

Mitigation:

- Keep `RAG_BACKEND=local` during migration.
- Run RAGAS A/B before claiming migration success.
- Compare per-question retrieved contexts.

### 8.2 Financial Table Integrity

Risk:

Generic cloud document processing may split financial tables and damage numeric QA accuracy.

Mitigation:

- Keep `rag/chunker.py` as source of truth.
- Upload already-processed chunks to Azure AI Search.
- Use `chunk_type=financial_table` for table chunks.

### 8.3 Public API Quota Burn

Risk:

Public demo URL can consume Azure OpenAI, Polygon, Alpha Vantage, and Search quota.

Mitigation:

- Add basic auth or access gate.
- Log usage by query/session.
- Keep yfinance disabled by default.
- Return structured unavailable responses when providers fail.

### 8.4 Historical vs Live Data Confusion

Risk:

Historical filing facts may accidentally be answered from live market APIs.

Mitigation:

- Preserve router rules for fiscal-year filing questions.
- Keep RAG citation and MCP `data_source` visually separate.
- Evaluation should inspect router decision and tool outputs.

---

## 9. Recommended Next Action

The next concrete story should be:

```text
S5-01 Dockerize Streamlit Demo
```

Why:

- It is required before Azure Container Apps deployment.
- It has a small, measurable scope.
- It does not risk breaking retrieval quality.
- It creates immediate portfolio value by showing deployment readiness.

Suggested first implementation files:

```text
Dockerfile
.dockerignore
deploy/azure-container-apps.md
```

Suggested first validation:

```bash
docker build -t stock-research-ai .
docker run --env-file .env -p 8501:8501 stock-research-ai
```

---

## 10. Interview Narrative

English version:

```text
I first validated the finance-domain AI architecture locally: SEC filing ingestion,
structure-aware chunking, hybrid retrieval, MCP market-data tools, query routing,
and RAGAS evaluation.

Then I migrated the system to Azure in phases. I containerized the Streamlit UI and
deployed it to Azure Container Apps, split the MCP finance server into a separate
service, added Azure OpenAI configuration, moved PDFs to Blob Storage, and replaced
the local Chroma retrieval backend with Azure AI Search while preserving hybrid
text + vector retrieval and metadata filtering.

The important design choice is that Azure provides managed infrastructure, but
finance-domain correctness remains controlled by application logic: whole-table
chunking, metadata preservation, source citations, and market-data fallback handling.
```

中文版本：

```text
我不是只是把本機 app 丟上 Azure，而是把 AI 系統拆成可部署的雲端服務。
Container Apps 跑 Streamlit UI 和 MCP server，Blob Storage 存 SEC PDFs，
Azure AI Search 做 hybrid retrieval，Azure OpenAI 做 routing / synthesis，
Key Vault 管 secrets，Application Insights 追蹤 retrieval、tool call 和 LLM latency。

但 finance-domain correctness 不交給雲端黑箱處理。財報表格切塊、metadata、
citation、market data fallback chain 還是由 application code 控制。
```
