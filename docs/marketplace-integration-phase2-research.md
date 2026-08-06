# Shopify / eBay / Walmart / Temu 第二阶段接入编码参考

> 版本：v0.1  
> 日期：2026-06-06  
> 状态：编码前资料整理稿；实施前需用真实开发者账号复核权限、字段和限流  
> 范围：仅整理 Shopify、eBay、Walmart、Temu 的接口接入资料，不包含代码实现

---

## 1. 文档目标

本文档作为下一阶段新增平台 adapter 的编码参考，单独覆盖 Shopify、eBay、Walmart、Temu，不与第一份 Amazon / Shopee / TikTok Shop / AliExpress / Lazada 资料放在同一文件。

重点回答：

- 每个平台首版接入应覆盖哪些 API 能力。
- 这些能力如何落到当前 `connector_runtime` 的统一接口。
- 鉴权凭据和店铺配置应如何存到 `PlatformAccount.encrypted_credentials` / `settings`。
- 平台订单、包裹、SKU、金额、物流单号、面单字段如何映射到现有本地模型。
- 哪些资料能从公开官方文档确认，哪些必须在开发者后台或真实店铺中复核。

---

## 2. 当前项目接入边界

### 2.1 现有统一接口

当前平台对接应优先新增 `connector_runtime` adapter，通过已有 HTTP 接口服务业务侧：

| 统一动作 | Connector Runtime 接口 | 返回/输入关注点 |
|---|---|---|
| 拉取待处理订单 | `POST /api/v1/connectors/{platform}/orders/unprocessed` | 返回 `NormalizedOrder[]` |
| 刷新订单状态 | `POST /api/v1/connectors/{platform}/orders/status-updates` | 返回 `OrderStatusUpdate[]` |
| 创建/确认平台发货 | `POST /api/v1/connectors/{platform}/shipments/create` | 输入本地订单，返回 `ShipmentResult` |
| 下载面单 | `POST /api/v1/connectors/{platform}/labels/fetch` | 返回 `LabelResult` 二进制 |
| 批量下载面单 | `POST /api/v1/connectors/{platform}/labels/fetch-batch` | 平台支持时实现 |

### 2.2 标准化字段约束

`NormalizedOrder` 当前字段较轻，平台差异应保留在 `raw_payload`：

| 字段 | 建议含义 |
|---|---|
| `platform_order_id` | 平台订单主 ID，尽量稳定且全局唯一 |
| `platform_order_no` | 平台展示订单号，前端查询/展示优先使用 |
| `posting_number` | 包裹号、发货单号、shipment id；无包裹维度时可退回订单号 |
| `platform_status` | 平台原始订单或履约状态 |
| `fulfillment_type` | `FBS` / `FBP` / `FBO` / `SDS` / `Crossborder` 等 |
| `is_overseas_warehouse` | 平台仓、海外仓、平台代履约订单标记 |
| `raw_payload` | 平台原始 JSON，必须保留订单行、物流、金额、地址摘要等字段 |

业务侧已从 `raw_payload` 识别常见 SKU 字段：`offer_id`、`seller_sku`、`seller_custom_field`、`sku`、`item_id` 等；识别常见运单字段：`tracking_number`、`track_number`、`trackingNo`、`waybill_number`、`shipment.tracking_number`、`shipping.tracking_number` 等。新 adapter 应尽量把平台字段归一出这些常见 key，减少业务侧改动。

### 2.3 第二阶段建议平台代码

| 平台 | 建议 `platform` | 建议 `auth_type` | 首版定位 |
|---|---|---|---|
| Shopify | `shopify` | `oauth2_admin_api` | 店铺自发货订单、发货回传 |
| eBay | `ebay` | `oauth2` | marketplace 订单、tracking fulfillment |
| Walmart | `walmart` | `oauth2_client_credentials` | Marketplace released orders、确认/发货 |
| Temu | `temu` | `oauth2_hmac` | 需后台复核后接订单/履约/面单 |

---

## 3. 第一阶段功能范围建议

### 3.1 必做

