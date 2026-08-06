# Amazon / Shopee / TikTok Shop / AliExpress / Lazada 接入资料整理

> 版本：v0.1  
> 日期：2026-06-06  
> 状态：资料整理稿，实施前需按平台开发者后台复核权限与最新字段  
> 范围：仅整理接口资料和项目接入边界，不包含代码实现

---

## 1. 文档目标

本文档用于为下一步新增 Amazon、Shopee、TikTok Shop、AliExpress、Lazada 平台对接做接口资料准备。重点不是完整复制平台文档，而是回答当前 CaifuClaw AI 项目实施前必须搞清楚的几件事：

- 每个平台第一阶段要接哪些接口。
- 鉴权凭据应如何落到现有 `PlatformAccount.encrypted_credentials`。
- 平台订单、包裹、SKU、物流、面单字段如何映射到现有订单模型。
- 哪些接口细节已经能从官方公开文档确认，哪些必须在开发者后台/应用审核后复核。

---

## 2. 当前项目接入边界

### 2.1 现有架构

当前项目已把平台适配职责放在 `connector_runtime`：

| 模块 | 当前职责 |
|---|---|
| `connector_runtime` | 平台 API 适配、字段标准化、发货、面单下载 |
| `caifuclaw_business_app` | 店铺凭据管理、订单同步、订单入库、订单明细、采购/打印流程 |
| `caifuclaw_business_app` | 店铺配置、OAuth 授权、凭据加密与业务流程 |

后续新增平台原则上应新增 `connector_runtime` adapter，并通过当前统一接口接入业务侧：

| 统一动作 | Connector Runtime 接口 | 说明 |
|---|---|---|
| 拉取待处理订单 | `POST /api/v1/connectors/{platform}/orders/unprocessed` | 返回 `NormalizedOrder[]` |
| 刷新订单状态 | `POST /api/v1/connectors/{platform}/orders/status-updates` | 返回 `OrderStatusUpdate[]`，可选 |
| 创建/确认平台发货 | `POST /api/v1/connectors/{platform}/shipments/create` | 返回 `ShipmentResult` |
| 下载面单 | `POST /api/v1/connectors/{platform}/labels/fetch` | 返回 PDF/图片二进制 |
| 批量下载面单 | `POST /api/v1/connectors/{platform}/labels/fetch-batch` | 平台支持时实现 |

### 2.2 当前标准化订单结构

`connector_runtime` 当前标准化结果很轻量：

| 字段 | 说明 |
|---|---|
| `platform_order_id` | 平台订单主 ID |
| `platform_order_no` | 平台可读订单号 |
| `posting_number` | 包裹号/发货单号/包裹维度唯一键 |
| `platform_status` | 平台原始状态 |
| `fulfillment_type` | FBS/FBO/FBP/DBS/CROSSBORDER 等 |
| `is_overseas_warehouse` | 平台仓/海外仓订单标记 |
| `raw_payload` | 平台原始 JSON，用于业务侧抽字段 |

业务侧会从 `raw_payload` 抽取：

- 买家、国家、币种、金额、付款时间、创建时间、发货截止时间。
- 商品明细：`products` / `items` / `order_items` / 嵌套 `orders[].items`。
- SKU 优先顺序包含 `offer_id`、`seller_sku`、`seller_custom_field`、`sku`、`item_id` 等。
- 物流单号优先顺序包含 `tracking_number`、`track_number`、`waybill_number`、`shipment.tracking_number`、`shipping.tracking_number` 等。

### 2.3 建议新增平台代码

建议统一使用以下平台代码，避免后续表字段和前端筛选混乱：

| 平台 | 建议 `platform` | 鉴权类型 |
|---|---|---|
| Amazon | `amazon` | OAuth2 + AWS SigV4 |
| Shopee | `shopee` | OAuth2-like 授权码 + HMAC-SHA256 |
| TikTok Shop | `tiktok_shop` | OAuth2 + HMAC/SHA256 签名 |
| AliExpress | `aliexpress` | OAuth2/Top API session + 签名 |
| Lazada | `lazada` | OAuth2/Top API access token + 签名 |

---

## 3. 第一阶段功能范围建议

### 3.1 必做

