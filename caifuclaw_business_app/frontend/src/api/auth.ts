/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import http, { get, post } from './http'
import type { CurrentUser } from '@/stores/auth'

export interface LoginPayload {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type?: string
}

export function login(payload: LoginPayload): Promise<LoginResponse> {
  return post<LoginResponse>('/api/auth/login', payload, { silent: true })
}

export function fetchCurrentUser(): Promise<CurrentUser> {
  return get<CurrentUser>('/api/v1/auth/me')
}

export function logout(): Promise<void> {
  return post('/api/v1/auth/logout').then(() => undefined)
}

export interface ChangePasswordPayload {
  old_password: string
  new_password: string
}

export function changePassword(payload: ChangePasswordPayload): Promise<void> {
  return http.post('/api/v1/auth/change-password', payload).then(() => undefined)
}
