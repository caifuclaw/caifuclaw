/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { get, post, put, del } from './http'
import http from './http'
import axios from 'axios'
import type { AxiosRequestConfig } from 'axios'

function filenameFromContentDisposition(value?: string): string {
  if (!value) return ''
  const encoded = value.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  if (encoded) {
    try {
      return decodeURIComponent(encoded)
    } catch {
      return encoded
    }
  }
  return value.match(/filename="?([^";]+)"?/i)?.[1] || ''
}

/* ============== 平台/邮件服务商字典 ============== */
export interface EmailProviderDto {
  code: string
  name: string
  smtp_host?: string
  smtp_port?: number
  use_ssl?: boolean
  sender_hint?: string
  auth_code_hint?: string
}

/* ============== 汇率 ============== */
export interface ExchangeRateDto {
  id: number
  rate_date: string
  currency_code: string
  currency_name?: string
  rate: string
  source_updated_at?: string | null
  synced_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface ExchangeRateListResponse {
  items: ExchangeRateDto[]
  total: number
  page: number
  page_size: number
  currencies: string[]
}

export interface ExchangeRateQueryParams {
  rate_date?: string
  currency_code?: string
  page?: number
  page_size?: number
}

export interface ExchangeRateSyncResult {
  synced: number
  skipped: number
  failed: number
  message?: string
}

export interface ExchangeRateCurrencySettingDto {
  id: number
  currency_code: string
  currency_name?: string
  enabled: boolean
  created_at?: string | null
  updated_at?: string | null
}

export interface ExchangeRateCurrencySettingPayload {
  currency_code: string
  currency_name?: string
}

/* ============== 打印设置 ============== */
export interface ShippingDeadlineSettingDto {
  id: number
  platform: string
  platform_name?: string
  base_date_field: 'platform_created_at' | 'shipping_deadline_at' | 'payment_at'
  base_date_field_name?: string
  offset_days: number
  sort_order: number
  enabled: boolean
  created_at?: string | null
  updated_at?: string | null
}

export interface ShippingDeadlineSettingPayload {
  platform: string
  base_date_field: 'platform_created_at' | 'shipping_deadline_at' | 'payment_at'
  offset_days: number
  sort_order?: number
  enabled?: boolean
}

export interface ShippingDeadlineSettingsUpdateResponse {
  items: ShippingDeadlineSettingDto[]
  backfilled: number
}

export interface PrintSettingDto {
  id: number
  platform: string
  document_type: string
  document_type_name?: string
  printer_name: string
  page_orientation: 'auto' | 'portrait' | 'landscape'
  page_orientation_name?: string
  enabled: boolean
  remark?: string
  updated_at?: string
}

export interface PrintSettingPayload {
  platform: string
  document_type: string
  printer_name: string
  page_orientation: 'auto' | 'portrait' | 'landscape'
  enabled: boolean
  remark?: string
}

export interface PrinterDto {
  name: string
  display_name?: string
  system?: string
  device_uri?: string
  driver_name?: string
  port_name?: string
  status?: string
  is_default?: boolean
  online?: boolean | null
}

export interface PlatformSettingDto {
  id: number
  platform: string
  platform_name?: string
  enabled: boolean
  updated_at?: string | null
}

/* ============== 定时任务 ============== */
export interface ScheduledTaskSettings {
  schedule_mode?: 'interval' | 'cron'
  interval_minutes?: number
  retry_count?: number
  retry_interval_minutes?: number
  timeout_minutes?: number
  poll_interval_seconds?: number
  failure_email_enabled?: boolean
  failure_email_recipients?: string
}

export interface ScheduledTaskDto {
  id: number
  name: string
  task_type: string
  cron_expr: string
  enabled: boolean
  remark?: string
  last_run_at?: string | null
  last_status?: string | null
  last_message?: string | null
  settings?: ScheduledTaskSettings
  created_at?: string
  updated_at?: string
}

export interface ScheduledTaskPayload {
  name: string
  task_type: string
  cron_expr: string
  enabled: boolean
  remark?: string
  settings: ScheduledTaskSettings
}

export interface ScheduledTaskRunDto {
  id: number
  scheduled_task_id?: number | null
  task_type?: string
  trigger_mode?: string
  status?: string
  stats_json?: Record<string, unknown>
  pdf_export_platforms?: string[]
  attempt_no?: number
  max_retry_count?: number
  next_retry_at?: string | null
  started_at?: string | null
  ended_at?: string | null
  summary?: string
  email_sent?: boolean
  email_error?: string | null
}

export interface ScheduledTaskRunListResponse {
  items: ScheduledTaskRunDto[]
  total: number
  page?: number
  page_size?: number
}

export interface ScheduledTaskRunStepDto {
  id: number
  step_name: string
  status?: string
  message?: string
  started_at?: string | null
  ended_at?: string | null
}

export interface ScheduledTaskRunOrderDto {
  id: number
  order_id?: number | string
  platform_order_no?: string
  platform?: string
  document_type_name?: string
  status_before?: string
  status_after?: string
  pdf_generated?: boolean
  printer_name?: string
  print_job_name?: string
  print_submitted?: boolean
  needs_reprint?: boolean
  print_message?: string
  error_message?: string
  pdf_file_path?: string
  has_label_file?: boolean
  label_file_path?: string
  purchase_order_id?: number | string | null
}

export interface ScheduledTaskRunPlatformDto {
  run_id: number
  platform: string
  document_type_name?: string
  total_count: number
  pdf_count: number
  print_submitted_count: number
  failed_count: number
  reprintable_count: number
  order_nos: string[]
  printer_names: string[]
  print_job_names: string[]
  messages: string[]
  pdf_file_paths: string[]
  needs_reprint: boolean
  print_submitted: boolean
}

export interface ScheduledTaskRunPdfDownloadLinkDto {
  url: string
  filename: string
  expires_in_seconds: number
}

/* ============== 邮件 SMTP ============== */
export interface EmailNotificationRecipientsDto {
  wanbang_tracking_failure: string
  bsi_address_anomaly: string
}

export interface EmailSmtpDto {
  provider: string
  enabled: boolean
  smtp_host: string
  smtp_port: number
  use_ssl: boolean
  sender_email: string
  sender_name?: string
  notification_recipients: EmailNotificationRecipientsDto
  has_auth_code?: boolean
  last_test_at?: string
  last_test_status?: string
  last_test_message?: string
}

export interface EmailSmtpPayload {
  provider: string
  enabled: boolean
  smtp_host: string
  smtp_port: number
  use_ssl: boolean
  sender_email: string
  sender_name?: string
  notification_recipients: EmailNotificationRecipientsDto
  auth_code?: string | null
}

export interface WeComRobotSettingDto {
  has_webhook_url: boolean
  webhook_url_masked: string
  timeout_seconds: number
  max_retries: number
  rate_limit_per_minute: number
  default_mentioned_user_ids: number[]
  default_mentioned_list: string[]
  default_mentioned_mobile_list: string[]
  default_prompt: string
  purchase_order_notify_enabled: boolean
  updated_at?: string | null
}

export interface WeComRobotSettingPayload {
  webhook_url: string
  timeout_seconds: number
  max_retries: number
  rate_limit_per_minute: number
  default_mentioned_user_ids: number[]
  default_mentioned_list: string[]
  default_mentioned_mobile_list: string[]
  default_prompt: string
  purchase_order_notify_enabled: boolean
}

export interface WeComMentionUserOptionDto {
  id: number
  username: string
  display_name: string
  wecom_mobile: string
}

export interface WeComRobotTestResponse {
  status: string
  message: string
}

export interface TranslationProviderOptionDto {
  code: string
  name: string
}

export interface TranslationLanguageOptionDto {
  code: string
  label: string
}

export interface TranslationProviderSettingDto {
  provider: string
  provider_name: string
  enabled: boolean
  app_id: string
  has_secret_key: boolean
  secret_key_masked: string
  endpoint: string
  source_language: string
  timeout_seconds: number
  max_retries: number
  batch_size: number
  batch_chars: number
  provider_options: Record<string, any>
  last_test_at?: string | null
  last_test_status?: string
  last_test_message?: string
  updated_at?: string | null
}

export interface TranslationProviderSettingPayload {
  provider: string
  enabled: boolean
  app_id: string
  secret_key?: string | null
  endpoint: string
  source_language: string
  timeout_seconds: number
  max_retries: number
  batch_size: number
  batch_chars: number
  provider_options?: Record<string, any>
}

export interface TranslationProviderTestResponse {
  status: string
  message: string
  translated_text: string
}

/* ============== 平台字典 ============== */
export interface ModelEndpointDto {
  id: number
  name: string
  base_url: string
  api_key_masked: string
  enabled: boolean
  remark?: string
  created_at?: string | null
  updated_at?: string | null
}

export interface ModelEndpointPayload {
  name: string
  base_url: string
  api_key?: string | null
  enabled: boolean
  remark?: string
}

export interface ModelSettingDto {
  id: number
  name: string
  model: string
  endpoint_id?: number | null
  endpoint_name?: string
  endpoint_enabled?: boolean
  url: string
  is_default: boolean
  supports_vision: boolean
  enabled: boolean
  created_at?: string | null
  updated_at?: string | null
}

export interface ModelSettingPayload {
  name: string
  model: string
  endpoint_id?: number | null
  is_default: boolean
  supports_vision: boolean
  enabled: boolean
}

export interface ModelConnectionTestResponse {
  model_setting_id: number
  model_setting_name: string
  model: string
  endpoint_name: string
  upstream_url: string
  duration_ms: number
  message: string
}

export interface PlatformDictDto {
  platform: string
  label?: string
  display_name?: string
  enabled?: boolean
}

export function listPlatformsDict(config?: AxiosRequestConfig) {
  return get<PlatformDictDto[]>('/api/v1/platforms', config)
}

export function listPlatformSettings() {
  return get<PlatformSettingDto[]>('/api/v1/system-settings/platform-settings')
}

export function updatePlatformSetting(platform: string, payload: { enabled: boolean }) {
  return put<PlatformSettingDto>(`/api/v1/system-settings/platform-settings/${platform}`, payload)
}

/* ============== 汇率 API ============== */
export function listExchangeRates(params?: ExchangeRateQueryParams) {
  return get<ExchangeRateListResponse>('/api/v1/system-settings/exchange-rates', {
    params: params || {},
    background: true
  })
}

export function syncExchangeRates() {
  return post<ExchangeRateSyncResult>('/api/v1/system-settings/exchange-rates/sync')
}

export function listExchangeRateCurrencySettings() {
  return get<ExchangeRateCurrencySettingDto[]>('/api/v1/system-settings/exchange-rate-currency-settings')
}

export function updateExchangeRateCurrencySettings(currencies: ExchangeRateCurrencySettingPayload[]) {
  return put<ExchangeRateCurrencySettingDto[]>('/api/v1/system-settings/exchange-rate-currency-settings', {
    currencies
  })
}

/* ============== 打印设置 API ============== */
export function listShippingDeadlineSettings() {
  return get<ShippingDeadlineSettingDto[]>('/api/v1/system-settings/shipping-deadline-settings')
}

export function updateShippingDeadlineSettings(items: ShippingDeadlineSettingPayload[]) {
  return put<ShippingDeadlineSettingsUpdateResponse>('/api/v1/system-settings/shipping-deadline-settings', {
    items
  })
}

export function listPrintSettings() {
  return get<PrintSettingDto[]>('/api/v1/system-settings/print-settings')
}

export function listPrinters() {
  return get<PrinterDto[]>('/api/v1/system-settings/printers')
}

export function createPrintSetting(payload: PrintSettingPayload) {
  return post<PrintSettingDto>('/api/v1/system-settings/print-settings', payload)
}

export function updatePrintSetting(id: number, payload: PrintSettingPayload) {
  return put<PrintSettingDto>(`/api/v1/system-settings/print-settings/${id}`, payload)
}

export function deletePrintSetting(id: number) {
  return del<{ status: string }>(`/api/v1/system-settings/print-settings/${id}`)
}

/* ============== 定时任务 API ============== */
export function listScheduledTasks() {
  return get<ScheduledTaskDto[]>('/api/v1/system-settings/scheduled-tasks')
}

export function createScheduledTask(payload: ScheduledTaskPayload) {
  return post<ScheduledTaskDto>('/api/v1/system-settings/scheduled-tasks', payload)
}

export function updateScheduledTask(id: number, payload: ScheduledTaskPayload) {
  return put<ScheduledTaskDto>(`/api/v1/system-settings/scheduled-tasks/${id}`, payload)
}

export function deleteScheduledTask(id: number) {
  return del<{ status: string }>(`/api/v1/system-settings/scheduled-tasks/${id}`)
}

export function toggleScheduledTask(id: number) {
  return post<ScheduledTaskDto>(`/api/v1/system-settings/scheduled-tasks/${id}/toggle`)
}

export function runScheduledTask(id: number) {
  return post<{ status: string }>(`/api/v1/system-settings/scheduled-tasks/${id}/run`)
}

export function listScheduledTaskRuns(params?: { task_id?: number; page?: number; page_size?: number }) {
  return get<ScheduledTaskRunListResponse>('/api/v1/system-settings/scheduled-task-runs', {
    params: params || {},
    background: true
  })
}

export function getRunSteps(runId: number) {
  return get<ScheduledTaskRunStepDto[]>(`/api/v1/system-settings/scheduled-task-runs/${runId}/steps`, { background: true })
}

export function getRunOrders(runId: number, params?: { needs_reprint?: boolean }) {
  return get<ScheduledTaskRunOrderDto[]>(
    `/api/v1/system-settings/scheduled-task-runs/${runId}/orders`,
    { params: params || {}, background: true }
  )
}

export function getRunPlatforms(runId: number, params?: { needs_reprint?: boolean }) {
  return get<ScheduledTaskRunPlatformDto[]>(
    `/api/v1/system-settings/scheduled-task-runs/${runId}/platforms`,
    { params: params || {}, background: true }
  )
}

export async function exportRunPdfsBlob(runId: number): Promise<{ blob: Blob; filename: string }> {
  try {
    const resp = await http.get(`/api/v1/system-settings/scheduled-task-runs/${runId}/pdf`, {
      silent: true,
      responseType: 'blob'
    })
    return {
      blob: resp.data,
      filename: filenameFromContentDisposition(resp.headers['content-disposition'])
    }
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.data instanceof Blob) {
      const text = await error.response.data.text()
      let detail = text
      try {
        const data = JSON.parse(text) as { detail?: string; message?: string }
        detail = data.detail || data.message || text
      } catch {
        detail = text
      }
      if (detail) throw new Error(detail)
    }
    throw error
  }
}

