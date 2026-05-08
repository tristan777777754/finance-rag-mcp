# Stock Research AI Assistant — Interview Notes

這份文件對應 Sprint 4 的 `S4-04`：面試準備筆記。重點不是背誦技術名詞，而是能清楚說明每個設計選擇在 finance-domain RAG 裡解決了什麼問題、帶來什麼 trade-off，以及目前 MVP 還有哪些限制。

---

## 1. One-Minute Project Pitch

這是一個股票研究 AI 助理，使用 RAG + MCP 架構，把 SEC filing 裡的歷史公司資訊和即時市場資料結合起來。

使用者可以問兩類問題：

- 財報問題：例如「Apple FY2024 的 revenue / net income / gross margin 是多少？」這類問題由 RAG 從 SEC 10-K / 10-Q 裡找證據。
- 即時市場問題：例如「Apple 現在的股價和 P/E 是多少？」這類問題由 MCP tools 呼叫 Polygon / Alpha Vantage 等市場資料 API。
- 混合問題：例如「比較 Nvidia 的 Data Center growth 和目前 valuation」，這類問題需要同時使用 filing context 與 live market data。

核心設計原則是：歷史財報數字要 grounded in SEC filing，即時市場數據要 structured tool output，而且答案必須能追溯來源。

---

## 2. Architecture Overview

整體 query flow：

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
BM25 + Vector + RRF         Polygon -> Alpha Vantage -> optional yfinance
   |                              |
   +--------------+---------------+
                  |
                  v
          Analyst Orchestrator
                  |
                  v
      Grounded answer with citations
```

面試時可以強調：

- Router 先把問題分成 `RAG_ONLY`、`MCP_ONLY`、`HYBRID`，避免每題都做所有工作。
- RAG 負責 SEC filing 裡的 historical / primary-source evidence。
- MCP 負責 live / current market data。
- Analyst layer 負責把 retrieved contexts 和 tool outputs 合成答案，但 prompt 要求只使用提供的 context。

---

## 3. Why Structure-Aware Chunking?

### 面試官可能問

為什麼不用固定 token size chunking？

### 建議回答

固定大小切塊在一般文字 RAG 裡可以接受，但在財務文件裡很危險，因為 10-K / 10-Q 有大量 financial tables。若固定 512 tokens 切，可能會把表格中的年份、line item 和數字切散。

例如一張 income statement 可能有：

```text
2025 2024 2023
Total net sales 416,161 391,035 383,285
Net income      112,010  93,736  96,995
```

如果 chunk boundary 剛好切在表格中間，模型可能看到 `391,035`，但看不到它對應的是 `2024 Total net sales`，這會直接造成 numeric answer 錯誤。

所以本專案採用：

- narrative sections：sliding window，512 tokens，80-token overlap。
- financial table pages：whole-page / whole-table chunk，不切表格。
- extracted tables：另存為獨立 table chunks。
- metadata：每個 chunk 保留 `ticker`、`filing_type`、`fiscal_year`、`section`、`section_type`、`page_number`。

### Trade-off

好處：

- 財務表格的 row / column relation 比較不會壞掉。
- RAG 對 revenue、net income、gross margin、segment revenue 這類 numeric questions 更穩。
- citation 可以顯示 page number 和 section。

代價：

- whole-table chunk 可能比一般 chunk 長，會增加 retrieval context 長度。
- PDF table extraction 不一定完美，仍需針對 SEC filing layout 做額外處理。
- 若 table 很大，未來可能要做 parent-child retrieval 或 table-aware parsing。

### 對應程式

- `rag/chunker.py`
- `chunk_filing()`
- `_has_financial_table()`
- `_format_table_chunk()`
- `_format_page_with_tables()`

---

## 4. Why Hybrid Search Instead of Pure Vector Search?

### 面試官可能問

為什麼不用 ChromaDB vector search 就好？

### 建議回答

財務查詢常同時需要 semantic matching 和 exact matching。Pure vector search 對語意問題很強，例如「management 對 AI strategy 怎麼說？」但對 exact finance terms 可能不穩，例如：

- `Item 1A`
- `gross margin`
- `net income`
- `Greater China`
- `Data Center`
- `Form 10-K`
- ticker / fiscal year / segment names

BM25 對這種 exact keywords 很有幫助。Vector search 可以找語意相近內容，BM25 可以精準命中財務術語，再用 Reciprocal Rank Fusion 合併排序。

本專案 retrieval flow：

```text
query
  |
  +-- BM25 keyword search
  |
  +-- dense vector search via BAAI/bge-small-en-v1.5
  |
  v
Reciprocal Rank Fusion
  |
  v
finance-domain rerank boost
  |
  v