| 能力 | 目标 |
|---|---|
| 店铺授权/凭据校验 | 能保存 token 或 client credentials，并确认店铺身份 |
| 拉待处理订单 | 只拉待发货、released、unfulfilled 等履约相关订单 |
| 拉订单详情 | 必须包含 SKU、数量、金额、币种、国家、收件信息摘要、发货时限 |
| 创建/确认发货 | 回传 carrier、tracking number、发货行或包裹维度信息 |
| 状态回查 | 同步取消、已发货、部分发货、关闭等状态 |
| 面单处理 | 能下载就实现；平台不提供或依赖额外服务时明确返回不支持 |

### 3.2 暂缓

| 能力 | 暂缓原因 |
|---|---|
| 售后、退款、退货 | 当前流程主要围绕采购、打印、发货、扫码出库 |
| Webhook 全量接入 | 首版轮询更容易稳定，Webhook 可在订单闭环后补 |
| 平台广告、营销、报表 | 非履约主链路 |
| 平台仓库存管理 | 首版只识别 `is_overseas_warehouse`，不处理仓内库存 |

---

## 4. Shopify Admin API

### 4.1 官方资料

- Admin GraphQL Orders query：<https://shopify.dev/docs/api/admin-graphql/latest/queries/orders>
- Admin GraphQL Order object：<https://shopify.dev/docs/api/admin-graphql/latest/objects/Order>
- Fulfillment Orders query：<https://shopify.dev/docs/api/admin-graphql/latest/queries/fulfillmentOrders>
- Fulfillment create mutation：<https://shopify.dev/docs/api/admin-graphql/latest/mutations/fulfillmentCreate>
- Fulfillment tracking update mutation：<https://shopify.dev/docs/api/admin-graphql/latest/mutations/fulfillmentTrackingInfoUpdate>
- OAuth authorization code grant：<https://shopify.dev/docs/apps/build/authentication-authorization/access-tokens/authorization-code-grant>

### 4.2 鉴权与配置

Shopify 建议优先使用 Admin GraphQL API。REST Admin API 仍可见，但 Shopify 新功能和版本演进更偏 GraphQL，首版 adapter 直接走 GraphQL 可减少后续迁移。

建议 `credentials`：

```json
{
  "shop_domain": "example.myshopify.com",
  "access_token": "",
  "client_id": "",
  "client_secret": ""
}
```

建议 `settings`：

```json
{
  "api_version": "2026-04",
  "pull_query": "fulfillment_status:unfulfilled OR fulfillment_status:partial",
  "financial_statuses": ["PAID", "PARTIALLY_PAID"],
  "include_archived": false,
  "label_mode": "unsupported"
}
```

建议 OAuth scopes：

| Scope | 用途 |
|---|---|
| `read_orders` | 查询订单 |
| `read_all_orders` | 如需读取超过默认时间窗口的历史订单，需额外申请 |
| `read_fulfillments` | 查询履约/发货信息 |
| `write_fulfillments` | 创建 fulfillment、回传 tracking |
| `read_assigned_fulfillment_orders` | 如果店铺使用 fulfillment order 流程，需读取分配履约单 |

### 4.3 首版接口清单

| 项目动作 | Shopify API | 说明 |
|---|---|---|
| 店铺校验 | Shop query / Admin API shop 信息 | 校验 token、店铺域名、币种、时区 |
| 拉订单列表 | GraphQL `orders` query | 用 query 过滤未发货/部分发货订单，cursor 分页 |
| 拉订单详情 | `Order` object fields | 补 line items、金额、地址、状态、取消信息 |
| 拉履约单 | `fulfillmentOrders` query 或 `order.fulfillmentOrders` | 获取 fulfillment order id、line item id、履约状态 |
| 创建发货 | `fulfillmentCreate` mutation | 基于 fulfillment order line items 创建 fulfillment |
| 更新物流 | `fulfillmentTrackingInfoUpdate` mutation | 更新 carrier、tracking number、tracking URL |
| 状态回查 | `orders` / `Order` query | 刷新 fulfillment、cancelled、closed 状态 |
| 面单下载 | 非标准 Admin API 能力 | 普通 Admin API 不直接提供平台面单下载，需 Shipping Label app/第三方物流 |