| 能力 | 目标 |
|---|---|
| 店铺授权 | 能保存并刷新令牌，能校验店铺身份 |
| 拉取待处理订单 | 以待发货/待处理状态为主，不拉历史全量订单 |
| 拉取订单详情 | 必须包含 SKU、数量、金额、买家国家、物流方式、截止时间 |
| 平台发货/安排物流 | 仅覆盖平台 FBS/卖家自发货流程 |
| 面单下载 | 保存为现有 `label_files` 支持的 PDF/图片 |
| 状态回查 | 订单取消、已发货、妥投等状态能同步回本地 |

### 3.2 暂缓

| 能力 | 暂缓原因 |
|---|---|
| 售后/退款 | 当前订单履约主流程未覆盖 |
| 平台广告/营销 | 非履约核心 |
| FBA/FBL/FBT 等平台仓完整库存管理 | 当前系统只需识别海外仓/平台仓订单，不一定要处理仓内库存 |
| Webhook 全量接入 | 可第二阶段做，第一阶段先轮询稳定落地 |

---

## 4. 平台资料整理

### 4.1 Amazon Selling Partner API

#### 官方资料

- SP-API 文档索引：<https://developer-docs.amazon.com/sp-api/llms.txt>
- SP-API Endpoints：<https://developer-docs.amazon.com/sp-api/docs/sp-api-endpoints>
- Connect to SP-API：<https://developer-docs.amazon.com/sp-api/docs/connecting-to-the-selling-partner-api>
- Orders API：<https://developer-docs.amazon.com/sp-api/docs/orders-api>
- Orders API Rate Limits：<https://developer-docs.amazon.com/sp-api/docs/orders-api-rate-limits>
- Merchant Fulfillment API：<https://developer-docs.amazon.com/sp-api/docs/merchant-fulfillment-api>
- Tokens API / RDT：<https://developer-docs.amazon.com/sp-api/docs/authorization-with-the-restricted-data-token>

#### 鉴权与配置

Amazon 比其他平台复杂，需要同时处理：

| 项 | 说明 |
|---|---|
| LWA refresh token | 卖家授权后获取，用于换 1 小时有效的 LWA access token |
| AWS access key / secret key | 请求 SP-API 需要 AWS SigV4 签名 |
| Role ARN | 如果按 SP-API 标准 AssumeRole，需要配置 IAM role |
| marketplaceIds | 订单查询必须按站点/区域指定 |
| endpoint region | NA/EU/FE 三套 endpoint，AWS region 分别为 `us-east-1`、`eu-west-1`、`us-west-2` |
| RDT | 访问买家地址、买家信息等 PII restricted operation 时需要 Restricted Data Token |

建议 `credentials`：

```json
{
  "lwa_client_id": "",
  "lwa_client_secret": "",
  "refresh_token": "",
  "aws_access_key_id": "",
  "aws_secret_access_key": "",
  "role_arn": ""
}
```

建议 `settings`：

```json
{
  "base_url": "https://sellingpartnerapi-na.amazon.com",
  "aws_region": "us-east-1",
  "marketplace_ids": ["ATVPDKIKX0DER"],
  "pull_order_statuses": ["Unshipped", "PartiallyShipped"],
  "use_restricted_data_token": true
}
```

#### 第一阶段接口清单

| 项目动作 | Amazon API | 用途 |
|---|---|---|
| 店铺/站点校验 | Sellers API `getMarketplaceParticipations` | 确认授权卖家可用站点 |
| 拉订单列表 | Orders API `getOrders` 或 v2026 `searchOrders` | 按创建/更新时间和订单状态拉取 |
| 拉订单详情 | Orders API `getOrder` | 补订单头字段 |
| 拉商品明细 | Orders API `getOrderItems` | SKU、数量、价格 |
| 拉地址/买家 | `getOrderAddress`、`getOrderBuyerInfo` | 需要 RDT，涉及 PII |
| 发货确认 | Orders API `confirmShipment` | 自有物流回传承运商和跟踪号 |
| 买 Amazon Shipping 面单 | Merchant Fulfillment `getEligibleShipmentServices` + `createShipment` | 需要 Direct to Consumer Shipping Restricted role |
| 面单重取 | Merchant Fulfillment `getShipment` | 取已创建 shipment 和 label 信息 |
| 报表补数 | Reports API `createReport` / `getReport` / `getReportDocument` | 大批量历史订单或特殊报表 |

