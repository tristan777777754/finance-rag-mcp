# MEMORY.md — Stock Research AI Assistant

這份文件是專案的工作記憶，不是 README。  
用途是讓使用者與 AI agent 下次回來時，可以快速理解目前做到哪裡、為什麼做了這些技術決策、還有哪些坑要注意。

---

## Current Project State

- 專案名稱：Stock Research AI Assistant
- 核心架構：RAG + MCP + Streamlit
- 目前主要目標：建立可展示的股票研究 AI 助理，能結合 SEC filing context 與 live market data 回答問題
- 目前最新工作重點：S5-03 Azure Container Apps public demo 已部署成功；下一步做 S5-04 secrets/config hardening 或 S6 MCP server split
- 目前 branch：`ragas-harness-fixes`
- 最新 Azure demo resource group：`rg-stock-research-demo`
- Azure Container Registry：`tristanragmcp2026.azurecr.io`
- Azure Container App：`stock-research-ui`
- Azure Container Apps Environment：`cae-stock-research-demo`

---

## Latest RAGAS Status

最新完整 evaluation artifact：

- Aggregate result：`eval/results/ragas_20260504T073612.json`
- Per-question details：
  - `eval/results/ragas_details_20260504T073612.json`
  - `eval/results/ragas_details_20260504T073612.csv`

目前分數：

```text
Faithfulness: 0.9297
Answer Relevancy: 0.8600
Context Recall: 0.6007
Evaluated: 47
Failed: 0
Supported scored: 33
Unsupported / data-unavailable: 14
Skipped multi-company: 3
```

目前 quality gate 判斷：

- `faithfulness > 0.80` 已達標
- `answer_relevancy > 0.75` 已達標
- `context_recall < 0.70` 尚未達標，但已診斷主要不是 generation 問題，而是 retrieval / eval-set mismatch / unsupported capability 混合問題
- 建議：不要繼續硬刷 accuracy，先進下一個 sprint，把 end-to-end demo 做完整

---

## Key Architecture Decisions

### 1. Hybrid Search Is Mandatory

本專案不使用純 vector search。  
原因是財務問題常需要精準命中術語、ticker、年份與 financial statement line item。

目前策略：

- BM25：處理 exact keyword，例如 `net income`, `gross margin`, `Item 1A`, `Greater China`
- Vector search：處理語意相似，例如「AI strategy」、「competitive moat」
- RRF：融合 BM25 與 vector ranking
- Finance domain boost：在最後排序階段給特定財報結構小幅加分

### 2. Financial Tables Must Be Whole-Table Chunks

財務表格不能像普通文字一樣用固定 token window 切。  
原因是表格被切斷後，年份、欄位名稱、line item 與數字會分離，LLM 可能無法判斷 `391,035` 對應哪一年或哪個科目。

目前 chunking 行為：

- extracted table 會變成獨立 whole-table chunk
- financial statement 頁面會把 extracted tables append 回 page chunk
- Item 8 / financial table 不用普通 sliding window 亂切
- section heading 會跨頁延續，避免表格頁 metadata 變空

這次 RAGAS 修復的重要 root cause：

- pdfplumber 原本有抽到 `page["tables"]`
- 但舊版 `chunk_filing()` 沒有把 tables 穩定存進 Chroma
- 導致 Apple FY2024 的關鍵數字不穩定出現在 retrieved contexts
- 修完後，AAPL id=1–5 能穩定抓到：
  - `Total net sales 391,035`
  - `Net income 93,736`
  - `iPhone 201,183`
  - `Services 96,169`
  - `Total gross margin percentage 46.2%`

### 3. Metadata Matters

每個 chunk 都應盡量保留：

- `ticker`
- `filing_type`
- `fiscal_year`
- `section`
- `section_type`
- `page_number`
- `table_index`，如果是 extracted table

這些 metadata 對 citation、debug retrieval、eval harness 都很重要。