### 4.4 本地字段映射

| 本地字段 | Shopify 字段候选 |
|---|---|
| `platform_order_id` | `Order.id` GraphQL GID；必要时保留 numeric legacy id |
| `platform_order_no` | `Order.name`，例如 `#1001` |
| `posting_number` | `FulfillmentOrder.id`；没有履约单时用 `Order.id` |
| `platform_status` | `displayFulfillmentStatus` + `displayFinancialStatus` + `cancelledAt` 组合 |
| `payment_at` | `processedAt` |
| `platform_created_at` | `createdAt` |
| `shipping_deadline_at` | `fulfillmentOrders.nodes[].fulfillBy`；没有则为空，由本地规则补 |
| `buyer_selected_logistics` | `shippingLine.title` / `shippingLine.code` |
| `shipment_tracking_number` | `fulfillments[].trackingInfo[].number` |
| `country_code` | `shippingAddress.countryCodeV2` |
| `buyer_name` | `shippingAddress.name` |
| `sku` | `lineItems.nodes[].sku` |
| `platform_product_name` | `lineItems.nodes[].title` / `variantTitle` |
| `quantity` | `lineItems.nodes[].quantity` / `currentQuantity` |
| `unit_price` | `lineItems.nodes[].originalUnitPriceSet.shopMoney.amount` |
| `currency` | `totalPriceSet.shopMoney.currencyCode` |

### 4.5 建议 `raw_payload` 归一键

```json
{
  "id": "gid://shopify/Order/123",
  "order_number": "#1001",
  "fulfillment_order_id": "gid://shopify/FulfillmentOrder/456",
  "status": "UNFULFILLED",
  "financial_status": "PAID",
  "shipping": {
    "service": "Standard",
    "country_code": "US",
    "tracking_number": ""
  },
  "items": [
    {
      "seller_sku": "SKU-001",
      "sku": "SKU-001",
      "quantity": 1,
      "title": "Product title",
      "price": "12.34",
      "currency": "USD"
    }
  ]
}
```

### 4.6 关键风险

- Shopify 是独立店铺系统，不是传统 marketplace；订单发货流程取决于 merchant 是否使用 Shopify Shipping、第三方履约服务或自定义 fulfillment service。
- 普通 Admin API 首版不应承诺“下载 Shopify 平台面单”。更稳妥的闭环是：同步订单、在本地打单、再通过 `fulfillmentCreate` / tracking update 回传物流。
- Shopify GraphQL 使用 cost-based rate limit，不是简单 QPS；实现时要读取 throttling 信息并控制 cursor 分页。
- 订单读取时间范围、PII、历史订单可能受 app scopes 和店铺授权影响。

---

## 5. eBay Sell Fulfillment API

### 5.1 官方资料

- Sell Fulfillment API overview：<https://developer.ebay.com/api-docs/sell/fulfillment/overview.html>
- Get orders：<https://developer.ebay.com/api-docs/sell/fulfillment/resources/order/methods/getOrders>
- Get order：<https://developer.ebay.com/api-docs/sell/fulfillment/resources/order/methods/getOrder>
- Create shipping fulfillment：<https://developer.ebay.com/api-docs/sell/fulfillment/resources/order/methods/createShippingFulfillment>
- Get shipping fulfillments：<https://developer.ebay.com/api-docs/sell/fulfillment/resources/order/methods/getShippingFulfillments>
- OAuth authorization code grant：<https://developer.ebay.com/api-docs/static/oauth-auth-code-grant.html>

### 5.2 鉴权与配置

eBay Sell API 使用 OAuth2 user access token。订单和发货属于卖家授权资源，不能只用 app token。

建议 `credentials`：

```json
{
  "client_id": "",
  "client_secret": "",
  "ru_name": "",
  "access_token": "",
  "refresh_token": "",
  "token_expires_at": ""
}
```

建议 `settings`：

```json
{
  "base_url": "https://api.ebay.com",
  "marketplace_id": "EBAY_US",
  "pull_filter": "orderfulfillmentstatus:{NOT_STARTED|IN_PROGRESS}",
  "limit": 100,
  "label_mode": "unsupported"
}
```