#### 映射建议

| 本地字段 | Amazon 字段候选 |
|---|---|
| `platform_order_id` | `AmazonOrderId` |
| `platform_order_no` | `AmazonOrderId` |
| `posting_number` | 第一阶段可用 `AmazonOrderId`；若按包裹拆分，可用 `AmazonOrderId + shipment/package index` |
| `platform_status` | `OrderStatus` |
| `payment_at` | `PurchaseDate` 或 `LastUpdateDate` |
| `shipping_deadline_at` | `LatestShipDate` |
| `buyer_selected_logistics` | `ShipmentServiceLevelCategory` / `ShipServiceLevel` |
| `country_code` | `ShippingAddress.CountryCode` |
| `sku` | `SellerSKU` |
| `platform_product_name` | `Title` |
| `quantity` | `QuantityOrdered` |
| `unit_price` | `ItemPrice.Amount` |
| `currency` | `ItemPrice.CurrencyCode` |

#### 关键风险

- Orders API v0 已标注 deprecated，官方当前版本为 v2026-01-01；实施时要评估直接接 v2026，还是先接 v0 以覆盖 `getOrderItems` 等成熟操作。
- PII 访问需要 RDT 和 restricted role，审核成本高；如果首版只做仓内拣货，需确认是否可以不拉完整地址。
- `getOrders` 默认限流很低，官方默认 `0.0167 rps / burst 20`；同步策略必须按店铺错峰和游标增量。

---

### 4.2 Shopee Open Platform v2

#### 官方资料

- Shopee Open Platform：<https://open.shopee.com/>
- OpenAPI 2.0 Overview：<https://open.shopee.com/documents?module=87&type=2&id=58&version=2>
- API Call Flows：<https://open.shopee.com/documents?module=87&type=2&id=60&version=2>
- 结构化 API 元数据入口示例：<https://open.shopee.com/opservice/api/v1/doc/api/?api_name=v2.order.get_order_list&version=2>

已从官方结构化元数据确认的公共参数：

| 参数 | 说明 |
|---|---|
| `partner_id` | 注册成功后分配 |
| `timestamp` | 请求时间戳，5 分钟过期 |
| `access_token` | 店铺 API access token，官方元数据说明有效期 4 小时 |
| `shop_id` | Shopee 店铺唯一 ID |
| `sign` | HMAC-SHA256 签名，Shop API 按 `partner_id + path + timestamp + access_token + shop_id + partner_key` 生成 |

Public API 的签名不带 `access_token` / `shop_id`，按 `partner_id + path + timestamp + partner_key` 生成。

#### 鉴权与配置

建议 `credentials`：

```json
{
  "partner_id": "",
  "partner_key": "",
  "shop_id": "",
  "access_token": "",
  "refresh_token": ""
}
```

建议 `settings`：

```json
{
  "base_url": "https://partner.shopeemobile.com",
  "region": "SG",
  "pull_order_statuses": ["READY_TO_SHIP", "PROCESSED"],
  "shipping_document_type": "THERMAL_AIR_WAYBILL"
}
```

#### 第一阶段接口清单

| 项目动作 | Shopee API | 官方元数据确认说明 |
|---|---|---|
| 换 access token | `v2.public.get_access_token` | 使用授权 code 获取 `shop_id`、`access_token`、`refresh_token` |
| 刷新 token | `v2.public.refresh_access_token` | `refresh_token` 一次性使用，调用后返回新的 refresh token |
| 查授权店铺 | `v2.public.get_shops_by_partner` | 获取已授权给 partner 的店铺基础信息 |
| 店铺校验 | `v2.shop.get_shop_info` | 获取店铺信息 |
| 拉订单列表 | `v2.order.get_order_list` | 搜索订单，可按状态过滤 |
| 拉订单详情 | `v2.order.get_order_detail` | 获取订单详情 |
| 获取物流参数 | `v2.logistics.get_shipping_parameter` | 判断 pickup/dropoff/non-integrated，需订单处于可发货状态 |
| 安排发货 | `v2.logistics.ship_order` | 发起 pickup/dropoff/non-integrated 物流 |
| 创建面单任务 | `v2.logistics.create_shipping_document` | 需已有 tracking number 后才能创建 |
| 查询面单任务 | `v2.logistics.get_shipping_document_result` | 状态为 `READY` 后可下载 |
| 下载面单 | `v2.logistics.download_shipping_document` | 下载 shipping document |

