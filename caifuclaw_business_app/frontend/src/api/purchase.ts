/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { get, post, put, del } from './http'
import http from './http'

// ===================== Order Summary =====================
export interface OrderSummaryDto {
  order_id: number
  item_id: number
  picking_at: string | null
  platform: string
  shop_name: string
  platform_created_at: string | null
  order_no: string
  status: string
  platform_status: string
  platform_order_no: string
  platform_order_id: string
  posting_number: string
  country_code: string
  country_name_cn: string
  customer_name: string
  sku: string
  platform_product_name: string
  quantity: number
  unit_price: string
  currency: string
  buyer_selected_logistics: string
  shipping_deadline_at: string | null
  shipment_tracking_number: string
  tracking_number: string
  dispatch_deadline_at: string | null
  product_name: string
  customer_confirm: string
  warning: string
  purchase_no?: string
  shipping_time?: string | null
}

export interface OrderSummaryResponse {
  items: OrderSummaryDto[]
  total: number
  page: number
  page_size: number
  has_more?: boolean
}

export interface OrderSummaryParams {
  status?: string
  platform?: string
  shop_ids?: string
  number?: string
  product_keyword?: string
  warning?: string
  payment_start?: string
  payment_end?: string
  picking_start?: string
  picking_end?: string
  old_customer_only?: boolean
  page?: number
  page_size?: number
  lazy?: boolean
}

const orderSummaryRequests = new Map<string, Promise<OrderSummaryResponse>>()

function orderSummaryRequestKey(params: OrderSummaryParams): string {
  return JSON.stringify(
    Object.entries(params)
      .filter(([, value]) => value !== undefined && value !== null && value !== '')
      .sort(([left], [right]) => left.localeCompare(right))
  )
}

export function listOrderSummary(params: OrderSummaryParams) {
  const key = orderSummaryRequestKey(params)
  const pending = orderSummaryRequests.get(key)
  if (pending) return pending
  const request = get<OrderSummaryResponse>('/api/v1/order-summary', { params, background: true })
    .finally(() => orderSummaryRequests.delete(key))
  orderSummaryRequests.set(key, request)
  return request
}

export async function exportOrderSummaryBlob(params: OrderSummaryParams & { item_ids?: string; columns?: string }): Promise<Blob> {
  const res = await http.get<Blob>('/api/v1/order-summary/export', {
    params,
    responseType: 'blob'
  })
  return res.data
}

// ===================== Purchase Orders =====================
export interface PurchaseOrderDto {
  id: number
  purchase_no: string
  purchase_date: string | null
  source_count: number
  item_count: number
  total_required_qty: number
  created_by: string | null
  remark: string
  created_at: string | null
  updated_at: string | null
}

export interface PurchaseOrderItemDto {
  id: number
  product_id: number | null
  product_name: string
  required_qty: number
  buyer_user_id: number | null
  buyer: string
  total_cost_record: number | null
  purchase_cost: number | null
  purchase_channel: string
  purchase_qty: number
  remark: string
  created_at: string | null
  updated_at: string | null
}

export interface PurchaseOrderSourceDto {
  id: number
  order_id: number
  order_item_id: number
  product_id: number | null
  product_name: string
  quantity: number
  created_at: string | null
}

export interface PurchaseOrderDetailDto extends PurchaseOrderDto {
  lock_acquired: boolean
  lock_owner: string
  lock_expires_at: string | null
  items: PurchaseOrderItemDto[]
  sources: PurchaseOrderSourceDto[]
}

export interface PurchaseOrderListResponse {
  items: PurchaseOrderDto[]
  total: number
  page: number
  page_size: number
}

export interface PurchaseOrderListParams {
  purchase_no?: string
  page?: number
  page_size?: number
}

export interface PurchaseOrderEditLockDto {
  purchase_order_id: number
  lock_acquired: boolean
  lock_owner: string
  lock_expires_at: string | null
  message: string
}

