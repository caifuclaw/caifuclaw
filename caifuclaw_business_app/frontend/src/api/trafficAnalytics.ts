/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { get, post } from './http'

export type TrafficMetricKey = 'impressions' | 'clicks' | 'add_to_cart' | 'orders'
export type TrafficRateMetricKey = 'ctr' | 'cvr'
export type TrafficRankingMetricKey = TrafficMetricKey | TrafficRateMetricKey
export type TrafficSortOrder = 'asc' | 'desc'
export type TrafficCoverage = 'full' | 'partial' | 'unavailable'
export type TrafficComparisonDimension = 'sku' | 'category'
export type TrafficComparisonSort =
  | 'delta_abs'
  | 'rate_desc'
  | 'rate_asc'
  | 'current_desc'
  | 'current_asc'
  | 'previous_desc'
  | 'previous_asc'
  | 'delta_desc'
  | 'delta_asc'
export type TrafficComparisonChangeDirection = 'all' | 'up' | 'down' | 'flat'

export interface TrafficCapability {
  label: string
  scope: string
  grain: string
  metrics: string[]
  note: string
}

export interface TrafficSyncRun {
  id: number
  platform_account_id: number
  platform: string
  account_id: string
  shop_name: string
  status: 'pending' | 'running' | 'success' | 'partial_success' | 'failed' | 'timed_out' | string
  date_from: string
  date_to: string
  rows_written: number
  error_message: string
  triggered_by: string
  started_at?: string | null
  finished_at?: string | null
  created_at?: string | null
}

export interface TrafficAccount {
  id: number
  platform: string
  account_id: string
  display_name: string
  enabled: boolean
  authorization_status: string
  capability: TrafficCapability
  latest_run?: TrafficSyncRun | null
  latest_metric_at?: string | null
  latest_period_start?: string | null
  latest_period_end?: string | null
  data_freshness: 'fresh' | 'stale' | 'missing'
}

export interface TrafficMetricRow {
  rank?: number
  platform: string
  platform_account_id: number
  account_id: string
  shop_name: string
  source: string
  grain: string
  stat_date?: string
  region: string
  entity_type?: string
  entity_id?: string
  sku?: string
  product_name?: string
  impressions: number | null
  clicks: number | null
  add_to_cart: number | null
  orders: number | null
  buyers: number | null
  units_sold: number | null
  negative_reviews: number | null
  revenue: number | null
  sales_share?: number | null
  currency: string
  ctr: number | null
  cart_rate: number | null
  cvr: number | null
  cart_conversion: number | null
  period_start: string
  period_end: string
  synced_at: string
  coverage: Record<string, TrafficCoverage>
}

export interface TrafficCategoryRow extends TrafficMetricRow {
  platform_category_id: string
  platform_category_name: string
  platform_category_path: string
  categorized: boolean
  sku_count: number
}

export interface TrafficComparisonRow {
  rank: number
  platform: string
  platform_account_id: number
  account_id: string
  shop_name: string
  source: string
  region: string
  grain?: string
  entity_type?: string
  entity_id?: string
  sku?: string
  product_name?: string
  platform_category_id?: string
  platform_category_name?: string
  platform_category_path?: string
  current_impressions: number | null
  previous_impressions: number | null
  delta_impressions: number | null
  delta_rate_impressions: number | null
  current_clicks: number | null
  previous_clicks: number | null
  delta_clicks: number | null
  delta_rate_clicks: number | null
  current_add_to_cart: number | null
  previous_add_to_cart: number | null
  delta_add_to_cart: number | null
  delta_rate_add_to_cart: number | null
  current_orders: number | null
  previous_orders: number | null
  delta_orders: number | null
  delta_rate_orders: number | null
}

export type TrafficSkuFocusReason =
  | 'high_impressions_no_orders'
  | 'high_clicks_missing_impressions_or_cart'
  | 'high_cart_missing_orders'
  | 'high_orders_missing_impressions'

export interface TrafficSkuFocusRow {
  rank: number
  platform: string
  platform_account_id: number
  account_id: string
  shop_name: string
  source: string
  region: string
  grain: string
  entity_type: string
  entity_id: string
  sku: string
  product_name: string
  impressions: number | null
  clicks: number | null
  add_to_cart: number | null
  orders: number | null
  impressions_rank: number | null
  clicks_rank: number | null
  add_to_cart_rank: number | null
  orders_rank: number | null
  focus_reasons: TrafficSkuFocusReason[]
}

export interface TrafficFilters {
  date_from: string
  date_to: string
  platform?: string[]
  platform_account_id?: number[]
  source?: string
  region?: string[]
}

export interface TrafficPeriodFallback {
  platform: string
  platform_account_id: number
  scope: 'current' | 'previous'
  requested_date_from: string
  requested_date_to: string
  actual_date_from: string
  actual_date_to: string
}

export interface TrafficRequestOptions {
  signal?: AbortSignal
}