建议 OAuth scopes：

| Scope | 用途 |
|---|---|
| `https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly` | 查询订单、履约信息 |
| `https://api.ebay.com/oauth/api_scope/sell.fulfillment` | 创建 shipping fulfillment |

### 5.3 首版接口清单

| 项目动作 | eBay API | 说明 |
|---|---|---|
| 授权换 token | OAuth authorization code grant | 卖家授权，保存 refresh token |
| 刷新 token | OAuth refresh token | 定期换 access token |
| 拉订单列表 | `getOrders` | 按创建/更新时间、订单状态、履约状态过滤 |
| 拉订单详情 | `getOrder` | 获取 shipping、lineItems、pricing、buyer |
| 创建发货 | `createShippingFulfillment` | 按 order id 和 line item 回传 carrier/tracking |
| 查询发货 | `getShippingFulfillments` | 获取已创建 fulfillment 和 tracking |
| 状态回查 | `getOrders` / `getOrder` | 更新取消、已付款、已发货状态 |
| 面单下载 | 非 Sell Fulfillment 标准能力 | Sell Fulfillment API 主要是 tracking fulfillment；平台购标需另查 eBay shipping label 能力 |

### 5.4 本地字段映射

| 本地字段 | eBay 字段候选 |
|---|---|
| `platform_order_id` | `orderId` |
| `platform_order_no` | `legacyOrderId` / `salesRecordReference` / `orderId` |
| `posting_number` | `orderId`；部分发货时可用 `orderId + fulfillmentId` |
| `platform_status` | `orderFulfillmentStatus` / `orderPaymentStatus` / cancel status |
| `payment_at` | `paymentSummary.payments[].paymentDate` |
| `platform_created_at` | `creationDate` |
| `shipping_deadline_at` | `lineItems[].lineItemFulfillmentInstructions.shipByDate` 或 fulfillment instructions 中的日期字段 |
| `buyer_selected_logistics` | `fulfillmentStartInstructions[].shippingStep.shippingServiceCode` |
| `shipment_tracking_number` | `fulfillments[].shipmentTrackingNumber` |
| `country_code` | `fulfillmentStartInstructions[].shippingStep.shipTo.contactAddress.countryCode` |
| `buyer_name` | `shipTo.fullName` / buyer username |
| `sku` | `lineItems[].sku` |
| `platform_product_name` | `lineItems[].title` |
| `quantity` | `lineItems[].quantity` |
| `unit_price` | `lineItems[].lineItemCost.value` |
| `currency` | `lineItems[].lineItemCost.currency` |

### 5.5 发货请求要点

`createShippingFulfillment` 首版应从本地订单构造：

| 字段 | 来源 |
|---|---|
| `lineItems[].lineItemId` | eBay 订单详情 line item |
| `lineItems[].quantity` | 本地待发货数量，首版通常全量发 |
| `shippedDate` | 本地发货/扫码出库时间 |
| `shippingCarrierCode` | 本地物流商映射到 eBay carrier code |
| `trackingNumber` | 本地货运单号 |

### 5.6 建议 `raw_payload` 归一键

```json
{
  "id": "12-34567-89012",
  "order_number": "12-34567-89012",
  "status": "NOT_STARTED",
  "shipping": {
    "service": "USPSPriority",
    "country_code": "US",
    "tracking_number": ""
  },
  "items": [
    {
      "line_item_id": "v1|123|456",
      "seller_sku": "SKU-001",
      "sku": "SKU-001",
      "quantity": 1,
      "title": "Product title",
      "price": "12.34",
      "currency": "USD"
    }
  ]
}
```

### 5.7 关键风险

- eBay 的订单状态和付款状态要一起判断；只看 `orderFulfillmentStatus` 可能会拉到未付款或取消相关订单。
- 部分发货必须按 `lineItemId` 和数量精确回传；首版若只支持整单发货，需要在 UI/任务层限制。
- eBay carrier code 需要映射表，不能直接把本地物流商中文名传给平台。
- Sell Fulfillment API 不等同于面单购买/下载。首版建议把 `labels/fetch` 标记为 unsupported，后续再评估 eBay Labels 或第三方物流。

