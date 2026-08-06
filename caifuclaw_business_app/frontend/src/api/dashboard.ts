import { get, put } from './http'

export interface DashboardDateParams {
  date_from?: string
  date_to?: string
  compare_from?: string
  compare_to?: string
  shop_ids?: number[]
}

export interface DashboardRequestOptions {
  signal?: AbortSignal
}

function dashboardQueryParams(params?: DashboardDateParams) {
  const searchParams = new URLSearchParams()
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value == null || value === '') return
    const values = Array.isArray(value) ? value : [value]
    values.forEach((item) => searchParams.append(key, String(item)))
  })
  return searchParams
}

/** /api/v1/orders/status-counts 返回的状态计数键 */
export interface OrderStatusCounts {
  all?: number
  pending: number
  waiting_print: number
  waiting_purchase: number
  picking: number
  shipped: number
  awaiting_pickup: number
  delivered: number
  voided: number
  platform_status_counts?: Record<string, number>
}

/** 获取订单各状态计数（Dashboard 待办、Orders 顶部 Tab 都用） */
export function fetchOrderStatusCounts() {
  return get<OrderStatusCounts>('/api/v1/orders/status-counts', { silent: true, background: true })
}

/** /api/v1/sync-api-logs-summary 返回的单行汇总 */
export interface ApiRequestLogSummary {
  log_date: string
  last_created_at: string
  platform: string
  account_id: string
  operation: string
  url: string
  total: number
  success_count: number
  failed_count: number
  avg_duration_ms: number | null
  max_duration_ms: number | null
}

export interface ApiRequestLogSummaryParams {
  platform?: string
  account_id?: string
  operation?: string
  status?: string
  date_from?: string
  date_to?: string
  limit?: number
}

export function fetchSyncApiLogsSummary(params?: ApiRequestLogSummaryParams) {
  return get<ApiRequestLogSummary[]>('/api/v1/sync-api-logs-summary', {
    params,
    silent: true
  })
}

export interface DashboardMonthlySales {
  month: string
  orders: number
  avg_daily_orders: number
  /** Amount converted to CNY. Kept as raw_amount for API compatibility. */
  raw_amount: number
  /** Average order value converted to CNY. */
  raw_aov: number
  expected_receipt: number
  pending: number
  picking: number
  shipped: number
  delivered: number
  voided: number
  voided_rate: number
  blank_currency_orders: number
}

export interface DashboardDailySales {
  date: string
  orders: number
  /** Amount converted to CNY. Kept as raw_amount for API compatibility. */
  raw_amount: number
  expected_receipt: number
  pending: number
  voided: number
}

export interface DashboardShopSales {
  platform: string
  shop: string
  orders: number
  /** Amount converted to CNY. Kept as raw_amount for API compatibility. */
  raw_amount: number
  /** Average order value converted to CNY. */
  raw_aov: number
  expected_receipt: number
  receipt_rate_pct: number
  voided: number
  blank_currency_orders: number
}

export interface DashboardMtdComparison {
  current_label: string
  previous_label: string
  current_orders: number
  previous_orders: number
  order_growth_pct: number
  current_amount: number
  previous_amount: number
  amount_growth_pct: number
  current_receipt: number
  previous_receipt: number
  receipt_growth_pct: number
  current_pending: number
  current_voided: number
  previous_pending: number
  previous_voided: number
}

export interface DashboardRiskBucket {
  key: string
  label: string
  orders: number
  /** Amount converted to CNY. Kept as raw_amount for API compatibility. */
  raw_amount: number
  earliest_deadline?: string | null
  latest_deadline?: string | null
}

export interface DashboardRiskShop {
  platform: string
  shop: string
  pending_orders: number
  pending_units: number
  overdue_orders: number
  due_24h: number
  due_48h: number
  due_later: number
  /** Amount converted to CNY. Kept as raw_amount for API compatibility. */
  raw_amount: number
  min_hours_to_deadline?: number | null
  earliest_deadline?: string | null
}

export interface DashboardRiskSku {
  sku: string
  product_name: string
  pending_orders: number
  pending_units: number
  shops: number
  overdue_orders: number
  earliest_deadline?: string | null
}

export interface DashboardHotSku {
  sku: string
  product_name: string
  units_all: number
  orders_all: number
  units_7d: number
  units_prev_7d: number
  units_7d_delta: number
  shops: number
  platforms: string
  pending_orders: number
}