### 4. MCP Tools Must Return Structured JSON

每個 MCP tool 回傳都必須包含：

- `ticker`
- `data_source`
- 足以回答問題的欄位
- 如果資料不可用，回傳 structured unavailable response，而不是讓 exception leak 出去

目前 market data 原則：

- 優先 Polygon.io
- 再用 Alpha Vantage
- yfinance 只作為 optional fallback，不應作為 evaluation 預設來源

原因：yfinance 容易 rate limit，會污染 RAGAS / MCP eval 結果。

### 5. Unsupported Capability Should Be Explicit

有些 HYBRID eval 題其實超出目前 MVP 能力，例如：

- 市場是否已經 pricing in future growth
- AWS / Google Cloud segment valuation comparison
- peer/segment valuation
- implied future growth
- buyback sustainability

這些題不是單靠 RAG + basic market data 就能穩定回答，需要額外產品能力：

- valuation model
- peer-company market data
- segment-level valuation logic
- forward-looking assumption framework

目前 eval harness 會把這類題標記為：

```text
unsupported_capability
```

資料 API 欄位不足時標記為：

```text
data_unavailable
```

這些題仍保留在 per-question details 中，但不納入 supported quality gate。

---

## Recent Fix Summary

### Latest Azure Deployment — 2026-05-24

本輪完成 `S5-02` 與 `S5-03`：

- 新增 `deploy/azure-container-apps.md`
  - 記錄 Azure CLI setup、Resource Group、ACR、Container Apps Environment、Container App 建立流程
  - 記錄 secrets / env vars 設定
  - 明確說明第一版仍使用 container-local ChromaDB，不是 Azure AI Search
  - 補上 ACR Tasks unavailable 時的 local Docker build + push fallback
  - 補上 Container App 從 private ACR pull image 需要 registry credentials

- Azure 基礎資源已建立
  - Resource Group：`rg-stock-research-demo`
  - ACR：`tristanragmcp2026`
  - ACR login server：`tristanragmcp2026.azurecr.io`
  - Container Apps Environment：`cae-stock-research-demo`
  - Container App：`stock-research-ui`

- Docker image 已 push 到 ACR
  ```text
  tristanragmcp2026.azurecr.io/stock-research-ai:s5-demo
  ```

- Public Azure demo 已驗證
  - Streamlit UI 可由 Azure Container Apps public URL 開啟
  - AAPL FY2024 filing 可完成 `Download & Ingest`
  - RAG_ONLY 問題驗證成功：
    ```text
    What was Apple's total net sales in fiscal year 2024?
    ```
    回答包含：
    ```text
    Apple's total net sales in fiscal year 2024 were $391,035 million [Doc 1].
    ```

- 實際部署時踩到的坑
  - `az acr build` 回：
    ```text
    TasksOperationsNotAllowed
    ```
    解法：改用 local Docker build，再 `docker push` 到 ACR。
  - 第一次建立 Container App 時出現：
    ```text
    UNAUTHORIZED: authentication required
    ```
    解法：建立 app 時加上 `--registry-server`、`--registry-username`、`--registry-password`。
  - Container App 預設 `0.5 CPU / 1Gi memory` 對 SEC ingest + sentence-transformers embedding 太小，按 `Download & Ingest` 可能中途重啟。
    解法：更新到至少：
    ```bash
    az containerapp update \
      --name stock-research-ui \
      --resource-group rg-stock-research-demo \
      --cpu 1.0 \
      --memory 2Gi
    ```

目前 Azure demo 的合理說法：

```text
I containerized the Streamlit RAG + MCP app, pushed the image to Azure Container Registry, deployed it to Azure Container Apps, configured secrets and environment variables, and verified a public demo URL with a real SEC filing query.
```

### Latest Dockerization / Demo Fixes — 2026-05-12

本輪完成 `S5-01 Dockerize Streamlit Demo` 的主要工作：