---

## 6. Walmart Marketplace APIs

### 6.1 官方资料

- Walmart Marketplace Developer Portal：<https://developer.walmart.com/us-marketplace>
- Choose an Orders API：<https://developer.walmart.com/us-marketplace/docs/choose-an-orders-api>
- Orders API 文档入口：<https://developer.walmart.com/us-marketplace/reference/orders>
- Marketplace authentication 文档入口：<https://developer.walmart.com/us-marketplace/docs/authentication>
- Ship with Walmart 文档入口：<https://developer.walmart.com/us-marketplace/docs/ship-with-walmart>

公开页面存在地区和动态渲染差异，实施前应登录 Walmart Developer Portal，用目标 seller account 复核 Orders API v3 的具体 reference path、请求体和 header 要求。

### 6.2 鉴权与配置

Walmart Marketplace API 当前公开资料通常按 Client ID / Client Secret 换 access token，再在业务请求中携带 Walmart 规定 headers。老账号或特殊集成可能仍涉及 consumer id/private key 模式，实施前需按实际后台确认。

建议 `credentials`：

```json
{
  "client_id": "",
  "client_secret": "",
  "access_token": "",
  "token_expires_at": "",
  "seller_id": ""
}
```

建议 `settings`：

```json
{
  "base_url": "https://marketplace.walmartapis.com",
  "market": "us",
  "pull_statuses": ["Created", "Acknowledged"],
  "released_only": true,
  "label_mode": "ship_with_walmart_optional"
}
```

常见 headers 需复核：

| Header | 用途 |
|---|---|
| `WM_SEC.ACCESS_TOKEN` | access token |
| `WM_QOS.CORRELATION_ID` | 请求追踪 ID，建议每次请求生成 UUID |
| `WM_SVC.NAME` | 服务名，通常为 Walmart Marketplace |
| `WM_MARKET` | 站点/市场，例如 `us` |
| `WM_CONSUMER.CHANNEL.TYPE` | 部分账号/接口可能要求 |

### 6.3 首版接口清单

| 项目动作 | Walmart API | 说明 |
|---|---|---|
| 获取 access token | Authentication / Token API | Client ID/Secret 换 token |
| 拉 released orders | Orders API released orders | 首版优先拉可处理订单 |
| 拉订单列表 | Orders API all orders | 按时间、状态分页补充查询 |
| 拉订单详情 | Orders API order by purchase order id | 获取订单行、金额、地址、SLA |
| 确认订单 | Orders API acknowledge order / lines | Walmart 通常要求先 acknowledge |
| 发货回传 | Orders API ship order lines | 回传 carrier、tracking、ship date、order line |
| 取消/退款状态回查 | Orders API | 首版只同步状态，不做售后动作 |
| 面单 | Ship with Walmart / Shipping Labels | 如果店铺开通 SWW，可评估；否则首版 unsupported |

### 6.4 本地字段映射

| 本地字段 | Walmart 字段候选 |
|---|---|
| `platform_order_id` | `purchaseOrderId` |
| `platform_order_no` | `customerOrderId` / `purchaseOrderId` |
| `posting_number` | `purchaseOrderId`；拆单时用 `purchaseOrderId + orderLineNumber` |
| `platform_status` | `orderLines.orderLine[].orderLineStatuses.orderLineStatus[].status` |
| `payment_at` | `orderDate`；如返回付款字段则优先付款时间 |
| `platform_created_at` | `orderDate` |
| `shipping_deadline_at` | `shippingInfo.estimatedShipDate` / `estimatedDeliveryDate` |
| `buyer_selected_logistics` | `shippingInfo.methodCode` / `shippingInfo.carrierMethodName` |
| `shipment_tracking_number` | ship response 或 order line status tracking info |
| `country_code` | `shippingInfo.postalAddress.country` |
| `buyer_name` | `shippingInfo.postalAddress.name` |
| `sku` | `orderLines.orderLine[].item.sku` |
| `platform_product_name` | `orderLines.orderLine[].item.productName` |
| `quantity` | `orderLines.orderLine[].orderLineQuantity.amount` |
| `unit_price` | `charges.charge[].chargeAmount.amount` |
| `currency` | `charges.charge[].chargeAmount.currency` |