top-k contexts
```

### Trade-off

好處：

- 對 exact financial terms 更穩。
- 對 semantic questions 仍保留向量檢索能力。
- RRF 比手動調權重更簡單，對不同 query types 較穩定。

代價：

- 需要同時維護 BM25 index 和 vector DB。
- 多一層 fusion / reranking 邏輯。
- 若 metadata filter 或 BM25 corpus 建錯，會造成 retrieval mismatch。

### Finance-domain why

在財報問答裡，答錯一個數字比答得稍微慢更嚴重。Hybrid search 的價值在於提高 exact line item retrieval 的穩定性，而不是只追求語意相似。

### 對應程式

- `rag/retriever.py`
- `build_bm25_index()`
- `vector_search()`
- `bm25_search()`
- `reciprocal_rank_fusion()`
- `_finance_boost()`
- `hybrid_search()`

---

## 5. Why MCP Instead of Hardcoded API Calls?

### 面試官可能問

為什麼需要 MCP？直接在 Python 裡 call Polygon API 不就好了？

### 建議回答

如果只是 demo 一個 API endpoint，hardcoded API call 可以。但這個 project 想展示的是 production-style AI tool architecture：LLM / agent 能根據問題類型選擇工具，而且工具回傳 schema 是穩定、可觀測、可 fallback 的。

MCP tools 把 market data access 包成明確的工具邊界：

- `get_stock_price`
- `get_fundamentals`
- `get_peers`
- `get_earnings_calendar`
- `get_sec_filings_list`
- `get_financials`

每個工具都回傳 structured JSON，而且必須包含 `data_source`。這讓 answer layer 可以清楚知道資料來自 `polygon`、`alpha_vantage`、`sec_edgar`、`yfinance` 或 `unavailable`。

### 為什麼要 fallback chain？

市場資料 API 很容易遇到：

- rate limit
- missing fields
- endpoint coverage 不完整
- free-tier latency / quota 問題

所以本專案的原則是：

```text
Polygon.io -> Alpha Vantage -> optional yfinance -> structured unavailable
```

特別注意：`yfinance` 不適合作為 evaluation 的主要資料源，因為它容易 rate limit，且資料 schema 不如正式 API 穩定。現在 repo 裡把 yfinance 設為 optional fallback，預設關閉。

### Trade-off

好處：

- market data schema 更可控。
- tool output 可記錄到 evaluation details。
- data source 可追溯。
- API failure 不會讓整個 agent crash，而是回 structured unavailable。

代價：

- 多一層 tool routing 和 schema design。
- 每個資料源的欄位不一致，需要 normalization。
- 如果 API free tier 缺欄位，答案能力會受限。

### 對應程式

- `tools/stock_server.py`
- `_unavailable()`
- `get_stock_price()`
- `get_fundamentals()`
- `get_earnings_calendar()`
- `get_sec_filings_list()`
- `agent/analyst.py`
- `_run_mcp()`

---

## 6. Query Router Design

### 面試官可能問

你怎麼決定一題該走 RAG、MCP 還是 HYBRID？

### 建議回答

我先用 query router 分類，因為 filing data 和 market data 是不同資料域：

- `RAG_ONLY`：需要 SEC filing 的歷史資訊，例如 revenue、risk factors、MD&A、segment performance。
- `MCP_ONLY`：只需要即時市場資料，例如 current stock price、current P/E、next earnings date。
- `HYBRID`：同時需要 filing evidence 和 live market data，例如「reported revenue vs current valuation」。

Router prompt 使用 few-shot examples，並明確規則化「specific fiscal year financials 應該走 RAG」。這點很重要，因為 historical revenue 不應該用 live market API 猜，應該從 SEC filing 裡回答。

### 對應程式

- `agent/router.py`
- `classify_query()`
- `agent/analyst.py`
- `run()`

---

## 7. Evaluation Methodology

### 面試官可能問

你怎麼知道這個 RAG system 真的有變好？

### 建議回答

我用 RAGAS 建 evaluation harness，並且不只看 aggregate score，而是輸出 per-question details。原因是財務 RAG 的錯誤通常不是單一類型，有可能是 retrieval、chunking、router、MCP tool、API data、generation prompt 或 eval set 本身的問題。

目前 evaluation 會記錄：

- question id
- query type
- ticker / fiscal year
- expected answer
- generated answer
- faithfulness
- answer relevancy
- context recall
- retrieved contexts preview
- retrieved context metadata
- router decision
- MCP tool outputs
- unsupported / data-unavailable reason

核心 metrics：

- `faithfulness`：答案是否被 context 支撐。
- `answer_relevancy`：答案是否回答了問題。
- `context_recall`：retrieved contexts 是否包含 expected answer 所需資訊。

目前最新結果：

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

### 如何解讀分數？

`faithfulness` 和 `answer_relevancy` 已達 MVP target，代表模型大多有用提供的 context 回答，也有回答到問題。

`context_recall` 仍低於 0.70，這不應該單純靠 prompt 硬修。已知原因包括：

- 部分 expected answer 和目前 PDF / filing year 不完全一致。
- 部分題目需要 parent-child retrieval 或 section-specific query rewriting。
- 部分 HYBRID 題其實需要尚未實作的 valuation model。
- RAGAS 對 financial numeric context 有時會低估 recall。

所以我把 unsupported capability 和 data unavailable 題保留在 details 裡，但不納入 supported quality gate。這比刪題刷分更接近真實產品評估。

### 對應程式

- `eval/ragas_eval.py`
- `_run_pipeline()`
- `_unsupported_reason()`
- `_print_low_score_examples()`
- `eval/results/ragas_*.json`
- `eval/results/ragas_details_*.json`
- `eval/results/ragas_details_*.csv`

---

## 8. Current Limitations and Honest Follow-Ups

### Multi-company HYBRID

目前 multi-company comparison 還不是完整產品能力。要做好需要：

- multi-ticker RAG retrieval
- multi-ticker MCP calls
- comparison table synthesis
- per-company citation mapping

這對應 PM spec 裡的 `S3-05`，目前 eval harness 會 skip multi-company samples。

### Context Recall

context recall 低於 0.70，下一步應該改善 retrieval，而不是只調 prompt。建議 follow-up：

- parent-child retrieval
- section-specific query rewriting
- adaptive top_k
- table metadata refinement
- eval expected-answer cleanup

### Market Data Coverage

Polygon / Alpha Vantage free tier 有些欄位可能缺：

- P/B
- EV/EBITDA
- ROE
- dividend history
- 52-week high / low

目前工具會回 `data_source: "unavailable"`，避免模型用猜的。

---

## 9. Interview Q&A Cheat Sheet

### Q1. Why not just put the full 10-K into the prompt?

10-K 通常有 150 到 250 頁，把整份丟進 prompt 成本高、延遲高，而且會稀釋注意力。RAG 只取 top-k relevant chunks，可以降低成本並提升答案 groundedness。

### Q2. Why not use only vector search?

Finance questions 很常需要 exact terms，例如 `Item 1A`、`gross margin`、`Data Center`。Vector search 對語意相似強，但 exact line item 不一定穩。BM25 + vector + RRF 可以兼顧語意與關鍵字精準度。

### Q3. Why preserve financial tables as whole chunks?

因為表格的 meaning 來自 row / column relationship。若切斷，數字可能失去年份和科目，造成財務答案錯誤。財務 RAG 裡 numeric correctness 比一般摘要任務更敏感。

### Q4. Why MCP?

MCP 把 market data access 變成 structured tools，能清楚定義 schema、fallback、timeout、data_source 和 error handling。這比把 API response 隨便塞進 prompt 更 production-like。

### Q5. How do you handle unsupported questions?

不讓模型硬猜。若問題需要 valuation model、peer/segment valuation 或 implied growth framework，而 MVP 沒實作，就標記 `unsupported_capability`。這些題保留在 eval details，但不拿來污染 supported quality gate。

### Q6. What would you improve next?

短期先補 demo packaging：Streamlit citation panel、README、demo GIF。技術上下一步是 parent-child retrieval 和 multi-company HYBRID，讓 comparison questions 更穩。

---

## 10. Recommended Demo Queries

RAG_ONLY:

```text
What was Apple's total net sales in fiscal year 2024?
What were Nvidia's main risk factors in its latest 10-K?
How did Apple's Services revenue change in fiscal year 2024?
```

MCP_ONLY:

```text
What is Apple's current stock price?
What is Microsoft's current P/E ratio?
When is Nvidia's next earnings report date?
```

HYBRID:

```text
Compare Apple's reported revenue with its current valuation.
What does Nvidia's filing say about Data Center growth, and what is its current market cap?
```

Demo 時要主動指出：RAG answers 應引用 filing section / page；MCP answers 應顯示 `data_source`。

---

## 11. Strong Closing Statement

這個 project 的重點不是單純把 LLM 接到 PDF，而是建立一個 finance-aware AI system：

- Retrieval layer 知道財報表格不能亂切。
- Search layer 知道財務術語需要 hybrid retrieval。
- Tool layer 知道 market data API 會缺欄位，所以要 fallback 和 structured unavailable。
- Evaluation layer 知道不能只看 aggregate score，必須能追到每題的 retrieval contexts 和 tool outputs。

這些設計讓系統更接近 production finance assistant，而不只是 notebook demo。
