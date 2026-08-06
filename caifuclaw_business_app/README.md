# CaifuClaw Business App

客户业务应用，负责订单入库、采购、打印、报表、定时任务和前端页面。

平台 API 适配不在本应用内实现，统一通过 `connector_runtime` 调用。

启动：

```powershell
$env:PYTHONPATH = (Get-Location).Path
Push-Location caifuclaw_business_app
try {
  python -m uvicorn app.main:app --host 127.0.0.1 --port 9999
} finally {
  Pop-Location
}
```

产品目录更新：

```bash
python caifuclaw_business_app/scripts/update_product_catalog.py
```

默认会自动读取 `~/demo_data/result_data_sync/Order follow up 2026.xlsx` 并正式写入产品基础数据。只预览不写库可加 `--dry-run`；需要复查指定订单或 SKU 可加 `--order-no DEMO-ORDER-002 --sku DEMO-SKU-001`。

配置项：

```toml
[services]
connector_runtime_url = "http://127.0.0.1:8100"

[security]
# Required for /internal/* service-to-service credential endpoints.
internal_service_token = "generate-a-long-random-value"
```
