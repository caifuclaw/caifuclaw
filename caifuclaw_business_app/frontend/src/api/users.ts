import { get, post, put, del } from './http'

export interface UserDto {
  id: number
  username: string
  display_name?: string | null
  wecom_mobile?: string | null
  role_id?: number | null
  role_code?: string
  role_name?: string | null
  role_ids?: number[]
  role_codes?: string[]
  role_names?: string[]
  enabled: boolean
  created_at?: string
  updated_at?: string
}

export interface UserPayload {
  username: string
  password?: string
  display_name?: string
  wecom_mobile?: string
  role_id?: number | null
  role_ids?: number[]
  enabled?: boolean
}

export interface UserUpdatePayload {
  display_name?: string
  wecom_mobile?: string
  role_id?: number | null
  role_ids?: number[]
  enabled?: boolean
}

export interface RoleDto {
  id: number
  code: string
  name: string
  description?: string | null
  enabled: boolean
  is_system?: boolean
  menus?: string[]
  created_at?: string
  updated_at?: string
}

export interface RoleCreatePayload {
  code: string
  name: string
  description?: string
  enabled?: boolean
  menus: string[]
}

export interface RoleUpdatePayload {
  name: string
  description?: string
  enabled?: boolean
  menus: string[]
}

export function listUsers() {
  return get<UserDto[]>('/api/v1/users')
}

export function createUser(payload: UserPayload) {
  return post<UserDto>('/api/v1/users', payload)
}

export function updateUser(id: number, payload: UserUpdatePayload) {
  return put<UserDto>(`/api/v1/users/${id}`, payload)
}

export function deleteUser(id: number) {
  return del<{ status: string }>(`/api/v1/users/${id}`)
}

export function resetUserPassword(id: number, password: string) {
  return post<{ status: string }>(`/api/v1/users/${id}/reset-password`, { password })
}

export function listRoles() {
  return get<RoleDto[]>('/api/v1/roles')
}

export function createRole(payload: RoleCreatePayload) {
  return post<RoleDto>('/api/v1/roles', payload)
}

export function updateRole(id: number, payload: RoleUpdatePayload) {
  return put<RoleDto>(`/api/v1/roles/${id}`, payload)
}

export function deleteRole(id: number) {
  return del<{ status: string }>(`/api/v1/roles/${id}`)
}
