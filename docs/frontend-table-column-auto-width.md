# 前端表格自适应与用户列配置方案

本文档记录当前公共表格 `DataTable` 的列宽自适应、用户列配置和列表页接入规则，供后续页面复用。

## 适用范围

适用于基于 `caifuclaw_business_app/frontend/src/components/DataTable.tsx` 的 Ant Design 表格页面。

已接入页面使用同一套样板配置：

```tsx
<DataTable
  rowKey="id"
  tableConfig={ORDER_TABLE_CONFIG}
  dataSource={orders}
  columns={columns}
  onVisibleColumnsChange={setVisibleExportColumns}
  pagination={pagination}
/>
```

## 2026-05-30 变更摘要

本轮围绕订单列表完成了表格自适应、用户列配置、导出一致性和 Excel 导出格式的样板落地：

- 公共 `DataTable` 支持 `tableConfig`、`tableKey`、用户列偏好加载和保存。
- 订单列表接入 `orders.list`，主识别列为 `platform_order_no`，即“订单编号”。
- 表格默认使用 `adaptive-left`：列宽按当前页表头和内容自适应，整体居左，右侧保留剩余空间。
- 普通列自动宽度上限为 `450px`；订单列表会通过列级 `minWidth` / `maxWidth` 控制平台、单号、日期等常见列的默认宽度。
- 用户拖拽某列后，该列生成用户级固定宽度，并通过 `PUT /api/v1/table-preferences/{table_key}` 持久化。
- “恢复默认值”会删除当前用户当前 `tableKey` 的个人配置，并立即回到页面系统默认自适应列宽。
- “订单编号”必选、不可隐藏，默认固定左侧。
- “操作”列固定右侧，不进入列设置弹窗；设置按钮放在“操作”列表头内。
- 右侧固定列的左边界保留拖拽热区，用于调整其左侧数据列宽度。
- 列设置弹窗采用左侧可选属性、右侧已选属性的布局；支持搜索、显示隐藏、已选列拖拽排序和恢复默认。
- 表格最后一行和分页之间的间距已压缩，分页区域更紧凑。
- 订单列表导出字段跟随当前界面可见列，顺序和内容口径保持一致；`actions` 操作列不导出。
- 业务表格数据导出统一为 `.xlsx` Excel 文件；订单列表和出库扫描记录已经从 CSV 改为真实 xlsx。
- PDF、面单等文件型导出保持原文件格式，不纳入业务表格 `.xlsx` 规则。

## 2026-05-31 批量接入摘要

本轮按订单列表样板继续接入业务列表，其余设置和日志页面暂不修改。

已接入页面：

| 页面 | `tableKey` | 主识别列 |
|---|---|---|
| 订单汇总表 | `order-summary.list` | 订单编号 `order_no` |
| 采购单管理 | `purchase-orders.list` | 采购单号 `purchase_no` |
| 采购明细 | `purchase-details.list` | 采购单号 `purchase_no` |
| 扫码出库今日记录 | `scan-outbound.today-records` | 货运单号 `tracking_number` |
| 扫码记录 | `outbound-scans.list` | 货运单号 `tracking_number` |
| 产品库存 | `inventory.list` | 产品编号 `product_code` |

本轮约束：

- 默认列顺序必须与页面当前 `columns` 定义保持一致，不为了接入配置重排默认列。
- 如果主识别列当前不是第一列，允许配置为必选但不默认固定左侧，例如订单汇总表和扫码相关页面使用 `fixed: false` 保持原顺序。
- 操作列使用 `key: 'actions'`，固定右侧，不进入列设置弹窗，也不进入导出。
- 其余设置和日志页面暂不接入，包括店铺、商品、用户、系统设置、汇率、定时任务日志、同步接口日志等页面。
- 订单汇总、扫码记录、产品库存导出字段跟随当前界面可见列，顺序和内容口径保持一致。
- 后端导出在前端未传 `columns` 时，回退读取当前用户对应 `tableKey` 的偏好配置；没有个人配置时使用页面系统默认列。

## 配置优先级

表格配置分三层：

```text
用户个人配置 > 页面系统默认配置 > 全局表格默认规则
```