- 新增 `Dockerfile`
  - 使用 `python:3.12-slim`
  - 安裝 Streamlit / RAG / Chroma / FastMCP 所需 runtime packages
  - 啟動指令為 `streamlit run app.py`
  - 對外 expose `8501`

- 新增 `.dockerignore`
  - 排除 `.env`、`data/chroma/`、`graphify-out/`、cache、venv、logs
  - 避免 secrets 和大型 generated artifacts 被打進 image

- 更新 `requirements.txt`
  - 新增 `openai==1.59.7`
    - 原因：`agent/analyst.py` 使用 `from openai import OpenAI`，本機 conda 有但 Docker image 原本沒有
  - 新增 `torch==2.5.1`
    - 原因：避免 Docker build 解析到新版 `torch 2.11` 並下載大量 CUDA / Nvidia packages
  - pin `pydantic==2.10.6`、`pydantic-settings==2.8.1`
    - 原因：`fastmcp==2.3.4` 與較新的 `pydantic 2.13+ / pydantic-settings 2.14+` 不相容，會在 import 時噴：
      ```text
      TypeError: cannot specify both default and default_factory
      ```

- 修正 Docker / local CLI 問題
  - `/usr/local/bin/docker` 和 `docker-credential-osxkeychain` 原本指到不存在的 OrbStack path
  - 已改回 Docker Desktop：
    ```text
    /Applications/Docker.app/Contents/Resources/bin/docker
    /Applications/Docker.app/Contents/Resources/bin/docker-credential-osxkeychain
    ```

- 修正 `.env` 的 Polygon key 問題
  - `POLYGON_API_KEY` 原本在 `=` 後多一個空白：
    ```text
    POLYGON_API_KEY= nQP...
    ```
  - Docker `--env-file` 會保留這個空白，導致 Polygon 回：
    ```text
    401 Unknown API Key
    ```
  - 移除空白後 Polygon API 測試成功：
    ```text
    AAPL price: 292.68
    data_source: polygon
    market_cap: 4308095261920.0
    pe_ratio: 39.23
    ```

- 改善 HYBRID demo answer
  - `agent/analyst.py`
    - 如果 HYBRID 問題沒有明確年份，會把 sidebar selected fiscal year 放進 prompt
    - 明確要求多年度表格要對準欄位，例如 `2024, 2023, 2022` 中 FY2024 要取第一欄
    - 如果 live market data unavailable，仍要回答 SEC filing 可支撐的部分
    - 清理模型輸出中的 Markdown `*` / `_` 與黏字問題，避免 Streamlit 顯示怪斜體
    - 讓 large market cap 以 billion/trillion 表達，不要錯寫成 millions
  - `rag/retriever.py`
    - 對 revenue / net sales / total net sales 查詢，boost 含數字的 `Total net sales` table chunk
    - 避免「reported revenue」問句沒抓到 Apple 10-K 的正式欄位 `total net sales`

目前 Docker demo 驗證狀態：

```text
docker build -t stock-research-ai .  # pass
http://localhost:8501                # HTTP 200 OK
fastmcp import                       # pass
agent.analyst import                 # pass
Polygon MCP tool                     # pass, data_source=polygon
HYBRID revenue + valuation smoke     # pass
```

最後一次 HYBRID smoke test 期望回答形態：

```text
For FY2024, Apple's total net sales reported are $391,035 million [Doc 3].

Currently, Apple's market capitalization is approximately $4.31 trillion [Live Data].

This comparison shows the company's revenue relative to its market valuation.
```

Docker demo 建議啟動指令：

```bash
docker build -t stock-research-ai .

docker run --rm -d \
  --name stock-research-ai-demo \
  --env-file .env \
  -p 8501:8501 \
  -v /Users/tristan/finance_rag_mcp/data/chroma:/app/data/chroma \
  stock-research-ai
```

