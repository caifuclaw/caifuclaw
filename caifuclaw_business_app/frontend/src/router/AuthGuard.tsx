import { useEffect, useState, type ReactNode } from 'react'
import { Redirect } from 'wouter'
import { useLocation } from '@/router/navigation'
import { Result, Spin } from 'antd'
import { findMenuByPath } from '@/menus'
import { useAuthStore } from '@/stores/auth'

export function AuthGuard({ children }: { children: ReactNode }) {
  const location = useLocation()
  const token = useAuthStore((s) => s.token)
  const currentUser = useAuthStore((s) => s.currentUser)
  const ensureCurrentUser = useAuthStore((s) => s.ensureCurrentUser)
  const hasMenu = useAuthStore((s) => s.hasMenu)
  const firstAllowedPath = useAuthStore((s) => s.firstAllowedPath)
  const [checking, setChecking] = useState(Boolean(token))

  useEffect(() => {
    let mounted = true
    if (!token) {
      setChecking(false)
      return
    }
    setChecking(true)
    ensureCurrentUser()
      .catch(() => undefined)
      .finally(() => {
        if (mounted) setChecking(false)
      })
    return () => {
      mounted = false
    }
  }, [ensureCurrentUser, token])

  if (!token) {
    const redirect = encodeURIComponent(location.pathname + location.search)
    return <Redirect to={`/login?redirect=${redirect}`} replace />
  }

  if (checking) {
    return (
      <div style={{ display: 'grid', minHeight: '100vh', placeItems: 'center' }}>
        <Spin />
      </div>
    )
  }

  const currentMenu = findMenuByPath(location.pathname)
  if (currentUser && currentMenu && !hasMenu(currentMenu.code)) {
    const target = firstAllowedPath()
    if (target === location.pathname) {
      return <Result status="403" title="无访问权限" subTitle="当前账号未分配可访问的菜单，请联系管理员。" />
    }
    return <Redirect to={target} replace />
  }

  return children
}