- 页面通过 `tableConfig` 声明系统默认列方案。
- 用户修改列宽、显示状态或排序后，配置按 `user_id + table_key` 保存。
- 系统新增列时，如果用户配置里没有该列，会按页面默认配置追加。
- 点击恢复默认值时，删除当前用户当前 `tableKey` 的个人配置，不影响其他用户和其他页面。

## 后端持久化

用户表格配置保存到 `user_table_preferences`。

唯一约束：

```text
user_id + table_key
```

接口：

| 方法 | 接口 | 说明 |
|---|---|---|
| GET | `/api/v1/table-preferences/{table_key}` | 获取当前用户该表格配置 |
| PUT | `/api/v1/table-preferences/{table_key}` | 保存或更新当前用户配置 |
| DELETE | `/api/v1/table-preferences/{table_key}` | 恢复默认，删除用户配置 |

接口只处理当前登录用户，前端不传 `user_id`。

## 页面默认配置

页面配置示例：

```ts
const orderTableConfig = {
  tableKey: 'orders.list',
  primaryColumnKey: 'platform_order_no',
  widthMode: 'adaptive-left',
  columns: [
    { key: 'platform_order_no', title: '订单编号', required: true, fixed: 'left', minWidth: 132, maxWidth: 180 },
    { key: 'platform', title: '平台', minWidth: 88, maxWidth: 140 },
    { key: 'actions', title: '操作', fixed: 'right', protectedWidth: 90, settingsHidden: true }
  ]
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `tableKey` | 页面表格唯一标识 |
| `primaryColumnKey` | 页面主识别列，必选且默认固定左侧 |
| `required` | 必选列，配置弹窗中不可取消 |
| `minWidth` / `maxWidth` | 默认自适应宽度边界 |
| `protectedWidth` | 操作列、按钮列等保护宽度 |
| `settingsHidden` | 系统保护列，不出现在列设置弹窗中 |

## 列宽规则

默认模式为 `adaptive-left`，按内容自适应并居左，剩余空间留在右侧。

基础公式：

```text
columnWidth = min(maxWidth, max(headerTextWidth, maxCellTextWidth) + extraWidth)
```

当前实现规则：

- 普通文本列在自适应模式下使用较紧凑的 `extraWidth = 24px`。
- 交互内容列使用 `extraWidth = 32px`，避免按钮、标签、控件被压得太紧。
- 全局自动列宽上限为 `450px`。
- 页面列配置中的 `maxWidth` 在自适应模式下生效。
- 超过列宽的内容显示省略号。
- 鼠标悬停普通单元格显示完整文本。
- 空数据时保留上一轮记忆列宽，避免搜索无结果后表头明显跳动。
- 刷新、分页、搜索、筛选、排序后重新计算未固定列的自适应宽度。

## 用户拖拽列宽

用户拖拽某列后：

- 该列生成用户级 `width` 配置。
- 后续该列按用户固定宽度显示。
- 其他未拖拽列继续使用自适应居左规则。
- 拖拽结果通过 `PUT /api/v1/table-preferences/{table_key}` 持久化。
- 用户拖拽宽度最大仍允许到 `450px`，不受页面默认 `maxWidth` 限制。
- 右侧固定列使用左边界作为拖拽点；在订单列表中拖拽“订单导入时间”和“操作”之间的分割线，会调整左侧数据列宽度。

## 列设置弹窗

入口位于表格最后一列表头中，当前订单列表为“操作”表头内的设置图标。

弹窗内容：

- 左侧：可选属性列表，支持搜索。
- 右侧：已选属性列表，支持拖拽排序。
- 必选列置灰，不能取消。
- 底部按钮：恢复默认值、取消、确定。

系统保护列不显示在弹窗中，例如：

- `actions` 操作列不出现在可选/已选列表。
- 操作列默认固定右侧。
- 操作列仍参与表格渲染和保护宽度计算。

## 必选列规则

每类单据必须保留主识别列，不允许隐藏。

| 页面 | 必选列 |
|---|---|
| 订单列表 | 订单编号 |
| 采购单列表 | 采购单号 |
| 出库/扫描相关 | 出库单号或扫描单号，接入时确认 |
| 商品列表 | 商品编码或 SKU，接入时确认 |

建议统一使用 `primaryColumnKey` 声明。

## 订单列表当前接入

订单列表使用：

```text
tableKey = orders.list
primaryColumnKey = platform_order_no
```

当前默认规则：

- 订单编号必选，默认固定左侧。
- 操作列固定右侧，不进入列设置弹窗。
- 操作列左边界保留拖拽热区，用于调整其左侧数据列宽度。
- 日期类列宽约束为 `150px - 170px`。
- 平台列默认宽度放宽到 `88px - 140px`，恢复默认后也应能容纳常见平台名。
- 单号类列按内容宽度计算，并设置合理 `maxWidth`。
- 分页区域上间距为 `8px`，比 Ant Design 默认 `16px` 更紧凑。

## 订单列表导出

订单列表导出使用 `GET /api/v1/orders/export`，统一返回 `.xlsx` Excel 文件，字段口径跟随当前界面显示列：

- 前端通过 `onVisibleColumnsChange` 收集当前可见数据列，并按界面顺序传入 `columns=key1,key2,...`。
- 后端按 `columns` 参数输出表头和内容；未传 `columns` 时，回退读取当前用户 `orders.list` 偏好配置。
- `actions` 操作列属于系统保护列，只在界面渲染，不进入导出。
- 平台、金额、时间、空值等显示格式按订单列表渲染口径处理。
- 若存在勾选订单，优先导出勾选订单；否则按当前筛选条件导出。
- 后续业务表格数据导出默认遵循 `.xlsx` 格式；PDF、面单等文件型导出保持原文件格式。

已同步的业务导出：

| 页面 / 功能 | 接口 | 当前格式 | 说明 |
|---|---|---|---|
| 订单列表 | `GET /api/v1/orders/export` | `.xlsx` | 字段、顺序、内容跟随当前界面可见列 |
| 订单汇总表 | `GET /api/v1/order-summary/export` | `.xlsx` | 字段、顺序、内容跟随当前界面可见列 |
| 出库扫描记录 | `GET /api/v1/outbound-scans/export` | `.xlsx` | 字段、顺序、内容跟随当前界面可见列 |
| 产品库存 | `GET /api/v1/inventory/export` | `.xlsx` | 字段、顺序、内容跟随当前界面可见列 |
| 商品、采购相关导出 | 既有导出接口 | `.xlsx` | 已符合统一格式，未接入可见列跟随时需按本规则补齐 |

## 维护文件

公共表格组件：

```text
caifuclaw_business_app/frontend/src/components/DataTable.tsx
```

前端偏好 API：

```text
caifuclaw_business_app/frontend/src/api/tablePreferences.ts
```

订单列表接入：

```text
caifuclaw_business_app/frontend/src/pages/Orders/Orders.tsx
```

本轮列表接入：

```text
caifuclaw_business_app/frontend/src/pages/OrderSummary/OrderSummary.tsx
caifuclaw_business_app/frontend/src/pages/PurchaseOrders/PurchaseOrders.tsx
caifuclaw_business_app/frontend/src/pages/PurchaseDetails/PurchaseDetails.tsx
caifuclaw_business_app/frontend/src/pages/ScanOutbound/ScanOutbound.tsx
caifuclaw_business_app/frontend/src/pages/OutboundScans/OutboundScans.tsx
caifuclaw_business_app/frontend/src/pages/Inventory/Inventory.tsx
```

全局样式：

```text
caifuclaw_business_app/frontend/src/styles/global.less
```

后端模型和接口：

```text
caifuclaw_business_app/app/models.py
caifuclaw_business_app/app/schemas.py
caifuclaw_business_app/app/main.py
```

## 验证方式

前端目录：

```bash
cd caifuclaw_business_app/frontend
```

类型检查：

```bash
npm run typecheck
```

生产构建：

```bash
npm run build
```

本地运行：

```bash
npm run dev
```

访问：

```text
http://127.0.0.1:5173/orders?status=pending
```

## 已知取舍

- 当前列宽按当前页数据计算，不跨分页拉取全部数据。
- 复杂自定义渲染内容只提取可识别文本；纯图标或复杂组件不会贡献文本宽度。
- `title` 悬停使用浏览器原生提示，轻量但样式不可控。
- 第一阶段只接入订单列表，稳定后再批量接入采购单、商品、库存等页面。
