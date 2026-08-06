/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { get, post } from './http'

export interface OutboundScanRecordDto {
  id: number
  tracking_number: string
  raw_input: string
  order_id: number | null
  platform: string
  shop_name: string
  platform_order_no: string
  posting_number: string
  order_status: string
  platform_status: string
  result: string
  message: string
  scanned_by: string
  scanned_at: string
  created_at: string
}

export interface OutboundScanRequest {
  tracking_number: string
  raw_input?: string
}

export interface OutboundScanResponse {
  result: string
  message: string
  record: OutboundScanRecordDto
}

export interface OutboundScanListResponse {
  items: OutboundScanRecordDto[]
  total: number
  page: number
  page_size: number
}

export interface OutboundScanStatsResponse {
  success: number
  duplicate: number
  not_found: number
  invalid: number
  error: number
  total: number
  last_scanned_at: string | null
}

export interface OutboundScanListParams {
  number?: string
  platform?: string
  shop_name?: string
  result?: string
  scanned_by?: string
  scanned_start?: string
  scanned_end?: string
  today_only?: boolean
  order_outbound?: boolean
  columns?: string
  page?: number
  page_size?: number
}

export function createOutboundScan(payload: OutboundScanRequest) {
  return post<OutboundScanResponse>('/api/v1/outbound-scans', payload, { silent: true })
}

export function listOutboundScans(params: OutboundScanListParams) {
  return get<OutboundScanListResponse>('/api/v1/outbound-scans', { params, background: true })
}

export function fetchOutboundScanStats() {
  return get<OutboundScanStatsResponse>('/api/v1/outbound-scans/stats', { background: true })
}
