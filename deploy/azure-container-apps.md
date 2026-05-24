# Azure Container Apps Deployment Notes

這份文件對應 `S5-02 Azure Container Apps Deployment Notes`。目標不是重寫 retrieval layer，而是把目前已 Dockerize 的 Streamlit demo 部署到 Azure Container Apps，先拿到可展示的 public URL。

參考 Microsoft 官方文件：

- [Deploy Azure Container Apps with `az containerapp up`](https://learn.microsoft.com/en-us/azure/container-apps/containerapp-up)
- [Manage environment variables on Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/environment-variables)
- [Manage secrets in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets)

## 1. Deployment Scope

第一版部署內容：

- Streamlit UI: `app.py`
- Agent orchestration: `agent/analyst.py`
- Local RAG backend: ChromaDB under `/app/data/chroma`
- MCP finance tools imported in-process from `tools/stock_server.py`
- Market data fallback chain: Polygon.io -> Alpha Vantage -> optional yfinance

第一版刻意不包含：

- Azure AI Search migration
- Blob Storage backed PDF ingestion
- Split MCP server Container App
- Key Vault integration
- Multi-replica production scaling

這是合理的 demo-first deployment。Finance RAG 的正確性仍由目前的 table-aware chunking、Hybrid Search、metadata citation、MCP `data_source` schema 保證；Azure Container Apps 這一步只處理 cloud runtime。

## 2. Required Environment Variables

必要：

```text
OPENAI_API_KEY
POLYGON_API_KEY
```

建議：

```text
ALPHA_VANTAGE_API_KEY
ENABLE_YFINANCE_FALLBACK=false
```

Streamlit runtime 已在 `Dockerfile` 設定：

```text
STREAMLIT_SERVER_ADDRESS=0.0.0.0
STREAMLIT_SERVER_PORT=8501
STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
```

Finance domain 注意：不要把 yfinance 設為主要資料源。它適合作為 last-resort fallback，但在 evaluation 或 demo 裡容易因 rate limit 造成不穩定結果。

## 3. Local Docker Verification

先在本機確認 image 可以完整啟動：

```bash
docker build -t stock-research-ai .

docker stop stock-research-ai-demo 2>/dev/null || true

docker run --rm -d \
  --name stock-research-ai-demo \
  --env-file .env \
  -p 8501:8501 \
  -v /Users/tristan/finance_rag_mcp/data/chroma:/app/data/chroma \
  stock-research-ai

curl -I http://localhost:8501
```

驗收問題：

```text
What was Apple's total net sales in fiscal year 2024?
What is Apple's current stock price?
Compare Apple's reported revenue with its current valuation.
```

預期：

- RAG_ONLY 題應引用 SEC filing section/page。
- MCP_ONLY 題應顯示 `data_source`。
- HYBRID 題應同時使用 filing citation 與 live market data。

## 4. Azure CLI Setup

登入並設定 subscription：

```bash
az login
az account set --subscription "<AZURE_SUBSCRIPTION_ID>"
az extension add --name containerapp --upgrade
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
az provider register --namespace Microsoft.ContainerRegistry
```

設定部署變數：

```bash
export LOCATION="australiaeast"
export RESOURCE_GROUP="rg-stock-research-demo"
export ACA_ENV="cae-stock-research-demo"
export ACR_NAME="<globally_unique_acr_name>"
export APP_NAME="stock-research-ui"
export IMAGE_NAME="stock-research-ai"
export IMAGE_TAG="s5-demo"
```

`ACR_NAME` 必須全域唯一，只能使用小寫英數字。

## 5. Create Azure Resources

建立 resource group、ACR、Container Apps environment：

```bash
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION"

az acr create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ACR_NAME" \
  --sku Basic \
  --admin-enabled true

az containerapp env create \
  --name "$ACA_ENV" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION"
```

## 6. Build and Push Image

建議用 ACR build，避免本機 CPU 架構與 cloud runtime 不一致：

```bash
az acr build \
  --registry "$ACR_NAME" \
  --image "$IMAGE_NAME:$IMAGE_TAG" \
  .
```

如果 subscription 不允許 ACR Tasks，會看到：

```text
TasksOperationsNotAllowed
ACR Tasks requests for the registry ... are not permitted.
```

這不是 Dockerfile 錯誤。改用本機 build，再 push 到 ACR：

```bash
export ACR_SERVER="$(az acr show \
  --name "$ACR_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query loginServer \
  --output tsv)"

az acr login --name "$ACR_NAME"

docker build --platform linux/amd64 \
  -t "$ACR_SERVER/$IMAGE_NAME:$IMAGE_TAG" \
  .

docker push "$ACR_SERVER/$IMAGE_NAME:$IMAGE_TAG"
```

確認 image 已存在：

```bash
az acr repository list \
  --name "$ACR_NAME" \
  --output table

az acr repository show-tags \
  --name "$ACR_NAME" \
  --repository "$IMAGE_NAME" \
  --output table
```

取得 ACR login server：

```bash
export ACR_SERVER="$(az acr show \
  --name "$ACR_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query loginServer \
  --output tsv)"
```

## 7. Create Container App

先把 secret 存成 shell variables。不要把真實 key commit 到 repo：

```bash
export OPENAI_API_KEY_VALUE="<your_openai_key>"
export POLYGON_API_KEY_VALUE="<your_polygon_key>"
export ALPHA_VANTAGE_API_KEY_VALUE="<your_alpha_vantage_key>"
```

建立 app：

```bash
export ACR_USERNAME="$(az acr credential show \
  --name "$ACR_NAME" \
  --query username \
  --output tsv)"

export ACR_PASSWORD="$(az acr credential show \
  --name "$ACR_NAME" \
  --query 'passwords[0].value' \
  --output tsv)"

az containerapp create \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ACA_ENV" \
  --image "$ACR_SERVER/$IMAGE_NAME:$IMAGE_TAG" \
  --target-port 8501 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 1 \
  --cpu 1.0 \
  --memory 2Gi \
  --registry-server "$ACR_SERVER" \
  --registry-username "$ACR_USERNAME" \
  --registry-password "$ACR_PASSWORD" \
  --secrets \
    openai-api-key="$OPENAI_API_KEY_VALUE" \
    polygon-api-key="$POLYGON_API_KEY_VALUE" \
    alpha-vantage-api-key="$ALPHA_VANTAGE_API_KEY_VALUE" \
  --env-vars \
    OPENAI_API_KEY=secretref:openai-api-key \
    POLYGON_API_KEY=secretref:polygon-api-key \
    ALPHA_VANTAGE_API_KEY=secretref:alpha-vantage-api-key \
    ENABLE_YFINANCE_FALLBACK=false
```

如果先跳過 Alpha Vantage，可以移除 `alpha-vantage-api-key` secret 與 `ALPHA_VANTAGE_API_KEY` env var。此時 demo 主要依賴 Polygon.io，`ENABLE_YFINANCE_FALLBACK=false` 代表不啟用 yfinance fallback。

取得 public URL：

```bash
az containerapp show \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query properties.configuration.ingress.fqdn \
  --output tsv
```

## 8. Update an Existing Deployment

重新 build image：

```bash
az acr build \
  --registry "$ACR_NAME" \
  --image "$IMAGE_NAME:$IMAGE_TAG" \
  .
```

更新 container image：

```bash
az containerapp update \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --image "$ACR_SERVER/$IMAGE_NAME:$IMAGE_TAG"
```

更新 CPU / memory：

```bash
az containerapp update \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --cpu 1.0 \
  --memory 2Gi
```

更新 secret：

```bash
az containerapp secret set \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --secrets polygon-api-key="<new_polygon_key>"
```

如果環境變數需要重新指向 secret：

```bash
az containerapp update \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --set-env-vars POLYGON_API_KEY=secretref:polygon-api-key
```

## 9. Verification

看 app 狀態：

```bash
az containerapp show \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "{fqdn:properties.configuration.ingress.fqdn,provisioningState:properties.provisioningState,latestRevision:properties.latestRevisionName}" \
  --output table
```

看 logs：

```bash
az containerapp logs show \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --follow
```

Demo 驗收：

```text
1. Open the Container Apps public URL.
2. Select AAPL and fiscal year 2024.
3. If the Chroma collection is empty, ingest the bundled filing from the UI.
4. Ask: What was Apple's total net sales in fiscal year 2024?
5. Ask: What is Apple's current stock price?
6. Ask: Compare Apple's reported revenue with its current valuation.
```

預期：

- AAPL FY2024 total net sales 應回答 `$391,035 million`。
- Current price / fundamentals 題應包含 `data_source`。
- HYBRID 題應同時包含 SEC filing citation 與 live market data。

## 10. Important Demo Limitations

### ChromaDB is still container-local

目前 `data/chroma` 在 Azure Container Apps 裡是 container filesystem。這代表：

- revision restart 後 collection 可能需要重新 ingest；
- 多 replica 會有資料不一致；
- 這不適合 production long-term storage；
- 第一版 deployment 應保持 `--min-replicas 1 --max-replicas 1`。

下一步可選兩條路：

1. 短期 demo：掛 Azure Files 到 `/app/data/chroma`。
2. 正式版：把 retrieval backend 遷移到 Azure AI Search。

Finance domain 建議是第二條，因為 Azure AI Search hybrid retrieval 可以保留 BM25 + vector + metadata filter 的核心設計。

### Demo data is not a managed filing store

目前 raw PDFs 仍在 repo 的 `data/pdfs/`，不是 Blob Storage。這對 portfolio demo 可以接受，但不適合多使用者或自動 EDGAR ingestion。

### Secrets are Container Apps secrets, not Key Vault yet

本文件先使用 Container Apps app-level secrets。後續 production hardening 再導入 Key Vault reference 與 managed identity。

## 11. Troubleshooting

### Streamlit page does not load

檢查 target port 是否是 `8501`：

```bash
az containerapp show \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query properties.configuration.ingress.targetPort
```

### Polygon returns unauthorized

常見原因是 key 有前後空白。本機 `.env` 不能寫成：

```text
POLYGON_API_KEY= abc123
```

應改成：

```text
POLYGON_API_KEY=abc123
```

Azure secret 也要重新設定：

```bash
az containerapp secret set \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --secrets polygon-api-key="$POLYGON_API_KEY_VALUE"
```

### RAG query returns no context

先判斷是不是 Chroma collection 尚未建立：

```text
Open the UI -> select ticker/year -> run Download & Ingest.
```

如果 restart 後又消失，這是目前 container-local Chroma 的已知限制。不要用 generation prompt 補答案，因為歷史財報數字必須由 SEC filing context 支撐。

### Download & Ingest hangs or disappears

如果按 `Download & Ingest` 後長時間停在 spinner，或 spinner 消失但沒有 `Loaded:` 訊息，先看 replica restart count：

```bash
az containerapp replica list \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --revision "$(az containerapp show \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query properties.latestRevisionName \
    --output tsv)" \
  --query "[].properties.containers[].{name:name,restartCount:restartCount,runningState:runningState}" \
  --output table
```

SEC filing 下載本身不重，真正吃資源的是 chunk 後載入 `sentence-transformers` / `torch` 做 embedding。`0.5 CPU / 1Gi memory` 很容易在 Azure Container Apps 裡重啟。先升到：

```bash
az containerapp update \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --cpu 1.0 \
  --memory 2Gi
```

如果仍不穩，再用 `2 CPU / 4Gi memory` 做 demo 驗證。長期正式架構應把 ingestion 移到 background job，或把 retrieval backend 遷到 Azure AI Search。

### Container App cannot pull from ACR

如果 create 時看到：

```text
UNAUTHORIZED: authentication required
```

代表 Container App 找得到 image，但沒有權限從 private ACR pull。建立 app 時加入：

```bash
--registry-server "$ACR_SERVER" \
--registry-username "$ACR_USERNAME" \
--registry-password "$ACR_PASSWORD"
```

### MCP answer lacks data_source

這代表 tool schema 或 fallback error path 需要修，不應在 UI 層硬塞資料來源。所有 MCP tool response 都必須從 `tools/stock_server.py` 回傳 `data_source`。

## 12. S5-02 Acceptance Checklist

- [x] 文件包含 image build / ACR push / Container Apps 建立流程。
- [x] 文件包含 env vars / secrets 設定。
- [x] 文件說明第一版仍使用 container-local ChromaDB。
- [x] 文件列出必要環境變數。
- [x] 文件列出 demo 驗收問題與 troubleshooting。