#### 映射建议

| 本地字段 | Shopee 字段候选 |
|---|---|
| `platform_order_id` | `order_sn` |
| `platform_order_no` | `order_sn` |
| `posting_number` | `package_number`，无包裹号时用 `order_sn` |
| `platform_status` | `order_status` |
| `payment_at` | `pay_time` |
| `platform_created_at` | `create_time` |
| `shipping_deadline_at` | `ship_by_date` / `days_to_ship` 计算 |
| `buyer_selected_logistics` | `shipping_carrier` / `logistics_channel_id` |
| `shipment_tracking_number` | `tracking_number` |
| `sku` | `item_sku` / `model_sku` |
| `platform_product_name` | `item_name` / `model_name` |
| `quantity` | `model_quantity_purchased` |
| `unit_price` | `model_discounted_price` |
| `currency` | `currency` |

#### 关键风险

- Shopee 有拆包裹和 `package_number` 场景，本地唯一键应优先 `shop_id + order_sn + package_number`。
- 面单流程是异步任务：创建、轮询、下载三步，不能直接假设一次请求返回 PDF。
- `refresh_token` 一次性使用，刷新时必须事务性更新加密凭据，避免并发同步把新 token 覆盖回旧 token。

---

### 4.3 TikTok Shop Open API

#### 官方资料

- TikTok Shop Partner Center：<https://partner.tiktokshop.com/>
- Partner Center Open API 文档入口：<https://partner.tiktokshop.com/docv2>
- 本次可公开访问页面为前端渲染文档，部分 API 详情需要登录开发者后台或具体 doc page 才能稳定查看。

#### 鉴权与配置

TikTok Shop Open API 通常需要应用级 `app_key/app_secret`、卖家授权 code 换取 access token，并对业务请求做签名。实施前需在 Partner Center 复核当前区域的签名串规则、token 过期时间、授权回调 URL 配置。

建议 `credentials`：

```json
{
  "app_key": "",
  "app_secret": "",
  "shop_cipher": "",
  "access_token": "",
  "refresh_token": ""
}
```

建议 `settings`：

```json
{
  "base_url": "https://open-api.tiktokglobalshop.com",
  "region": "GLOBAL",
  "pull_order_statuses": ["AWAITING_SHIPMENT", "AWAITING_COLLECTION", "IN_TRANSIT"]
}
```

#### 第一阶段接口清单

以下为第一阶段应在 TikTok Shop Open API 中确认和接入的接口族。具体路径、版本号和参数名需以 Partner Center 当前应用权限下的 API reference 为准：

| 项目动作 | TikTok Shop API 族 | 待复核重点 |
|---|---|---|
| 授权换 token | Authorization / Token API | code 换 token、refresh token、店铺标识字段 |
| 店铺校验 | Seller / Shop API | `shop_id` / `shop_cipher` 语义和跨区域差异 |
| 搜索订单 | Order API Search Orders | 时间筛选、状态筛选、分页 cursor |
| 订单详情 | Order API Get Order Detail | SKU、包裹、收件国家、金额、发货截止时间 |
| 包裹/履约 | Fulfillment / Package API | `package_id`、拆包、发货方式 |
| 发货回传 | Fulfillment Shipping API | 自发货 tracking number / carrier 回传 |
| 面单 | Fulfillment Shipping Document / Label API | 是否异步生成，返回 PDF 还是 URL |
| 状态回查 | Order / Fulfillment API | 取消、已发货、妥投状态字段 |

#### 映射建议

| 本地字段 | TikTok Shop 字段候选 |
|---|---|
| `platform_order_id` | `order_id` |
| `platform_order_no` | `order_id` 或平台展示订单号 |
| `posting_number` | `package_id` / `fulfillment_id` |
| `platform_status` | `order_status` / `fulfillment_status` |
| `payment_at` | `paid_time` |
| `platform_created_at` | `create_time` |
| `shipping_deadline_at` | `shipping_due_time` / `dispatch_by_time` |
| `buyer_selected_logistics` | `shipping_provider` / `delivery_option` |
| `shipment_tracking_number` | `tracking_number` |
| `sku` | seller SKU 字段，需复核 `seller_sku` / `sku_id` |
| `platform_product_name` | product/title 字段 |
| `quantity` | line item quantity |
| `unit_price` | sale/original price amount |
| `currency` | currency |