### 6.5 发货请求要点

Walmart 的发货通常在 order line 维度完成，首版 adapter 应保留：

| 字段 | 来源 |
|---|---|
| `purchaseOrderId` | 平台订单主 ID |
| `orderLineNumber` | 订单行号 |
| `shipDateTime` | 本地发货时间 |
| `carrierName` / `carrierCode` | 本地物流商映射 |
| `methodCode` | 配送方式，按 Walmart 枚举 |
| `trackingNumber` | 本地货运单号 |
| `trackingURL` | 如物流商可提供则带上 |

### 6.6 建议 `raw_payload` 归一键

```json
{
  "id": "1234567890123",
  "order_number": "987654321",
  "status": "Created",
  "shipping": {
    "service": "Standard",
    "country_code": "US",
    "tracking_number": ""
  },
  "items": [
    {
      "line_number": "1",
      "seller_sku": "SKU-001",
      "sku": "SKU-001",
      "quantity": 1,
      "title": "Product title",
      "price": "12.34",
      "currency": "USD"
    }
  ]
}
```

### 6.7 关键风险

- Walmart 首版需要明确是否自动 acknowledge。若拉单后不及时 acknowledge，可能影响 seller SLA；但自动确认也意味着本地已接单。
- 订单行状态是关键，整单状态不能完全代表每个 SKU 的履约状态。
- Walmart API 对 header、correlation id、market、限流和错误码比较敏感，实现时要统一请求封装和重试策略。
- Ship with Walmart/平台面单不是所有卖家或配送场景都可用，首版不要默认承诺面单下载。

---

## 7. Temu Open Platform

### 7.1 官方资料

- Temu Partner Platform API documentation：<https://partner.temu.com/documentation>
- Temu / PDD Holdings Open Platform Postman workspace：<https://www.postman.com/temu-open/temu-open-platform/overview>

Temu 的官方文档入口可以访问，但接口详情在公开网络下主要依赖前端渲染、后台登录、店铺/应用权限。Postman workspace 可作为辅助线索，不应替代 Partner Platform 官方后台确认。

### 7.2 鉴权与配置

Temu 接入需在 Partner Platform 中确认当前应用的授权模式、站点范围、API gateway、签名规则、token 有效期和刷新方式。公开资料不足以最终确认全部字段。

建议先按 OAuth/HMAC 型平台建模：

```json
{
  "app_key": "",
  "app_secret": "",
  "access_token": "",
  "refresh_token": "",
  "seller_id": "",
  "mall_id": ""
}
```

建议 `settings`：

```json
{
  "base_url": "https://openapi-b-us.temu.com",
  "region": "US",
  "pull_statuses": ["pending_shipment", "awaiting_shipping"],
  "label_mode": "requires_partner_portal_confirmation"
}
```

实施前必须复核：

| 项 | 需确认内容 |
|---|---|
| API gateway | 不同区域是否使用不同域名 |
| 签名规则 | 公共参数排序、body 是否参与签名、hash 算法 |
| token 刷新 | refresh token 是否一次性使用、有效期、并发刷新要求 |
| 店铺标识 | `seller_id`、`mall_id`、`shop_id` 或其他字段语义 |
| API 权限 | 订单、物流、面单是否分开申请 |

### 7.3 首版接口族清单

以下为首版应在 Temu Partner Platform 中逐项确认的接口族，不在本稿中固化具体 method/path：

| 项目动作 | Temu API 族 | 待复核重点 |
|---|---|---|
| 授权换 token | Authorization / Token | code 换 token、refresh token、店铺身份 |
| 店铺校验 | Seller / Mall / Shop | 店铺名称、站点、seller/mall id |
| 拉订单列表 | Order list/search | 待发货状态、时间字段、分页 cursor |
| 拉订单详情 | Order detail | SKU、数量、金额、收件国家、SLA、履约方式 |
| 包裹查询 | Package / Fulfillment | package id、拆包、平台仓/卖家仓标记 |
| 发货回传 | Shipping / Fulfillment | carrier、tracking number、发货时间、包裹维度 |
| 面单生成 | Shipping label / document | 是否异步、PDF/图片、批量下载 |
| 状态回查 | Order / Package status | 取消、已发货、已揽收、妥投 |