export function listPurchaseOrders(params: PurchaseOrderListParams) {
  return get<PurchaseOrderListResponse>('/api/v1/purchase-orders', { params, background: true })
}

export async function exportPurchaseOrdersBlob(
  params: PurchaseOrderListParams & { purchase_start?: string; purchase_end?: string }
): Promise<Blob> {
  const res = await http.get<Blob>('/api/v1/purchase-orders/export', {
    params,
    responseType: 'blob'
  })
  return res.data
}

export function getPurchaseOrderDetail(id: number) {
  return get<PurchaseOrderDetailDto>(`/api/v1/purchase-orders/${id}`)
}

export async function exportPurchaseOrderBlob(id: number): Promise<Blob> {
  const res = await http.get<Blob>(`/api/v1/purchase-orders/${id}/export`, {
    responseType: 'blob'
  })
  return res.data
}

export function generatePurchaseOrder(orderItemIds: number[], remark = '') {
  return post<PurchaseOrderDetailDto>('/api/v1/purchase-orders/generate', {
    order_item_ids: orderItemIds,
    remark
  })
}

export function acquirePurchaseOrderLock(id: number, force = false) {
  return post<PurchaseOrderEditLockDto>(`/api/v1/purchase-orders/${id}/lock`, { force })
}

export function releasePurchaseOrderLock(id: number) {
  return del<void>(`/api/v1/purchase-orders/${id}/lock`, { silent: true })
}

export interface PurchaseOrderUpdatePayload {
  purchase_date: string | null
  remark: string
}

export function updatePurchaseOrder(id: number, payload: PurchaseOrderUpdatePayload) {
  return put<PurchaseOrderDto>(`/api/v1/purchase-orders/${id}`, payload)
}

export interface PurchaseOrderItemUpdatePayload {
  buyer_user_id: number | null
  buyer?: string
  total_cost_record: number | null
  purchase_cost: number | null
  purchase_channel: string
  purchase_qty: number
  remark: string
}

export function updatePurchaseOrderItem(
  purchaseOrderId: number,
  itemId: number,
  payload: PurchaseOrderItemUpdatePayload
) {
  return put<PurchaseOrderItemDto>(
    `/api/v1/purchase-orders/${purchaseOrderId}/items/${itemId}`,
    payload
  )
}

export function deletePurchaseOrder(id: number) {
  return del<void>(`/api/v1/purchase-orders/${id}`)
}

// ===================== Purchase Details =====================
export interface PurchaseDetailDto {
  purchase_order_id: number
  item_id: number
  purchase_no: string
  purchase_date: string | null
  picking_date: string | null
  product_name: string
  daily_order_qty: number
  stock_qty: number
  pending_purchase_qty: number
  buyer_user_id: number | null
  buyer: string
  total_cost_record: number | null
  purchase_cost: number | null
  purchase_channel: string
  purchase_qty: number
  remark: string
}

export interface PurchaseDetailListResponse {
  items: PurchaseDetailDto[]
  total: number
  page: number
  page_size: number
}

export interface PurchaseDetailListParams {
  purchase_no?: string
  product_name?: string
  buyer?: string
  picking_start?: string
  picking_end?: string
  page?: number
  page_size?: number
}

export function listPurchaseDetails(params: PurchaseDetailListParams) {
  return get<PurchaseDetailListResponse>('/api/v1/purchase-details', { params, background: true })
}

export async function exportPurchaseDetailsBlob(params: PurchaseDetailListParams): Promise<Blob> {
  const res = await http.get<Blob>('/api/v1/purchase-details/export', {
    params,
    responseType: 'blob'
  })
  return res.data
}

// ===================== Common =====================
export interface UserOptionDto {
  id: number
  username: string
  display_name: string
  role_code?: string
}

export function listUserOptions() {
  return get<UserOptionDto[]>('/api/v1/user-options', { background: true })
}