export function createRunPdfsDownloadLink(runId: number) {
  return post<ScheduledTaskRunPdfDownloadLinkDto>(
    `/api/v1/system-settings/scheduled-task-runs/${runId}/pdf-download-link`,
    undefined,
    { silent: true }
  )
}

export function reprintRunOrder(orderId: number) {
  return post<{ status: string }>(
    `/api/v1/system-settings/scheduled-task-run-orders/${orderId}/reprint`
  )
}

export function reprintRunPlatform(runId: number, platform: string) {
  return post<ScheduledTaskRunPlatformDto>(
    `/api/v1/system-settings/scheduled-task-runs/${runId}/platforms/${encodeURIComponent(platform)}/reprint`
  )
}

/* ============== 邮件 SMTP API ============== */
export function listEmailProviders() {
  return get<EmailProviderDto[]>('/api/v1/system-settings/email-providers')
}

export function getEmailSmtp() {
  return get<EmailSmtpDto>('/api/v1/system-settings/email-smtp')
}

export function updateEmailSmtp(payload: EmailSmtpPayload) {
  return put<EmailSmtpDto>('/api/v1/system-settings/email-smtp', payload)
}

export function testEmailSmtp(recipient: string) {
  return post<EmailSmtpDto>('/api/v1/system-settings/email-smtp/test', { recipient })
}