注意：目前建議把 `data/chroma` bind mount 進 container。否則用 `--rm` 起新 container 時，Chroma collection 可能不存在，需要重新 ingest。這是本地 Docker demo 的合理折衷；上 Azure 前要在 deployment notes 裡明確說明第一版仍使用 container-local / mounted local Chroma，不是 Azure AI Search。

最近一次 RAGAS 修復主要改了：

- `rag/chunker.py`
  - 保留 extracted tables
  - 新增 whole-table chunks
  - 加入 financial table detection
  - section heading 跨頁延續

- `rag/ingest.py`
  - embedding model 改成 lazy load
  - 修正 AAPL ingest fiscal year label

- `rag/retriever.py`
  - embedding model 改成 lazy load
  - 新增 finance-domain rerank boost
  - 對 risk factors、geographic segment、financial statement tables 做 query-aware boost
  - 降低 Table of Contents 類噪音 chunk

- `agent/analyst.py`
  - MCP tool routing 更細
  - 針對 earnings、filings、peers、fundamentals、price 選不同 tool
  - 回傳 routing trace 給 evaluation harness

- `tools/stock_server.py`
  - MCP tool schema 更完整
  - unavailable response 統一帶 `data_source`
  - Alpha Vantage parsing 更穩定
  - 新增 / 改善 earnings、SEC filings、fundamentals 欄位

- `eval/ragas_eval.py`
  - 輸出 per-question details
  - 儲存 retrieved context metadata 與 preview
  - 儲存 router decision
  - 儲存 MCP tool outputs
  - 支援 unsupported/data-unavailable 標記

---

## Known Issues

### 1. Context Recall Still Below 0.70

目前 context recall 約 `0.6007`。  
已知原因：

- 部分 expected answer 與目前 PDF 版本或數字不完全一致
- RAGAS 有時對正確 answer/context 仍給低 recall
- 部分題目需要更細的 parent-child retrieval 或 section-specific query rewriting
- NVDA / AAPL 部分 segment 題仍可改善 table ranking

建議不要現在繼續硬刷，先開 follow-up ticket。

### 2. Multi-Company HYBRID Not Implemented

目前 eval harness 會 skip multi-company samples。  
未來若要支援，需補：

- multi-ticker RAG retrieval
- multi-ticker MCP calls
- comparison synthesis prompt
- table-style output

相關 sprint story：

- `S3-05`: multi-company comparison query

### 3. Current Market Data Fields Are Incomplete

Polygon / Alpha Vantage 有些欄位可能缺：

- 52-week high / low
- EV/EBITDA
- P/B
- ROE
- dividend history

目前工具會回 structured unavailable，不會讓 pipeline crash。  
未來若要提高 MCP_ONLY accuracy，需要擴充資料源或補更可靠的 fundamentals provider。

### 4. GitHub CLI Auth Is Invalid

目前 `gh auth status` 顯示 token invalid。  
所以目前只能用 `git push`，不能自動開 PR。

需要使用者執行：

```bash
gh auth login -h github.com
```

---

## Recommended Next Sprint Direction

建議現在不要繼續硬刷 RAGAS accuracy。  
Streamlit RAG / MCP / HYBRID demo 已可展示，Dockerized local demo 與第一版 Azure Container Apps public demo 都已完成。下一步應做 Azure deployment hardening，而不是立刻重寫 RAG。

下一步優先順序：

1. S5-04 Azure deployment hardening
   - 確認 Container App secrets/env vars 都在 Azure Portal 可見且沒有 key 進 repo
   - 記錄目前 Container App CPU / memory 設定
   - 補 README 的 Azure deployment status
   - 視需要加 Azure Files 或明確標註 container restart 後需重新 ingest

2. S6 Split / deploy MCP server separately
   - 在 UI container 穩定後，再把 MCP finance server 拆成第二個 container app
   - UI 透過 env var 指向 MCP endpoint
   - 所有 MCP response 仍需包含 `data_source`

