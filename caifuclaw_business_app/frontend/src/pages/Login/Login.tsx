import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from '@/router/navigation'
import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { App, Button, Checkbox, Form, Input } from 'antd'
import { login as loginApi } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import './Login.less'

const REMEMBER_KEY = 'sync_login_remember_credentials'
const CRED_KEY = 'sync_login_credentials'

interface LoginForm {
  username: string
  password: string
  remember: boolean
}

function loadSaved(): Partial<LoginForm> {
  try {
    const saved = JSON.parse(localStorage.getItem(CRED_KEY) || '{}') as Partial<LoginForm>
    const username = typeof saved.username === 'string' ? saved.username : ''
    localStorage.setItem(CRED_KEY, JSON.stringify({ username }))
    return { username }
  } catch {
    return {}
  }
}

function loginErrorMessage(error: unknown) {
  const err = error as {
    code?: string
    message?: string
    response?: { status?: number; data?: { detail?: string; message?: string } }
  }
  const status = err.response?.status
  const detail = err.response?.data?.detail || err.response?.data?.message
  if (status === 401) return detail || '用户名或密码错误'
  if (status === 403) return detail || '用户已停用'
  if (!status || err.code === 'ERR_NETWORK') return '无法连接后端服务，请确认财赋业务应用已启动'
  return detail || `登录失败 (${status})`
}

export function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const { message } = App.useApp()
  const setToken = useAuthStore((s) => s.setToken)
  const ensureCurrentUser = useAuthStore((s) => s.ensureCurrentUser)
  const firstAllowedPath = useAuthStore((s) => s.firstAllowedPath)
  const [loading, setLoading] = useState(false)
  const saved = useMemo(loadSaved, [])

  useEffect(() => {
    document.documentElement.classList.add('login-viewport')
    return () => document.documentElement.classList.remove('login-viewport')
  }, [])

  const initialValues: LoginForm = {
    username: saved.username || '',
    password: '',
    remember: localStorage.getItem(REMEMBER_KEY) !== 'false'
  }

  function persistCredentials(values: LoginForm) {
    if (values.remember) {
      localStorage.setItem(REMEMBER_KEY, 'true')
      localStorage.setItem(CRED_KEY, JSON.stringify({ username: values.username }))
    } else {
      localStorage.setItem(REMEMBER_KEY, 'false')
      localStorage.removeItem(CRED_KEY)
    }
  }

  async function onSubmit(values: LoginForm) {
    setLoading(true)
    try {
      const username = values.username.trim()
      const password = values.password
      const data = await loginApi({ username, password })
      persistCredentials({ ...values, username })
      setToken(data.access_token)
      await ensureCurrentUser()
      const params = new URLSearchParams(location.search)
      const redirect = params.get('redirect') || ''
      navigate(redirect.startsWith('/') ? redirect : firstAllowedPath(), { replace: true })
      message.success('登录成功')
    } catch (e) {
      message.error(loginErrorMessage(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <section className="login-brand-panel">
        <div className="login-brand-logo">
          <img src="/caifuclaw-ai-logo.png" alt="CaifuClaw AI 跨境运营智能体" />
        </div>

        <div className="login-visual" aria-hidden="true">
          <div className="login-visual__image-wrap">
            <img className="login-visual__image" src="/login-commerce-visual-cutout.webp" alt="" />
          </div>
          <div className="login-visual__caption">
            <strong>让AI做运营 让人做战略</strong>
            <span>智能选品 ・ 多平台运营 ・ ROI分析与提效</span>
          </div>
        </div>
      </section>

      <section className="login-form-panel">
        <div className="login-form-card">
          <div className="login-form-heading">
            <h1>欢迎回来</h1>
            <p>输入您的账号和密码登录</p>
          </div>

          <Form layout="vertical" requiredMark={false} initialValues={initialValues} autoComplete="on" onFinish={onSubmit}>
            <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
              <Input
                size="large"
                prefix={<UserOutlined />}
                placeholder="请输入用户名"
                autoComplete="username"
                aria-label="用户名"
              />
            </Form.Item>
            <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
              <Input.Password
                size="large"
                prefix={<LockOutlined />}
                placeholder="请输入密码"
                autoComplete="current-password"
                aria-label="密码"
              />
            </Form.Item>

            <div className="login-options">
              <Form.Item name="remember" valuePropName="checked" noStyle>
                <Checkbox>记住账号</Checkbox>
              </Form.Item>
            </div>

            <Form.Item>
              <Button className="login-submit" type="primary" htmlType="submit" size="large" block loading={loading}>
                登录
              </Button>
            </Form.Item>
          </Form>
        </div>
      </section>
    </div>
  )
}
