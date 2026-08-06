/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { create } from 'zustand'
import { flattenMenus } from '@/menus'
import { fetchCurrentUser } from '@/api/auth'

export interface CurrentUser {
  id: number
  username: string
  display_name?: string
  role_id?: number | null
  role_code?: string
  role_name?: string
  role_ids?: number[]
  role_codes?: string[]
  role_names?: string[]
  menus?: string[]
}

export function isAdminUser(user: CurrentUser | null): boolean {
  return user?.role_code === 'admin' || (user?.role_codes || []).includes('admin')
}

function permissionCodesForMenu(code: string): string[] {
  if (code === 'outbound-scans') return ['outbound-scans', 'order-outbound']
  return [code]
}

function menuCodesFromPermissions(codes: string[]): string[] {
  const normalized = new Set(codes)
  if (normalized.has('order-outbound')) normalized.add('outbound-scans')
  return Array.from(normalized)
}

interface AuthState {
  token: string
  currentUser: CurrentUser | null
  setToken: (token: string) => void
  setCurrentUser: (user: CurrentUser | null) => void
  logout: () => void
  hasMenu: (code: string) => boolean
  menuCodes: () => string[]
  firstAllowedPath: () => string
  ensureCurrentUser: () => Promise<CurrentUser | null>
}

const COOKIE_SESSION = 'cookie-session'

export const useAuthStore = create<AuthState>((set, get) => ({
  token: COOKIE_SESSION,
  currentUser: null,
  setToken: (token) => {
    set({ token: token ? COOKIE_SESSION : '' })
  },
  setCurrentUser: (user) => set({ currentUser: user }),
  logout: () => {
    set({ token: '', currentUser: null })
  },
  hasMenu: (code) => {
    const user = get().currentUser
    if (!code) return true
    if (isAdminUser(user)) return true
    const allowed = user?.menus || []
    return permissionCodesForMenu(code).some((item) => allowed.includes(item))
  },
  menuCodes: () => {
    const user = get().currentUser
    if (isAdminUser(user)) return flattenMenus().map((m) => m.code)
    return menuCodesFromPermissions(user?.menus || [])
  },
  firstAllowedPath: () => {
    const codes = get().menuCodes()
    for (const item of flattenMenus()) {
      if (item.children?.length) continue
      if (item.path.startsWith('/_group/')) continue
      if (codes.includes(item.code)) return item.path
    }
    return '/dashboard'
  },
  ensureCurrentUser: async () => {
    const state = get()
    if (!state.token) return null
    if (state.currentUser) return state.currentUser
    try {
      const user = await fetchCurrentUser()
      set({ currentUser: user })
      return user
    } catch (e) {
      get().logout()
      throw e
    }
  }
}))
