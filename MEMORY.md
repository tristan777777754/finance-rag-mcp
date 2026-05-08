# MEMORY.md — Stock Research AI Assistant

這份文件是專案的工作記憶，不是 README。  
用途是讓使用者與 AI agent 下次回來時，可以快速理解目前做到哪裡、為什麼做了這些技術決策、還有哪些坑要注意。

---

## Current Project State

- 專案名稱：Stock Research AI Assistant
- 核心架構：RAG + MCP + Streamlit
- 目前主要目標：建立可展示的股票研究 AI 助理，能結合 SEC filing context 與 live market data 回答問題
- 目前 branch：`ragas-harness-fixes`
- 最新 pushed commit：`61fa12e Improve RAGAS harness and financial table retrieval`
- GitHub branch 已 push：`origin/ragas-harness-fixes`
- PR 可從這裡建立：
  - https://github.com/tristan777777754/finance-rag-mcp/pull/new/ragas-harness-fixes

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
目前應該進下一個 sprint，把產品 demo 做完整。

下一步優先順序：

1. Streamlit end-to-end query flow
   - user query
   - router
   - RAG / MCP / HYBRID execution
   - synthesized answer
   - citation panel

2. Citation rendering
   - RAG citation：section + page number
   - MCP citation：data_source + ticker + timestamp if available

3. HYBRID response quality
   - 清楚分開 filing evidence 與 live market data
   - 避免超出 context 的 valuation speculation

4. Follow-up accuracy ticket
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
5. 若任務是產品開發，優先從 Streamlit end-to-end citation flow 開始
