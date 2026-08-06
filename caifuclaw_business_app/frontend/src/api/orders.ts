/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { get, post } from './http'

/** 后端 OrderDto（与 schemas.py 对齐） */
export interface OrderDto {
  id: number
  platform: string
  account_id: string
  shop_id: string
  shop_name: string
  site: string
  platform_order_id: string
  platform_order_no: string
  posting_number: string
  transaction_id: string
  customer_id: string
  customer_name: string
  status: string
  local_status: string
  platform_status: string
  fulfillment_type: string
  is_overseas_warehouse: boolean
  bsi_order_no: string
  bsi_submitted_at: string | null
  is_joom_offline_shipping: boolean
  logistics_label_exempt: boolean
  platform_handover_deadline: string | null
  country_name_cn: string
  country_code: string
  buyer_selected_logistics: string
  order_amount: string
  currency: string
  payment_at: string | null
  shipment_tracking_number: string
  tracking_number: string
  logistics_channel: string
  logistics_match_rule_id?: number | null
  logistics_match_rule_name: string
  logistics_match_status: string
  logistics_match_reason: string
  logistics_matched_at?: string | null
  picking_at: string | null
  marked_shipped_at: string | null
  label_printed_at: string | null
  handover_at: string | null
  shipped_at: string | null
  shipping_deadline_at: string | null
  remaining_shipping_seconds: number | null
  remaining_shipping_time: string
  has_label: boolean
  label_path: string
  created_at: string
  updated_at: string
  risk_deadline_at: string | null
  risk_bucket: string
  risk_handled: boolean
  risk_handled_at: string | null
  risk_handled_by: string
  risk_handling_note: string
}

export interface OrderListResponse {
  items: OrderDto[]
  total: number
  page: number
  page_size: number
  search_summary?: OrderSearchSummary | null
}

export interface OrderSearchSummary {
  submitted: number
  unique: number
  matched: number
  unmatched_numbers: string[]
}

export interface OrderListParams {
  status?: string
  risk?: 'all' | 'unhandled' | 'handled' | 'overdue' | 'due_24'
  shop?: string
  shop_ids?: string
  platform?: string
  number?: string
  numbers?: string[]
  product_keyword?: string
  payment_start?: string
  payment_end?: string
  page?: number
  page_size?: number
}

export interface OrderDetailItemDto {
  id: number
  sku: string
  platform_product_name: string
  quantity: number
  unit_price: string
  currency?: string
  product_code: string
  product_name: string
  product_cost?: number | null
  product_weight?: number | null
}

export interface OrderOperationLogDto {
  id: number
  operation_type: string
  operation_attribute: string
  description: string
  operator: string
  source: string
  result: 'success' | 'warning' | 'failed' | 'unchanged' | string
  changes: OrderOperationLogChangeDto[]
  task_run_id?: number | null
  sync_job_log_id?: number | null
  operated_at: string
  created_at: string
}

export interface OrderOperationLogChangeDto {
  field: string
  label: string
  before: string
  after: string
}

export interface OrderOperationLogListResponse {
  items: OrderOperationLogDto[]
  has_more: boolean
  next_before_id?: number | null
}

export interface OrderOperationLogListParams {
  before_id?: number
  page_size?: number
  operation_type?: string
  source?: string
}

export interface OrderDetailDto extends OrderDto {
  internal_order_no: string
  items: OrderDetailItemDto[]
  operation_logs: OrderOperationLogDto[]
}

export interface OrderBatchResponse {
  updated: number
  message: string
  purchase_order_id?: number | null
  purchase_no?: string | null
}

export interface OrderRiskHandlingOptions {
  handled: boolean
  note?: string
}

export interface ToPrintingOptions {
  allowMissingTracking?: boolean
}

export interface PrintLabelResponse {
  filename: string
  content_type: string
  pdf_base64: string
  cached: number
  fetched: number
  failed: number
  skipped: number
  printed: number
  total: number
}

export interface WanbangTestItem {
  order_id: number
  order_no: string
  success: boolean
  account_name: string
  process_code: string
  tracking_number: string
  parcel_status: string
  reference_id: string
  label_ready: boolean
  label_attempts: number
  label_bytes: number
  label_sha256: string
  label_path: string
  error: string
}

export interface WanbangTestResponse {
  total: number
  succeeded: number
  failed: number
  message: string
  items: WanbangTestItem[]
}

export interface ManualSyncRequest {
  platform?: string
  account_id?: string
  full_refresh?: boolean
}

export function listOrders(params: OrderListParams) {
  if (params.numbers?.length) {
    return post<OrderListResponse, OrderListParams>('/api/v1/orders/search', params, {
      background: true,
      retry: 2
    })
  }
  return get<OrderListResponse>('/api/v1/orders', { params, background: true })
}

export function fetchOrderDetail(id: number) {
  return get<OrderDetailDto>(`/api/v1/orders/${id}`)
}

export function listOrderOperationLogs(id: number, params: OrderOperationLogListParams = {}) {
  return get<OrderOperationLogListResponse>(`/api/v1/orders/${id}/operation-logs`, { params, background: true })
}

export function batchToPicking(orderIds: number[]) {
  return post<OrderBatchResponse>('/api/v1/orders/batch/to-picking', { order_ids: orderIds })
}

export function batchToPrinting(orderIds: number[], options: ToPrintingOptions = {}) {
  return post<OrderBatchResponse>('/api/v1/orders/batch/to-printing', {
    order_ids: orderIds,
    allow_missing_tracking: Boolean(options.allowMissingTracking)
  })
}

export function batchConfirmPrinted(orderIds: number[]) {
  return post<OrderBatchResponse>('/api/v1/orders/batch/confirm-printed', { order_ids: orderIds })
}

export function batchMarkShipped(orderIds: number[]) {
  return post<OrderBatchResponse>('/api/v1/orders/batch/mark-shipped', { order_ids: orderIds })
}

export function batchUpdateRiskHandling(orderIds: number[], options: OrderRiskHandlingOptions) {
  return post<OrderBatchResponse>('/api/v1/orders/batch/risk-handling', {
    order_ids: orderIds,
    handled: options.handled,
    note: options.note || ''
  })
}

export function batchPrintLabel(orderIds: number[]) {
  return post<PrintLabelResponse>('/api/v1/orders/batch/print-label', { order_ids: orderIds }, { timeout: 300000 })
}

export function batchPrintChineseLabel(orderIds: number[]) {
  return post<PrintLabelResponse>('/api/v1/orders/batch/print-chinese-label', { order_ids: orderIds }, { timeout: 300000 })
}

export function batchWanbangTest(orderIds: number[]) {
  return post<WanbangTestResponse>('/api/v1/orders/batch/wanbang-test', { order_ids: orderIds }, { timeout: 300000 })
}

export function batchSetLogisticsChannel(orderIds: number[], logisticsChannel: string) {
  return post<OrderBatchResponse>('/api/v1/orders/batch/logistics-channel', {
    order_ids: orderIds,
    logistics_channel: logisticsChannel
  })
}

export function manualSync(payload: ManualSyncRequest) {
  return post<{ status?: string; detail?: string }>('/api/v1/sync/manual', payload)
}