3. Follow-up accuracy ticket
   - target：context recall > 0.70
   - 方法：
     - parent-child retrieval
     - section-specific query rewriting
     - table metadata refinement
     - adaptive top_k
     - eval set expected-answer cleanup

---

## Interview Talking Points

### Why table-aware chunking?

Fixed-size chunking 會切斷 financial tables，讓年份、line items 和數字分離。  
在財務 RAG 裡，這會直接造成 numeric answer 錯誤或 retrieval recall 下降。

### Why hybrid search?

Vector search 擅長語意，但財報查詢常需要 exact match。  
BM25 對 `Item 1A`, `gross margin`, `net income`, `Greater China` 這類查詢更可靠。  
RRF 可以融合兩者。

### Why MCP instead of direct API calls inside prompt?

MCP 把 market data access 做成 structured tools，讓資料來源、schema、fallback、error handling 更可控。  
這比把 API response 隨便塞進 prompt 更接近 production tool architecture。

### Why mark unsupported questions?

不是所有 eval 題都應該用 prompt 硬答。  
如果題目需要尚未實作的 product capability，例如 valuation model 或 peer valuation，應該明確標記 unsupported，而不是讓模型猜。

---

## Useful Commands

Run Dockerized Streamlit demo:

```bash
docker build -t stock-research-ai .

docker stop stock-research-ai-demo 2>/dev/null || true

docker run --rm -d \
  --name stock-research-ai-demo \
  --env-file .env \
  -p 8501:8501 \
  -v /Users/tristan/finance_rag_mcp/data/chroma:/app/data/chroma \
  stock-research-ai
```

Check Docker demo health:

```bash
curl -I http://localhost:8501
docker logs --tail 80 stock-research-ai-demo
docker exec stock-research-ai-demo python -c "from rag.chroma_client import get_chroma_client; print(get_chroma_client().get_collection('sec_filings').count())"
```

Smoke test MCP tools in Docker:

```bash
docker exec stock-research-ai-demo python -c "from tools.stock_server import get_stock_price, get_fundamentals; print(get_stock_price('AAPL')); print(get_fundamentals('AAPL'))"
```

Smoke test HYBRID answer in Docker:

```bash
docker exec stock-research-ai-demo python -c "from agent.analyst import run; result=run(\"Compare Apple's reported revenue with its current valuation.\", ticker='AAPL', fiscal_year='2024'); print(result['answer'])"
```

Run full evaluation:

```bash
/Users/tristan/machine-learning-for-trading/.conda_envs/finance_rag/bin/python eval/ragas_eval.py
```

Compile core files:

```bash
python -m py_compile agent/analyst.py eval/ragas_eval.py rag/chunker.py rag/ingest.py rag/retriever.py tools/stock_server.py
```

Check latest result:

```bash
sed -n '1,120p' eval/results/ragas_20260504T073612.json
```

Check current branch:

```bash
git status -sb
```

---

## Next Agent Instructions

下次接手時：

1. 先讀 `stock_research_pm_report.docx`
2. 再讀 `AGENTS.md`
3. 再讀本檔 `MEMORY.md`
4. 若任務是 accuracy/eval，先看最新 `eval/results/ragas_details_*.json`
5. 若任務是產品開發，下一步優先做 `S5-02 deploy/azure-container-apps.md`
6. 目前 `S5-02` / `S5-03` 已完成；不要直接跳 Azure AI Search / Blob Storage，下一步先做 Azure hardening 或 MCP split
7. 如果 Docker demo 又出現 market data unavailable，先檢查 `.env`：
   - `POLYGON_API_KEY` 不可有前後空白
   - Docker `--env-file` 會保留 `=` 後面的空白
   - 用 `docker exec` 測 `get_stock_price('AAPL')` 是否回 `data_source='polygon'`
8. 如果 Azure UI ingest 卡住或 container restart，先檢查 Container App resources，至少用 `1 CPU / 2Gi memory`
