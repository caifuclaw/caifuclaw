/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { del, get, post, put } from './http'

export interface LogisticsMatchRuleDto {
  id: number
  name: string
  platform: string
  priority: number
  enabled: boolean
  shop_names: string[]
  is_overseas_warehouse: boolean | null
  country_codes: string[]
  logistics_channel: string
  remark: string
  created_by?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface LogisticsMatchRuleListParams {
  name?: string
  platform?: string
  enabled?: boolean
  page?: number
  page_size?: number
}

export interface LogisticsMatchRuleListResponse {
  items: LogisticsMatchRuleDto[]
  total: number
  page: number
  page_size: number
}

export interface LogisticsChannelOptionDto {
  value: string
  label: string
  carrier_code: string
  carrier_name: string
  account_name: string
}

export interface LogisticsShopOptionDto {
  value: string
  label: string
}

export interface LogisticsMatchRulePayload {
  name: string
  platform: string
  priority: number
  enabled: boolean
  shop_names: string[]
  is_overseas_warehouse: boolean | null
  country_codes: string[]
  logistics_channel: string
  remark: string
}

export interface LogisticsRematchPayload {
  order_ids?: number[]
  include_manual?: boolean
  include_shipped?: boolean
}

export interface LogisticsRematchResponse {
  matched: number
  unmatched: number
  skipped: number
  total: number
  message: string
}

export function listLogisticsRules(params: LogisticsMatchRuleListParams) {
  return get<LogisticsMatchRuleListResponse>('/api/v1/logistics-rules', { params, background: true })
}

export function listLogisticsChannelOptions() {
  return get<LogisticsChannelOptionDto[]>('/api/v1/logistics-rules/channel-options', { background: true })
}

export function listLogisticsShopOptions(platform: string) {
  return get<LogisticsShopOptionDto[]>('/api/v1/logistics-rules/shop-options', { params: { platform }, background: true })
}

export function createLogisticsRule(payload: LogisticsMatchRulePayload) {
  return post<LogisticsMatchRuleDto>('/api/v1/logistics-rules', payload)
}

export function updateLogisticsRule(id: number, payload: LogisticsMatchRulePayload) {
  return put<LogisticsMatchRuleDto>(`/api/v1/logistics-rules/${id}`, payload)
}

export function toggleLogisticsRule(id: number) {
  return post<LogisticsMatchRuleDto>(`/api/v1/logistics-rules/${id}/toggle-enabled`)
}

export function deleteLogisticsRule(id: number) {
  return del<{ status: string }>(`/api/v1/logistics-rules/${id}`)
}

export function rematchLogisticsRules(payload: LogisticsRematchPayload = {}) {
  return post<LogisticsRematchResponse>('/api/v1/logistics-rules/rematch', payload, { timeout: 300000 })
}
