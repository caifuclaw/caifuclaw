import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useLocation, useNavigate } from '@/router/navigation'
import {
  LockOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  UserOutlined
} from '@ant-design/icons'
import { App, Avatar, Breadcrumb, Button, Drawer, Dropdown, Form, Input, Layout, Menu, Modal, Space, type MenuProps } from 'antd'
import { changePassword, logout as logoutApi } from '@/api/auth'
import { findMenuByPath, findParentMenuPaths, menus, type MenuItem } from '@/menus'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

interface PasswordForm {
  old_password: string
  new_password: string
  confirm_password: string
}

const { Header, Content, Sider } = Layout

function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.matchMedia(query).matches
  })

  useEffect(() => {
    if (typeof window === 'undefined') return
    const media = window.matchMedia(query)
    const updateMatches = () => setMatches(media.matches)
    updateMatches()
    media.addEventListener('change', updateMatches)
    return () => media.removeEventListener('change', updateMatches)
  }, [query])

  return matches
}

function toMenuItems(items: MenuItem[], hasMenu: (code: string) => boolean): NonNullable<MenuProps['items']> {
  const result: NonNullable<MenuProps['items']> = []
  for (const item of items) {
    if (item.hideInMenu) continue

    const children = item.children?.length ? toMenuItems(item.children, hasMenu) : undefined
    if (item.children?.length && !children?.length) continue
    if (!item.children?.length && !hasMenu(item.code)) continue

    result.push({
      key: item.path,
      icon: item.icon,
      label: item.title,
      children
    })
  }
  return result
}