#### 关键风险

- TikTok Shop 的店铺标识常见有 `shop_id` 与 `shop_cipher` 两套概念，接口参数可能要求 `shop_cipher`。
- 不同国家/区域开放的物流和面单能力不完全一致，必须按目标店铺站点验证。
- 订单、包裹、面单经常分属不同 API group，不能只接 Order API 就认为履约闭环完成。

---

### 4.4 AliExpress Open Platform

#### 官方资料

- AliExpress Developers：<https://developers.aliexpress.com/>
- 阿里开放平台 API 文档页示例：<https://open.alitrip.com/docs/api.htm>

AliExpress 开放平台文档在公开网络下可访问性不稳定，部分页面会按账号/地区跳转或返回空内容。实施前必须使用实际开发者账号在官方后台复核应用权限、API 方法名和参数。

#### 鉴权与配置

AliExpress 属于阿里开放平台体系，通常使用 `app_key/app_secret`、授权 code 换 session/access token，并通过 Top API 签名调用。建议先按 OAuth/Top API 模式建模。

建议 `credentials`：

```json
{
  "app_key": "",
  "app_secret": "",
  "access_token": "",
  "refresh_token": "",
  "seller_id": ""
}
```

建议 `settings`：

```json
{
  "base_url": "https://api-sg.aliexpress.com/sync",
  "region": "GLOBAL",
  "pull_order_statuses": ["PLACE_ORDER_SUCCESS", "WAIT_SELLER_SEND_GOODS"]
}
```

#### 第一阶段接口清单

需在官方后台复核以下 API 方法名和权限：

| 项目动作 | AliExpress API 候选 | 用途 |
|---|---|---|
| 授权换 token | OAuth / System token API | 保存 seller token |
| 拉订单列表 | `aliexpress.trade.redefining.findorderlistsimplequery` 或 solution order list API | 按状态/时间查询订单 |
| 拉订单详情 | `aliexpress.trade.redefining.findorderbyid` / `aliexpress.solution.order.get` | 商品、金额、收件信息、物流要求 |
| 发货回传 | `aliexpress.logistics.redefining.sellershipmentfortop` / solution fulfill API | 回传物流单号和承运商 |
| 物流方案 | logistics service/list API | 查询可用物流服务 |
| 面单/打印 | logistics print info / getprintinfo API | 获取线上发货面单或打印信息 |
| 状态回查 | order detail/list API | 同步取消、完成、发货状态 |

#### 映射建议

| 本地字段 | AliExpress 字段候选 |
|---|---|
| `platform_order_id` | `order_id` |
| `platform_order_no` | `order_id` |
| `posting_number` | `logistics_no` / `tracking_no` / `order_id` |
| `platform_status` | `order_status` |
| `payment_at` | `gmt_pay_time` / `pay_time` |
| `platform_created_at` | `gmt_create` |
| `shipping_deadline_at` | `send_goods_time` / seller shipment deadline |
| `buyer_selected_logistics` | logistics service name/code |
| `shipment_tracking_number` | `logistics_no` / `tracking_no` |
| `sku` | `sku_code` / `product_sku` |
| `platform_product_name` | product name |
| `quantity` | product count |
| `unit_price` | product price |
| `currency` | currency code |

#### 关键风险

- AliExpress 老接口、solution 接口、物流重定义接口并存，方法名要以当前应用权限为准。
- 跨境线上发货和卖家自发货是不同流程，是否能拿平台面单取决于店铺物流方案。
- 订单详情可能需要额外权限才能返回完整买家地址。

---

### 4.5 Lazada Open Platform

#### 官方资料

- Lazada Open Platform：<https://open.lazada.com/>
- Getting Started：<https://open.lazada.com/apps/doc/doc?nodeId=10534&docId=108130>
- API Reference：<https://open.lazada.com/doc/api.htm>

Lazada 文档页面会通过官方后端动态拉取内容，公开无登录请求可能返回空内容。实施前需登录 Lazada Open Platform，用目标应用查看 API Reference。