export function getWecomRobotSetting() {
  return get<WeComRobotSettingDto>('/api/v1/system-settings/wecom-robot')
}

export function listWecomMentionUsers() {
  return get<WeComMentionUserOptionDto[]>('/api/v1/system-settings/wecom-robot/mention-users')
}

export function updateWecomRobotSetting(payload: WeComRobotSettingPayload) {
  return put<WeComRobotSettingDto>('/api/v1/system-settings/wecom-robot', payload)
}

export function testWecomRobotSetting(content?: string) {
  return post<WeComRobotTestResponse>('/api/v1/system-settings/wecom-robot/test', {
    content: content ?? ''
  })
}

export function listTranslationProviderOptions() {
  return get<TranslationProviderOptionDto[]>('/api/v1/system-settings/translation-provider-options')
}

export function listTranslationLanguageOptions() {
  return get<TranslationLanguageOptionDto[]>('/api/v1/system-settings/translation-language-options', {
    background: true,
    silent: true
  })
}

export function getTranslationProviderSetting(provider = 'baidu') {
  return get<TranslationProviderSettingDto>('/api/v1/system-settings/translation-provider', {
    params: { provider }
  })
}

export function updateTranslationProviderSetting(payload: TranslationProviderSettingPayload) {
  return put<TranslationProviderSettingDto>('/api/v1/system-settings/translation-provider', payload)
}

