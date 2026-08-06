import { get, post, put } from './http'
import type { AxiosRequestConfig } from 'axios'

export interface PlatformOptionDto {
  platform: string
  display_name: string
  enabled?: boolean
}

export interface ShopDto {
  id?: number
  platform: string
  shop_id: string
  account_id?: string
  display_name: string
  enabled: boolean
  authorization_status: string
  token_valid?: boolean | null
  token_message?: string
  last_authorized_at?: string | null
  authorization_expires_at?: string | null
  created_by?: string | null
  created_at?: string | null
  settings?: Record<string, unknown>
}

export interface ShopListParams {
  display_name?: string
  platform?: string
  enabled?: boolean
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

export interface ShopCreatePayload {
  platform: string
  display_name: string
  enabled: boolean
  credential_type: 'oauth2' | 'api_key' | 'oauth2_hmac' | 'oauth2_top' | 'oauth2_sigv4' | 'oauth2_admin_api' | 'oauth2_client_credentials' | 'hmac_openapi' | 'oauth2_client_credentials_graphql'
  credentials: Record<string, string>
  settings: Record<string, unknown>
  authorization_expires_at: string | null
}

export interface ShopUpdatePayload {
  display_name: string
  enabled: boolean
  settings: Record<string, unknown>
}

export interface OAuthStartResponse {
  state?: string
  authorize_url?: string
}

export interface OAuthCompleteResponse {
  status: 'success' | 'pending' | 'failed' | string
  message?: string
  shop?: ShopDto
}

export function listPlatforms(config?: AxiosRequestConfig) {
  return get<PlatformOptionDto[]>('/api/v1/platforms', config)
}

export function listShops(params: ShopListParams, config?: AxiosRequestConfig) {
  return get<ShopDto[]>('/api/v1/shops', { ...config, params })
}

export function getShopCredentials(platform: string, shopId: string) {
  return get<Record<string, string>>(
    `/api/v1/shops/${platform}/${shopId}/credentials`,
    { silent: true }
  )
}

export function createShop(payload: ShopCreatePayload) {
  return post<ShopDto>('/api/v1/shops', payload)
}

export function updateShop(platform: string, shopId: string, payload: ShopUpdatePayload) {
  return put<ShopDto>(`/api/v1/shops/${platform}/${shopId}`, payload)
}

export function updateShopCredentials(
  platform: string,
  shopId: string,
  payload: { credentials: Record<string, string>; authorization_expires_at: string | null }
) {
  return post<{ message: string }>(`/api/v1/shops/${platform}/${shopId}/credentials`, payload)
}

export function reauthorizeShop(
  platform: string,
  shopId: string,
  payload: { credentials: Record<string, string>; authorization_expires_at: string | null }
) {
  return post<ShopDto>(`/api/v1/shops/${platform}/${shopId}/reauthorize`, payload)
}

export function toggleShopEnabled(platform: string, shopId: string) {
  return post<{ enabled: boolean }>(`/api/v1/shops/${platform}/${shopId}/toggle-enabled`)
}

export function startShopOAuth(
  platform: string,
  shopId: string,
  body: { credentials: Record<string, string> }
) {
  return post<OAuthStartResponse>(`/api/v1/shops/${platform}/${shopId}/oauth/start`, body)
}

export function completeShopOAuth(
  platform: string,
  shopId: string,
  body: { state: string; code: string | null }
) {
  return post<OAuthCompleteResponse>(`/api/v1/shops/${platform}/${shopId}/oauth/complete`, body)
}
