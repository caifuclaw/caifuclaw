import axios, { AxiosError } from 'axios'
import type { AxiosInstance, AxiosRequestConfig, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { message } from 'antd'

const pendingRef = { count: 0 }
const listeners = new Set<(loading: boolean) => void>()

function setPending(delta: number) {
  pendingRef.count = Math.max(0, pendingRef.count + delta)
  const loading = pendingRef.count > 0
  listeners.forEach((fn) => fn(loading))
}

export function onRequestPending(cb: (loading: boolean) => void): () => void {
  listeners.add(cb)
  return () => listeners.delete(cb)
}

export interface RequestExtraOptions {
  silent?: boolean
  background?: boolean
  retry?: number
  retryDelayMs?: number
}

interface CaifuClawInternalRequestConfig extends InternalAxiosRequestConfig {
  __caifuclawPendingTracked?: boolean
}

declare module 'axios' {
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type
  export interface InternalAxiosRequestConfig extends RequestExtraOptions {}
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type
  export interface AxiosRequestConfig extends RequestExtraOptions {}
}

const http: AxiosInstance = axios.create({
  baseURL: '',
  timeout: 30000,
  withCredentials: true
})

const DEFAULT_TRANSIENT_RETRIES = 2
const DEFAULT_RETRY_DELAY_MS = 700
const IDEMPOTENT_METHODS = new Set(['get', 'head', 'options'])
const TRANSIENT_ERROR_CODES = new Set([
  'ERR_NETWORK',
  'ECONNABORTED',
  'ECONNRESET',
  'ECONNREFUSED',
  'ETIMEDOUT'
])

function isCanceledRequest(error: AxiosError): boolean {
  return axios.isCancel(error) || error.code === 'ERR_CANCELED'
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => globalThis.setTimeout(resolve, ms))
}

function requestRetryCount(config: CaifuClawInternalRequestConfig | undefined): number {
  if (!config) return 0
  if (typeof config.retry === 'number') return Math.max(0, config.retry)
  const method = String(config.method || 'get').toLowerCase()
  return IDEMPOTENT_METHODS.has(method) ? DEFAULT_TRANSIENT_RETRIES : 0
}

function retryDelayMs(config: CaifuClawInternalRequestConfig, attempt: number): number {
  const baseDelay = typeof config.retryDelayMs === 'number' ? config.retryDelayMs : DEFAULT_RETRY_DELAY_MS
  return Math.max(0, baseDelay * attempt)
}

function isTransientRequestError(error: AxiosError): boolean {
  if (error.response) {
    return [502, 503, 504].includes(error.response.status)
  }
  return !error.response && (!error.code || TRANSIENT_ERROR_CODES.has(error.code))
}

function finishPending(config: CaifuClawInternalRequestConfig | undefined) {
  if (config?.__caifuclawPendingTracked) {
    config.__caifuclawPendingTracked = false
    setPending(-1)
  }
}

http.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const requestConfig = config as CaifuClawInternalRequestConfig
    config.headers = config.headers || {}
    if (!config.background && !requestConfig.__caifuclawPendingTracked) {
      requestConfig.__caifuclawPendingTracked = true
      setPending(1)
    }
    return config
  },
  (error) => {
    setPending(-1)
    return Promise.reject(error)
  }
)

http.interceptors.response.use(
  (response: AxiosResponse) => {
    finishPending(response.config as CaifuClawInternalRequestConfig | undefined)
    return response
  },
  async (error: AxiosError) => {
    const config = error.config as CaifuClawInternalRequestConfig | undefined
    const retryAttempt = Number(config?.headers?.['X-CaifuClaw-Retry-Attempt'] || 0)
    if (isCanceledRequest(error)) {
      finishPending(config)
      return Promise.reject(error)
    }

    if (config && isTransientRequestError(error) && retryAttempt < requestRetryCount(config)) {
      await delay(retryDelayMs(config, retryAttempt + 1))
      config.headers = config.headers || {}
      config.headers['X-CaifuClaw-Retry-Attempt'] = String(retryAttempt + 1)
      return http.request(config)
    }

    finishPending(config)

    const status = error.response?.status
    const data = error.response?.data as { detail?: string; message?: string } | undefined
    const detail = data?.detail || data?.message || error.message

    if (status === 401) {
      const current = window.location.pathname + window.location.search
      if (!current.startsWith('/login')) {
        const redirect = encodeURIComponent(current)
        window.location.replace(`/login?redirect=${redirect}`)
      }
    } else if (!error.config?.silent) {
      message.error(detail || `请求失败 (${status || 'network'})`)
    }

    return Promise.reject(error)
  }
)

export async function get<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const res = await http.get<T>(url, config)
  return res.data
}

export async function post<T = unknown, D = unknown>(
  url: string,
  body?: D,
  config?: AxiosRequestConfig
): Promise<T> {
  const res = await http.post<T>(url, body, config)
  return res.data
}

export async function put<T = unknown, D = unknown>(
  url: string,
  body?: D,
  config?: AxiosRequestConfig
): Promise<T> {
  const res = await http.put<T>(url, body, config)
  return res.data
}

export async function del<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const res = await http.delete<T>(url, config)
  return res.data
}

export default http