export function BasicLayout({ children }: { children: ReactNode }) {
  const location = useLocation()
  const navigate = useNavigate()
  const { message } = App.useApp()
  const [form] = Form.useForm<PasswordForm>()
  const darkMode = useAppStore((s) => s.darkMode)
  const collapsed = useAppStore((s) => s.sidebarCollapsed)
  const setCollapsed = useAppStore((s) => s.setSidebarCollapsed)
  const currentUser = useAuthStore((s) => s.currentUser)
  const logout = useAuthStore((s) => s.logout)
  const hasMenu = useAuthStore((s) => s.hasMenu)
  const [openKeys, setOpenKeys] = useState<string[]>([])
  const [pwdVisible, setPwdVisible] = useState(false)
  const [pwdLoading, setPwdLoading] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const isMobile = useMediaQuery('(max-width: 768px), (max-width: 960px) and (max-height: 500px)')
  const isDashboard = location.pathname === '/dashboard'
  const isOperationsDailyReport = location.pathname === '/operations-daily-report'
  const isTrafficPage = ['/traffic-analytics', '/traffic-sync-status'].includes(location.pathname)
  const isAiImageProcessing = location.pathname === '/ai-image-processing'
  const isTextTranslation = location.pathname === '/text-translation'
  const usesDashboardViewport = isDashboard || isOperationsDailyReport || isTrafficPage
  const isTablePage =
    ['/orders', '/order-summary', '/platform-product-catalog'].includes(location.pathname) ||
    (isTrafficPage && !isMobile)
  const useDashboardMobileShell = (isDashboard || isOperationsDailyReport || isTrafficPage || isAiImageProcessing || isTextTranslation) && isMobile

  const menuItems = useMemo(() => toMenuItems(menus, hasMenu), [hasMenu])
  const currentMenu = findMenuByPath(location.pathname)
  const contentClassName =
    isOperationsDailyReport
      ? 'caifuclaw-shell__content caifuclaw-shell__content--operations-daily-report'
      : isTablePage
        ? 'caifuclaw-shell__content caifuclaw-shell__content--table-page'
        : isAiImageProcessing
            ? 'caifuclaw-shell__content caifuclaw-shell__content--ai-image-page'
            : isTextTranslation
              ? 'caifuclaw-shell__content caifuclaw-shell__content--text-translation-page'
              : 'caifuclaw-shell__content'
  const shellClassName = [
    'caifuclaw-shell',
    darkMode ? 'caifuclaw-shell--dark-menu' : '',
    useDashboardMobileShell ? 'caifuclaw-shell--dashboard-mobile' : ''
  ]
    .filter(Boolean)
    .join(' ')
  const userInitial = String(currentUser?.display_name || currentUser?.username || 'U').trim().slice(0, 1).toUpperCase()

  useEffect(() => {
    const parents = findParentMenuPaths(location.pathname)
    if (parents.length) {
      setOpenKeys((keys) => Array.from(new Set([...keys, ...parents])))
    }
  }, [location.pathname])

  useEffect(() => {
    document.documentElement.classList.toggle('dashboard-viewport', usesDashboardViewport)
    return () => document.documentElement.classList.remove('dashboard-viewport')
  }, [usesDashboardViewport])

  useEffect(() => {
    document.documentElement.classList.toggle('ai-image-processing-viewport', isAiImageProcessing)
    return () => document.documentElement.classList.remove('ai-image-processing-viewport')
  }, [isAiImageProcessing])

  useEffect(() => {
    document.documentElement.classList.toggle('text-translation-viewport', isTextTranslation)
    return () => document.documentElement.classList.remove('text-translation-viewport')
  }, [isTextTranslation])

  useEffect(() => {
    if (!useDashboardMobileShell) setMobileMenuOpen(false)
  }, [useDashboardMobileShell])

  const userMenu: MenuProps['items'] = [
    {
      key: 'profile',
      disabled: true,
      icon: <UserOutlined />,
      label: currentUser?.username || '访客'
    },
    {
      key: 'password',
      icon: <LockOutlined />,
      label: '修改密码'
    },
    { type: 'divider' },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录'
    }
  ]

  async function handleLogout() {
    try {
      await logoutApi()
    } catch {
      // Local logout must still succeed when the session has already expired.
    }
    logout()
    message.success('已退出登录')
    navigate('/login', { replace: true })
  }

  function renderMenu(className: string, inDrawer = false) {
    return (
      <Menu
        className={className}
        mode="inline"
        theme={darkMode ? 'dark' : 'light'}
        items={menuItems}
        selectedKeys={[location.pathname]}
        openKeys={!inDrawer && collapsed ? [] : openKeys}
        onOpenChange={(keys) => {
          const nextKeys = keys as string[]
          setOpenKeys(nextKeys)
        }}
        onClick={({ key }) => {
          const target = String(key)
          if (!target.startsWith('/_group/')) {
            navigate(target)
            if (inDrawer) setMobileMenuOpen(false)
          }
        }}
      />
    )
  }

  async function submitPasswordChange() {
    const values = await form.validateFields()
    setPwdLoading(true)
    try {
      await changePassword({
        old_password: values.old_password,
        new_password: values.new_password
      })
      message.success('密码修改成功，请重新登录')
      setPwdVisible(false)
      handleLogout()
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      message.error(detail || '修改密码失败')
    } finally {
      setPwdLoading(false)
    }
  }

  const headerActions = (
    <Space size={12} className="header-actions">
      <Dropdown
        trigger={['click']}
        placement="bottomRight"
        menu={{
          items: userMenu,
          onClick: ({ key }) => {
            if (key === 'password') {
              form.resetFields()
              setPwdVisible(true)
            }
            if (key === 'logout') handleLogout()
          }
        }}
      >
        <a className="user-trigger">
          <Avatar size="small" style={{ backgroundColor: '#1677ff' }}>
            {userInitial}
          </Avatar>
          <span className="user-name">{currentUser?.display_name || currentUser?.username || '未登录'}</span>
        </a>
      </Dropdown>
    </Space>
  )

  return (
    <>
      <Layout className={shellClassName}>
        {!useDashboardMobileShell ? (
          <Sider
            className="caifuclaw-shell__sider"
            width={192}
            collapsedWidth={64}
            collapsed={collapsed}
            trigger={null}
            theme={darkMode ? 'dark' : 'light'}
          >
            <div className="caifuclaw-shell__brand" onClick={() => navigate('/dashboard')}>
              <img src="/caifuclaw-ai-mark.png" alt="" />
              {!collapsed ? <span>CaifuClaw AI</span> : null}
            </div>
            {renderMenu('caifuclaw-shell__menu')}
          </Sider>
        ) : null}

        <Layout className="caifuclaw-shell__main">
          <Header className="caifuclaw-shell__header">
            <Button
              type="text"
              className="caifuclaw-shell__collapse"
              icon={useDashboardMobileShell ? <MenuUnfoldOutlined /> : collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => (useDashboardMobileShell ? setMobileMenuOpen(true) : setCollapsed(!collapsed))}
            />
            <div className="caifuclaw-shell__header-spacer" />
            {headerActions}
          </Header>
          <Content className={contentClassName}>
            <Breadcrumb
              className="caifuclaw-shell__breadcrumb"
              items={[
                { title: <a onClick={() => navigate('/dashboard')}>首页</a> },
                ...(currentMenu && currentMenu.path !== '/dashboard' ? [{ title: currentMenu.title }] : [])
              ]}
            />
            {children}
          </Content>
        </Layout>
      </Layout>

      <Drawer
        className={darkMode ? 'caifuclaw-mobile-menu-drawer caifuclaw-mobile-menu-drawer--dark' : 'caifuclaw-mobile-menu-drawer'}
        placement="left"
        width={264}
        open={mobileMenuOpen}
        onClose={() => setMobileMenuOpen(false)}
        title={
          <div className="caifuclaw-mobile-menu__brand">
            <img src="/caifuclaw-ai-mark.png" alt="" />
            <span>CaifuClaw AI</span>
          </div>
        }
      >
        {renderMenu('caifuclaw-shell__menu caifuclaw-mobile-menu__menu', true)}
      </Drawer>

      <Modal
        open={pwdVisible}
        title="修改密码"
        confirmLoading={pwdLoading}
        okText="提交"
        cancelText="取消"
        destroyOnHidden
        onCancel={() => setPwdVisible(false)}
        onOk={submitPasswordChange}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="old_password" label="当前密码" rules={[{ required: true, message: '请输入当前密码' }]}>
            <Input.Password autoComplete="current-password" />
          </Form.Item>
          <Form.Item
            name="new_password"
            label="新密码"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: 6, message: '密码至少 6 位' }
            ]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item
            name="confirm_password"
            label="确认新密码"
            dependencies={['new_password']}
            rules={[
              { required: true, message: '请再次输入新密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  return !value || getFieldValue('new_password') === value
                    ? Promise.resolve()
                    : Promise.reject(new Error('两次输入不一致'))
                }
              })
            ]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Modal>

    </>
  )
}
