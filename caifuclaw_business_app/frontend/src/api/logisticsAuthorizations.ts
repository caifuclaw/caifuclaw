/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { get, post, put } from './http'
import type { AxiosRequestConfig } from 'axios'

export interface LogisticsAuthorizationDto {
  id: number
  carrier_code: string
  carrier_name: string
  account_name: string
  enabled: boolean
  authorization_status: string
  token_valid?: boolean | null
  token_message?: string | null
  credential_type: string
  credentials_masked: Record<string, unknown>
  config_json: Record<string, unknown>
  settings_json: Record<string, unknown>
  last_authorized_at?: string | null
  authorization_expires_at?: string | null
  credentials_version: string
  created_by?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface LogisticsAuthorizationListParams {
  carrier_name?: string
  carrier_code?: string
  enabled?: boolean
}

export interface LogisticsAuthorizationUpdatePayload {
  carrier_code: string
  carrier_name: string
  account_name: string
  enabled: boolean
  credential_type: string
  credentials: Record<string, string>
  config_json: Record<string, unknown>
  settings_json: Record<string, unknown>
  authorization_expires_at?: string | null
}

export interface LogisticsAuthorizationVerifyResponse {
  authorization_status: string
  token_valid: boolean
  token_message: string
  missing_fields: string[]
}

export function listLogisticsAuthorizations(params: LogisticsAuthorizationListParams, config?: AxiosRequestConfig) {
  return get<LogisticsAuthorizationDto[]>('/api/v1/logistics-authorizations', { ...config, params })
}

export function getLogisticsAuthorization(id: number, config?: AxiosRequestConfig) {
  return get<LogisticsAuthorizationDto>(`/api/v1/logistics-authorizations/${id}`, config)
}

export function getLogisticsAuthorizationCredentials(id: number) {
  return get<Record<string, string>>(`/api/v1/logistics-authorizations/${id}/credentials`, { silent: true })
}

export function updateLogisticsAuthorization(id: number, payload: LogisticsAuthorizationUpdatePayload) {
  return put<LogisticsAuthorizationDto>(`/api/v1/logistics-authorizations/${id}`, payload)
}

export function verifyLogisticsAuthorization(id: number) {
  return post<LogisticsAuthorizationVerifyResponse>(`/api/v1/logistics-authorizations/${id}/verify`)
}

export function toggleLogisticsAuthorization(id: number) {
  return post<LogisticsAuthorizationDto>(`/api/v1/logistics-authorizations/${id}/toggle-enabled`)
}
