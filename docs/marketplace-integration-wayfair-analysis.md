# Wayfair 接入分析

> 日期：2026-06-08  
> 状态：编码前后边界记录；真实联调前仍需 Wayfair Partner Home / GraphQL schema 复核

## 结论

Wayfair 与传统 REST marketplace 不完全一致。公开资料和供应商 API 入口显示其订单履约更偏 GraphQL 模型，典型链路是：

- OAuth client credentials 获取 access token。
- GraphQL 查询 dropship purchase orders。
- GraphQL registration/acknowledgement 类 mutation 注册履约/请求取件。
- 面单可能通过 registration 结果中的 label URL 或单独 label query 获取。

因此首版实现为 `platform=wayfair`，`auth_type=oauth2_client_credentials_graphql`，并保留 `orders_query`、`register_mutation`、`label_query`、`graphql_url` 等 settings 覆盖项。

## 建议凭据

```json
{
  "client_id": "",
  "client_secret": "",
  "access_token": "",
  "supplier_id": ""
}
```

## 建议 settings

```json
{
  "graphql_url": "https://api.wayfair.com/v1/graphql",
  "token_url": "https://sso.auth.wayfair.com/oauth/token",
  "has_response": false,
  "limit": 50,
  "label_mode": "registration_label_url"
}
```

## 本地字段映射

| 本地字段 | Wayfair 候选字段 |
|---|---|
| `platform_order_id` | `poNumber` |
| `platform_order_no` | `poNumber` |
| `posting_number` | `poNumber` |
| `platform_status` | `status` / `hasResponse` / `orderType` |
| `platform_created_at` | `poDate` |
| `shipping_deadline_at` | `estimatedShipDate` |
| `buyer_selected_logistics` | `shippingInfo.shipSpeed` / `carrierCode` |
| `country_code` | `customerCountry` |
| `buyer_name` | `customerName` |
| `sku` | `products[].partNumber` |
| `quantity` | `products[].quantity` |
| `unit_price` | `products[].price` |

## 必须复核

- 目标账号使用的 GraphQL endpoint、OAuth token endpoint 和 scope。
- `getDropshipPurchaseOrders` 的真实参数、分页模型、排序枚举和值域。
- registration mutation 的 input 类型与字段名，例如 warehouse、pickup date、carrier 等。
- 是否所有订单都返回 `consolidatedShippingLabel.url`，或必须使用单独 label query。
- Castlegate/平台仓订单是否需要排除，或只做 `is_overseas_warehouse` 标记。