#### 鉴权与配置

Lazada 也属于阿里开放平台体系，通常使用 `app_key/app_secret`、授权 code、access token，并按 API path + 参数签名调用。不同站点有不同 API gateway。

建议 `credentials`：

```json
{
  "app_key": "",
  "app_secret": "",
  "seller_id": "",
  "access_token": "",
  "refresh_token": ""
}
```

建议 `settings`：

```json
{
  "base_url": "https://api.lazada.com/rest",
  "region": "SG",
  "pull_order_statuses": ["pending", "ready_to_ship", "packed"]
}
```

#### 第一阶段接口清单

| 项目动作 | Lazada API 候选 | 用途 |
|---|---|---|
| 授权换 token | Auth token API | code 换 access token / refresh token |
| 刷新 token | Auth refresh API | token 续期 |
| 拉订单列表 | `GetOrders` | 按时间、状态分页查询订单 |
| 拉订单商品 | `GetOrderItems` | SKU、数量、价格、包裹状态 |
| 拉单个订单 | `GetOrder` | 补订单头字段 |
| 发货/RTS | `SetStatusToReadyToShip` | 设置 ready to ship，获取/绑定 package 信息 |
| 面单 | `GetDocument` | 获取 shipping label / invoice 等文档 |
| 包裹/物流 | Shipment Provider / Package 相关 API | 获取物流商、包裹、跟踪号 |

#### 映射建议

| 本地字段 | Lazada 字段候选 |
|---|---|
| `platform_order_id` | `order_id` |
| `platform_order_no` | `order_number` |
| `posting_number` | `package_id` / `order_item_id` / tracking code |
| `platform_status` | order status / order item status |
| `payment_at` | `created_at` / `updated_at` / payment time |
| `platform_created_at` | `created_at` |
| `shipping_deadline_at` | `ship_before` / SLA 字段 |
| `buyer_selected_logistics` | shipment provider / shipping type |
| `shipment_tracking_number` | `tracking_code` |
| `sku` | `sku` / `seller_sku` |
| `platform_product_name` | item name |
| `quantity` | order item quantity，通常一 item 一行 |
| `unit_price` | item price / paid price |
| `currency` | currency |

#### 关键风险

- Lazada 很多履约状态在 order item/package 维度，不一定是 order 维度；本地 `posting_number` 需要按 `package_id` 或 `order_item_id` 设计。
- `SetStatusToReadyToShip` 参数与站点物流模式相关，实施前要用真实店铺订单跑通。
- `GetDocument` 返回格式和可下载文档类型需按站点确认。

---

## 5. 跨平台字段映射总表

| 本地字段 | Amazon | Shopee | TikTok Shop | AliExpress | Lazada |
|---|---|---|---|---|---|
| `platform_order_id` | `AmazonOrderId` | `order_sn` | `order_id` | `order_id` | `order_id` |
| `platform_order_no` | `AmazonOrderId` | `order_sn` | 展示订单号/`order_id` | `order_id` | `order_number` |
| `posting_number` | order/shipment/package key | `package_number` | `package_id` | logistics/tracking/order id | `package_id` / `order_item_id` |
| `platform_status` | `OrderStatus` | `order_status` | order/fulfillment status | `order_status` | order/item status |
| `payment_at` | `PurchaseDate` | `pay_time` | `paid_time` | pay time | created/payment time |
| `shipping_deadline_at` | `LatestShipDate` | `ship_by_date` | dispatch due time | shipment deadline | `ship_before` / SLA |
| `buyer_selected_logistics` | `ShipServiceLevel` | shipping carrier/channel | delivery option/provider | logistics service | shipment provider |
| `shipment_tracking_number` | shipment tracking | `tracking_number` | `tracking_number` | logistics/tracking no | `tracking_code` |
| `sku` | `SellerSKU` | `item_sku` / `model_sku` | seller sku | sku code | `seller_sku` |
| `quantity` | `QuantityOrdered` | purchased quantity | line item quantity | product count | item quantity |
| `unit_price` | `ItemPrice.Amount` | discounted price | sale price | product price | paid/item price |
| `currency` | `CurrencyCode` | `currency` | `currency` | currency code | currency |