export function testTranslationProviderSetting(payload: { provider: string; text: string; target_language: string }) {
  return post<TranslationProviderTestResponse>('/api/v1/system-settings/translation-provider/test', payload)
}

export function listModelEndpoints(params?: { enabled_only?: boolean }) {
  return get<ModelEndpointDto[]>('/api/v1/system-settings/model-endpoints', { params: params || {} })
}

export function createModelEndpoint(payload: ModelEndpointPayload) {
  return post<ModelEndpointDto>('/api/v1/system-settings/model-endpoints', payload)
}

export function updateModelEndpoint(id: number, payload: ModelEndpointPayload) {
  return put<ModelEndpointDto>(`/api/v1/system-settings/model-endpoints/${id}`, payload)
}

export function deleteModelEndpoint(id: number) {
  return del<{ status: string }>(`/api/v1/system-settings/model-endpoints/${id}`)
}

export function listModelSettings(params?: { enabled_only?: boolean }) {
  return get<ModelSettingDto[]>('/api/v1/system-settings/model-settings', { params: params || {} })
}

export function createModelSetting(payload: ModelSettingPayload) {
  return post<ModelSettingDto>('/api/v1/system-settings/model-settings', payload)
}

export function updateModelSetting(id: number, payload: ModelSettingPayload) {
  return put<ModelSettingDto>(`/api/v1/system-settings/model-settings/${id}`, payload)
}

export function deleteModelSetting(id: number) {
  return del<{ status: string }>(`/api/v1/system-settings/model-settings/${id}`)
}

export function testModelSettingConnection(id: number) {
  return post<ModelConnectionTestResponse>(`/api/v1/system-settings/model-settings/${id}/test`)
}