### 7.4 本地字段映射

| 本地字段 | Temu 字段候选，需后台复核 |
|---|---|
| `platform_order_id` | `order_id` / `parent_order_sn` / `order_sn` |
| `platform_order_no` | 平台展示订单号 / `order_sn` |
| `posting_number` | `package_id` / `fulfillment_id` / `shipping_order_id` |
| `platform_status` | order status / package status |
| `payment_at` | pay time / paid at |
| `platform_created_at` | create time |
| `shipping_deadline_at` | latest ship time / delivery SLA |
| `buyer_selected_logistics` | shipping service / logistics channel |
| `shipment_tracking_number` | tracking number / waybill number |
| `country_code` | shipping country / region code |
| `buyer_name` | receiver name，可能受 PII 权限限制 |
| `sku` | seller SKU / goods SKU / product SKU |
| `platform_product_name` | goods name / product name |
| `quantity` | item quantity |
| `unit_price` | item price / paid price |
| `currency` | currency |

### 7.5 建议 `raw_payload` 归一键

```json
{
  "id": "TEMU_ORDER_ID",
  "order_number": "TEMU_ORDER_NO",
  "package_id": "TEMU_PACKAGE_ID",
  "status": "awaiting_shipping",
  "shipping": {
    "service": "",
    "country_code": "",
    "tracking_number": ""
  },
  "items": [
    {
      "seller_sku": "SKU-001",
      "sku": "SKU-001",
      "quantity": 1,
      "title": "Product title",
      "price": "12.34",
      "currency": "USD"
    }
  ]
}
```

### 7.6 关键风险

- Temu 资料当前可信度低于 Shopify/eBay/Walmart，必须以 Partner Platform 后台 API reference 为准。
- Temu 订单可能存在平台托管履约、半托管、卖家自发货等差异，首版要先确认本项目目标店铺是哪种履约模式。
- 面单和发货能力可能依赖具体店铺角色、站点、物流方案，不应在未拿到真实权限前承诺。
- 如果接口返回 PII 受限，应先确认本地业务是否真的需要完整地址；能不存完整 PII 就尽量不存。

---

## 8. 跨平台字段映射总表

| 本地字段 | Shopify | eBay | Walmart | Temu |
|---|---|---|---|---|
| `platform_order_id` | `Order.id` | `orderId` | `purchaseOrderId` | `order_id` / `order_sn` |
| `platform_order_no` | `Order.name` | `legacyOrderId` / `salesRecordReference` | `customerOrderId` | 展示订单号 |
| `posting_number` | `FulfillmentOrder.id` | `orderId` / fulfillment id | `purchaseOrderId + line` | `package_id` / fulfillment id |
| `platform_status` | fulfillment/financial/cancel status | fulfillment/payment status | order line status | order/package status |
| `payment_at` | `processedAt` | payment date | `orderDate` 或付款字段 | paid time |
| `platform_created_at` | `createdAt` | `creationDate` | `orderDate` | create time |
| `shipping_deadline_at` | `fulfillBy` | `shipByDate` | estimated ship/delivery date | latest ship/SLA |
| `buyer_selected_logistics` | shipping line | shipping service code | method/carrier name | shipping service/channel |
| `shipment_tracking_number` | fulfillment tracking number | fulfillment tracking number | tracking number | tracking/waybill number |
| `country_code` | shipping country code | shipTo country code | postal address country | shipping country |
| `sku` | line item SKU | line item SKU | item SKU | seller/goods SKU |
| `quantity` | line item quantity | line item quantity | order line quantity | item quantity |
| `unit_price` | unit price set | line item cost | charge amount | item paid price |
| `currency` | shop/presentment currency | line item currency | charge currency | currency |

---

## 9. 凭据、token 与安全注意事项