---

## 6. 凭据与店铺字段建议

### 6.1 `PlatformAccount.account_id` 建议

| 平台 | 建议存储值 |
|---|---|
| Amazon | seller id 或 `seller_id:marketplace_group` |
| Shopee | `shop_id` |
| TikTok Shop | `shop_cipher` 优先；如业务展示需要另存 `shop_id` |
| AliExpress | seller/member id |
| Lazada | seller id 或 seller short code |

### 6.2 `auth_type`

| 平台 | 值 |
|---|---|
| Amazon | `oauth2_sigv4` |
| Shopee | `oauth2_hmac` |
| TikTok Shop | `oauth2_hmac` |
| AliExpress | `oauth2_top` |
| Lazada | `oauth2_top` |

### 6.3 Token 并发刷新要求

所有 OAuth 类平台都应避免多个同步任务并发刷新同一店铺 token。建议后续实现时：

- 复用当前按账号同步锁。
- token 过期前主动刷新。
- 刷新成功后立即更新 `encrypted_credentials`。
- 对一次性 refresh token 的平台，刷新和保存必须在同一临界区完成。

---

## 7. 实施顺序建议

| 顺序 | 平台 | 原因 |
|---|---|---|
| 1 | Shopee | 官方结构化文档可公开访问，接口链路清晰，东南亚履约场景接近 Lazada/TikTok |
| 2 | Lazada | 与 Shopee 同区域运营场景，但需要登录后台复核文档 |
| 3 | TikTok Shop | 订单增长快，但文档和区域差异需更多验证 |
| 4 | AliExpress | 阿里开放平台接口体系复杂，需先确定走 solution 还是 redefining API |
| 5 | Amazon | SP-API 权限、RDT、SigV4、限流复杂，审核和安全要求最高 |

如果业务优先级已经确定，可按业务优先级调整；技术风险最低路线是先 Shopee。

---

## 8. 实施前待确认问题

| 问题 | 影响 |
|---|---|
| 五个平台是否都有现成开发者账号和已审核应用？ | 决定能否获取真实 token 和 API 权限 |
| 每个平台目标站点/国家是什么？ | 影响 endpoint、物流、面单、币种、税务字段 |
| 首版是否必须拉买家完整地址？ | Amazon/TikTok/AliExpress 可能涉及 PII 权限 |
| 是否统一只处理 FBS/卖家自发货订单？ | 决定是否跳过平台仓订单，仅标记 `is_overseas_warehouse` |
| 是否必须下载平台面单，还是允许自有面单/手工物流？ | 决定 fulfillment API 复杂度 |
| 是否要接 Webhook？ | 决定是否新增外网回调、签名校验、事件去重 |
| 每个平台店铺的默认发货方式是什么？ | Shopee/Lazada/TikTok 发货参数高度依赖物流方式 |
| 现有商品 SKU 是否已覆盖这些平台店铺？ | 影响 `product_shop_mappings` 导入计划 |

---

## 9. 资料可信度标记

| 平台 | 当前资料可信度 | 说明 |
|---|---|---|
| Amazon | 高 | 官方 Markdown/llms 索引可直接访问，已确认 endpoint、鉴权、Orders、Merchant Fulfillment、RDT、限流 |
| Shopee | 高 | 官方结构化 API 元数据可访问，已确认订单、物流、面单、Public token API |
| TikTok Shop | 中 | 官方入口可访问，但 API 详情前端渲染/后台权限依赖较强，需登录复核 |
| AliExpress | 中低 | 官方入口存在，但公开页面不稳定，需开发者后台确认方法名和权限 |
| Lazada | 中 | 官方入口存在，但 API detail 后端无会话返回空内容，需登录后台确认 |

---

## 10. 下一步建议

1. 先收集五个平台开发者后台信息：应用 key、回调 URL、目标站点、已开通 API 权限。
2. 为每个平台创建一张“真实接口确认表”，用开发者后台逐项确认 API path、请求参数、返回字段和限流。
3. 先做 Shopee adapter 设计评审，因为它的官方资料最完整，能沉淀 OAuth/HMAC/异步面单的通用模式。
4. 在编码前补一份平台字段样例 JSON，至少每个平台各 1 个待发货订单、1 个已发货订单、1 个取消订单。