function trafficQueryParams(params: object) {
  const searchParams = new URLSearchParams()
  Object.entries(params as Record<string, unknown>).forEach(([key, value]) => {
    if (value == null || value === '') return
    const values = Array.isArray(value) ? value : [value]
    values.forEach((item) => searchParams.append(key, String(item)))
  })
  return searchParams
}

export interface TrafficMetricResponse {
  items: TrafficMetricRow[]
  date_from: string
  date_to: string
  metric?: string
  sort_order?: TrafficSortOrder
  rank_scope?: 'global'
  fallback_periods?: TrafficPeriodFallback[]
}

export interface TrafficCategoryResponse {
  items: TrafficCategoryRow[]
  date_from: string
  date_to: string
  total_sku_count: number
  categorized_sku_count: number
  uncategorized_sku_count: number
  classification_rate: number
  fallback_periods?: TrafficPeriodFallback[]
}

export interface TrafficComparisonResponse {
  items: TrafficComparisonRow[]
  metric: string
  dimension: TrafficComparisonDimension
  sort_by: TrafficComparisonSort
  date_from: string
  date_to: string
  previous_date_from: string
  previous_date_to: string
  fallback_periods?: TrafficPeriodFallback[]
}

export interface TrafficSkuFocusResponse {
  items: TrafficSkuFocusRow[]
  top_n: number
  supported_metrics: TrafficMetricKey[]
  date_from: string
  date_to: string
  fallback_periods?: TrafficPeriodFallback[]
}

export interface TrafficCategorySkuComparisonFilters {
  date_from: string
  date_to: string
  metric: TrafficMetricKey
  sort_by?: TrafficComparisonSort
  keyword?: string
  change_direction?: TrafficComparisonChangeDirection
  limit?: number
  platform: string
  platform_account_id: number
  source: string
  grain: string
  region: string
  platform_category_id: string
}

export interface TrafficCategorySkuFocusFilters {
  date_from: string
  date_to: string
  top_n?: number
  keyword?: string
  platform: string
  platform_account_id: number
  source: string
  grain: string
  region: string
  platform_category_id: string
}

export function listTrafficAccounts(config?: { background?: boolean; silent?: boolean }) {
  return get<{ items: TrafficAccount[] }>('/api/v1/traffic-analytics/accounts', config)
}

export function fetchTrafficSummary(params: TrafficFilters, options?: TrafficRequestOptions) {
  return get<TrafficMetricResponse>('/api/v1/traffic-analytics/summary', {
    params: trafficQueryParams(params),
    background: true,
    signal: options?.signal
  })
}

export function fetchDailyNegativeReviews(params: TrafficFilters, options?: TrafficRequestOptions) {
  return get<TrafficMetricResponse>('/api/v1/traffic-analytics/negative-reviews', {
    params: trafficQueryParams(params),
    background: true,
    signal: options?.signal
  })
}

export function fetchTrafficCategories(params: TrafficFilters, options?: TrafficRequestOptions) {
  return get<TrafficCategoryResponse>('/api/v1/traffic-analytics/categories', {
    params: trafficQueryParams(params),
    background: true,
    signal: options?.signal
  })
}

export function fetchTrafficRankings(
  params: TrafficFilters & { metric: TrafficRankingMetricKey; sort_order?: TrafficSortOrder; limit?: number },
  options?: TrafficRequestOptions
) {
  return get<TrafficMetricResponse>('/api/v1/traffic-analytics/rankings', {
    params: trafficQueryParams(params),
    background: true,
    signal: options?.signal
  })
}

export function fetchTrafficComparison(
  params: TrafficFilters & {
    metric: TrafficMetricKey
    dimension?: TrafficComparisonDimension
    sort_by?: TrafficComparisonSort
    limit?: number
  },
  options?: TrafficRequestOptions
) {
  return get<TrafficComparisonResponse>('/api/v1/traffic-analytics/comparison', {
    params: trafficQueryParams(params),
    background: true,
    signal: options?.signal
  })
}

export function fetchTrafficCategorySkuComparison(
  params: TrafficCategorySkuComparisonFilters,
  options?: TrafficRequestOptions
) {
  return get<TrafficComparisonResponse>('/api/v1/traffic-analytics/comparison/category-skus', {
    params: trafficQueryParams(params),
    background: true,
    silent: true,
    signal: options?.signal
  })
}

export function fetchTrafficCategorySkuFocusAnalysis(
  params: TrafficCategorySkuFocusFilters,
  options?: TrafficRequestOptions
) {
  return get<TrafficSkuFocusResponse>('/api/v1/traffic-analytics/analysis/category-skus', {
    params: trafficQueryParams(params),
    background: true,
    silent: true,
    signal: options?.signal
  })
}

export function syncTrafficAnalytics(payload: {
  platform_account_ids?: number[]
  date_from: string
  date_to: string
}) {
  return post<{ items: TrafficSyncRun[] }>('/api/v1/traffic-analytics/sync', payload)
}
