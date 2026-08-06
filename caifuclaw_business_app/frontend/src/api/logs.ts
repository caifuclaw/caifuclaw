import { get } from './http'

export interface SyncApiLogSummaryDto {
  log_date?: string | null
  last_created_at?: string | null
  platform?: string | null
  account_id?: string | null
  operation?: string | null
  url?: string | null
  total: number
  success_count?: number
  failed_count?: number
  avg_duration_ms?: number | null
  max_duration_ms?: number | null
}

export interface SyncApiLogDto {
  id: number
  created_at?: string | null
  platform?: string | null
  account_id?: string | null
  operation?: string | null
  status?: string | null
  response_status?: number | null
  duration_ms?: number | null
  method?: string | null
  url?: string | null
  error_message?: string | null
  request_body?: unknown
  response_body?: unknown
  extra?: unknown
}

export interface SyncApiLogQueryParams {
  platform?: string
  account_id?: string
  operation?: string
  status?: string
  keyword?: string
  date_from?: string
  date_to?: string
  page?: number
  page_size?: number
  limit?: number
}

export interface SyncApiLogListResponse {
  items: SyncApiLogDto[]
  total: number
  page?: number
  page_size?: number
}

export interface SyncApiLogSummaryListResponse {
  items: SyncApiLogSummaryDto[]
  total: number
  page?: number
  page_size?: number
}

export function listSyncApiLogSummaries(params: SyncApiLogQueryParams) {
  return get<SyncApiLogSummaryListResponse>('/api/v1/sync-api-logs-summary', { params, background: true })
}

export function listSyncApiLogs(params: SyncApiLogQueryParams) {
  return get<SyncApiLogListResponse>('/api/v1/sync-api-logs', { params, background: true })
}

export function getSyncApiLog(id: number) {
  return get<SyncApiLogDto>(`/api/v1/sync-api-logs/${id}`)
}