### 9.1 `PlatformAccount.account_id` 建议

| 平台 | 建议存储值 |
|---|---|
| Shopify | `shop_domain`，例如 `example.myshopify.com` |
| eBay | eBay seller user id 或授权 token 对应 user id |
| Walmart | seller id / partner id |
| Temu | `mall_id` 或官方店铺唯一 ID，需后台复核 |

### 9.2 Token 刷新原则

- OAuth token 过期前主动刷新，避免同步任务中途失败。
- 同一店铺 token 刷新必须加锁，避免并发刷新覆盖凭据。
- refresh token 如果一次性使用，刷新和保存必须在同一临界区完成。
- `encrypted_credentials` 中只保存密文，日志禁止输出 access token、refresh token、client secret、app secret。
- connector error 的 `raw` 字段要脱敏，尤其是 Authorization header、PII、地址和手机号。

### 9.3 限流和重试

| 平台 | 重点 |
|---|---|
| Shopify | GraphQL cost-based throttle，读取 response extensions 后节流 |
| eBay | 按 API family 和 seller token 限流，429/5xx 做指数退避 |
| Walmart | header 和 correlation id 必须完整，429/5xx 做退避，业务错误不要盲重试 |
| Temu | 需后台确认限流模型和错误码，先按平台+店铺维度限速 |

---

## 10. 编码顺序建议

| 顺序 | 平台 | 原因 |
|---|---|---|
| 1 | Shopify | GraphQL 文档完整，订单/发货闭环清晰，面单可先标 unsupported |
| 2 | eBay | Sell Fulfillment API 链路明确，适合沉淀 OAuth2 + line item fulfillment |
| 3 | Walmart | 订单/发货能力明确，但 acknowledge 和 order line 维度需要更细测试 |
| 4 | Temu | 必须先拿开发者后台和真实店铺权限复核接口 |

如果业务优先级不同，可调整顺序；技术风险最低路线是先 Shopify，再 eBay。

---

## 11. 实施前待确认问题

| 问题 | 影响 |
|---|---|
| 四个平台是否已有开发者账号、应用、测试店铺或 sandbox？ | 决定能否真实联调 |
| 首版是否只处理卖家自发货订单？ | 决定是否跳过平台仓/托管履约 |
| 是否要求首版必须下载平台面单？ | Shopify/eBay/Walmart/Temu 的面单能力差异很大 |
| 是否允许 Shopify/eBay 首版只回传 tracking，不创建平台面单？ | 可显著降低首版复杂度 |
| Walmart 是否自动 acknowledge released order？ | 影响 SLA 和业务接单语义 |
| Temu 店铺履约模式是什么？ | 影响订单、包裹、发货、面单接口 |
| 是否需要完整买家地址和手机号？ | 涉及 PII 权限、脱敏、存储策略 |
| 本地物流商名称如何映射平台 carrier code？ | eBay/Walmart 发货回传必须处理 |
| 是否需要部分发货？ | eBay/Walmart/Shopify 都有 line item 维度复杂度 |

---

## 12. 资料可信度标记

| 平台 | 当前可信度 | 说明 |
|---|---|---|
| Shopify | 高 | 官方 Shopify.dev 页面可访问，GraphQL 订单、履约和 OAuth 链路清晰 |
| eBay | 高 | 官方 eBay Developer Sell Fulfillment 与 OAuth 文档明确 |
| Walmart | 中高 | 官方 Developer Portal 有 Orders/Auth/Ship with Walmart 入口；具体 reference 需登录复核 |
| Temu | 中低 | 官方 Partner Platform 入口可访问，但接口详情需后台权限确认 |

---

## 13. 下一步建议

1. 按本文档的“实施前待确认问题”收集四个平台真实账号、应用、店铺和权限。
2. 每个平台各导出或抓取 3 类样例 JSON：待发货、已发货、取消/关闭。
3. 先为 Shopify 设计 adapter 字段样例和测试用例，因为它最适合作为第二阶段的第一块模板。
4. Temu 在编码前单独开一次后台 API reference 核对，不建议只凭公开页面直接实现。