export interface DashboardAnalytics {
  generated_at: string
  total_orders: number
  first_order_date?: string | null
  last_order_date?: string | null
  blank_currency_orders: number
  monthly_sales: DashboardMonthlySales[]
  daily_sales: DashboardDailySales[]
  comparison_daily_sales: DashboardDailySales[]
  shop_sales: DashboardShopSales[]
  current_label: string
  comparison_label: string
  mtd_comparison: DashboardMtdComparison
  risk_buckets: DashboardRiskBucket[]
  risk_shops: DashboardRiskShop[]
  risk_skus: DashboardRiskSku[]
  hot_skus: DashboardHotSku[]
}

export interface DashboardOverview {
  generated_at: string
  total_orders: number
  first_order_date?: string | null
  last_order_date?: string | null
  blank_currency_orders: number
  mtd_comparison: DashboardMtdComparison
}

export interface DashboardSales {
  monthly_sales: DashboardMonthlySales[]
  daily_sales: DashboardDailySales[]
  comparison_daily_sales: DashboardDailySales[]
  shop_sales: DashboardShopSales[]
  current_label: string
  comparison_label: string
}

export interface DashboardRisk {
  risk_buckets: DashboardRiskBucket[]
  risk_shops: DashboardRiskShop[]
}

export interface DashboardSkus {
  risk_skus: DashboardRiskSku[]
  hot_skus: DashboardHotSku[]
  current_label: string
  previous_label: string
}

export interface OperationsDailyOrderPoint {
  date: string
  orders: number
  /** Revenue converted to CNY using the exchange rate closest to the payment date. */
  revenue_cny: number
}

export interface OperationsDailyShop {
  platform: string
  account_id: string
  shop: string
  days: OperationsDailyOrderPoint[]
  total_orders: number
  /** Revenue converted to CNY using the exchange rate closest to the payment date. */
  total_revenue_cny: number
}

export interface OperationsFulfillmentRisk {
  platform: string
  overdue_orders: number
  due_soon_orders: number
}

export interface OperationsCustomerComplaint {
  platform: string
  shop: string
  count: number
  latest_issue_at?: string | null
}

export interface OperationsDailyReport {
  generated_at: string
  date_from: string
  date_to: string
  shop_daily_orders: OperationsDailyShop[]
  fulfillment_risk: OperationsFulfillmentRisk[]
  customer_complaints: OperationsCustomerComplaint[]
  customer_complaints_data_status: 'pending_source' | 'negative_reviews'
}

export interface DashboardPlatformSetting {
  platform: string
  platform_name: string
  receipt_rate_pct: number
  fulfillment_days: number
}

export interface DashboardSettings {
  items: DashboardPlatformSetting[]
  can_manage: boolean
}

export interface DashboardSettingsUpdate extends DashboardSettings {
  backfilled: number
}

export function fetchDashboardAnalytics(params?: DashboardDateParams, options?: DashboardRequestOptions) {
  return get<DashboardAnalytics>('/api/v1/dashboard/analytics', {
    params: dashboardQueryParams(params),
    silent: true,
    signal: options?.signal
  })
}

export function fetchDashboardOverview(params?: DashboardDateParams, options?: DashboardRequestOptions) {
  return get<DashboardOverview>('/api/v1/dashboard/overview', {
    params: dashboardQueryParams(params),
    silent: true,
    background: true,
    signal: options?.signal
  })
}

export function fetchDashboardSales(params?: DashboardDateParams, options?: DashboardRequestOptions) {
  return get<DashboardSales>('/api/v1/dashboard/sales', {
    params: dashboardQueryParams(params),
    silent: true,
    background: true,
    signal: options?.signal
  })
}

export function fetchDashboardRisk(params?: DashboardDateParams, options?: DashboardRequestOptions) {
  return get<DashboardRisk>('/api/v1/dashboard/risk', {
    params: dashboardQueryParams(params),
    silent: true,
    background: true,
    signal: options?.signal
  })
}

export interface OperationsDailyReportParams {
  report_date?: string
}

export function fetchOperationsDailyReport(params?: OperationsDailyReportParams, options?: DashboardRequestOptions) {
  return get<OperationsDailyReport>('/api/v1/dashboard/operations', {
    params: { days: 7, report_date: params?.report_date },
    silent: true,
    background: true,
    signal: options?.signal
  })
}

export function fetchDashboardSkus(params?: DashboardDateParams, options?: DashboardRequestOptions) {
  return get<DashboardSkus>('/api/v1/dashboard/skus', {
    params: dashboardQueryParams(params),
    silent: true,
    background: true,
    signal: options?.signal
  })
}

export function fetchDashboardSettings() {
  return get<DashboardSettings>('/api/v1/dashboard/settings', { silent: true })
}

export function updateDashboardSettings(items: DashboardPlatformSetting[]) {
  return put<DashboardSettingsUpdate>('/api/v1/dashboard/settings', { items })
}
