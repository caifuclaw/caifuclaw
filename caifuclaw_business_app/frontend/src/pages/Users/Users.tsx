import { useEffect, useMemo, useState } from 'react'
import { PlusOutlined } from '@ant-design/icons'
import { App, Button, Form, Input, Modal, Select, Space, Switch, Tag } from 'antd'
import { DataTable } from '@/components/DataTable'
import type { ColumnsType } from 'antd/es/table'
import {
  createUser,
  listRoles,
  listUsers,
  resetUserPassword,
  updateUser,
  type RoleDto,
  type UserDto
} from '@/api/users'
import { formatTime } from '@/utils/format'
import { shouldIgnoreTableRowDoubleClick } from '@/utils/tableInteractions'

interface UserFormValues {
  username?: string
  password?: string
  display_name?: string
  wecom_mobile?: string
  role_ids?: number[]
  enabled?: boolean
}

interface ResetFormValues {
  password?: string
}

const MAINLAND_MOBILE_PATTERN = /^1[3-9]\d{9}$/

export function Users() {
  const { message } = App.useApp()
  const [userForm] = Form.useForm<UserFormValues>()
  const [resetForm] = Form.useForm<ResetFormValues>()
  const [users, setUsers] = useState<UserDto[]>([])
  const [roles, setRoles] = useState<RoleDto[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [userOpen, setUserOpen] = useState(false)
  const [userMode, setUserMode] = useState<'create' | 'edit'>('create')
  const [editingUser, setEditingUser] = useState<UserDto | null>(null)
  const [resetOpen, setResetOpen] = useState(false)
  const [resetTarget, setResetTarget] = useState<UserDto | null>(null)

  const enabledRoles = useMemo(() => roles.filter((role) => role.enabled), [roles])
  const userSelectedRoleIds = Form.useWatch('role_ids', userForm) || []
  const roleOptions = useMemo(
    () =>
      roles.map((role) => ({
        value: role.id,
        label: roleLabel(role),
        disabled: !role.enabled && !userSelectedRoleIds.includes(role.id)
      })),
    [roles, userSelectedRoleIds]
  )
  const isEditingAdminUser = userMode === 'edit' && hasAdminRole(editingUser)

  function defaultRoleIds() {
    const role = enabledRoles.find((item) => item.code !== 'admin') || enabledRoles[0]
    return role ? [role.id] : []
  }

  function roleLabel(role?: Pick<RoleDto, 'code' | 'name'> | null) {
    if (role?.code === 'admin') return '超级管理员'
    return role?.name || '-'
  }

  function hasAdminRole(row?: Pick<UserDto, 'role_code' | 'role_codes'> | null) {
    return row?.role_code === 'admin' || (row?.role_codes || []).includes('admin')
  }

  function userRoleItems(row: UserDto) {
    const ids = row.role_ids?.length ? row.role_ids : row.role_id ? [row.role_id] : []
    const codes = row.role_codes?.length ? row.role_codes : row.role_code ? [row.role_code] : []
    const names = row.role_names?.length ? row.role_names : row.role_name ? [row.role_name] : []
    return ids.map((id, index) => ({
      id,
      code: codes[index] || '',
      name: roleLabel({ code: codes[index] || '', name: names[index] || '' })
    }))
  }

  async function load() {
    setLoading(true)
    try {
      const [userResp, roleResp] = await Promise.all([listUsers(), listRoles()])
      setUsers(userResp || [])
      setRoles(roleResp || [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  function openCreateUser() {
    setUserMode('create')
    setEditingUser(null)
    userForm.resetFields()
    userForm.setFieldsValue({
      username: '',
      password: '',
      display_name: '',
      wecom_mobile: '',
      role_ids: defaultRoleIds(),
      enabled: true
    })
    setUserOpen(true)
  }

  function openEditUser(row: UserDto) {
    setUserMode('edit')
    setEditingUser(row)
    userForm.setFieldsValue({
      username: row.username,
      password: '',
      display_name: row.display_name || '',
      wecom_mobile: row.wecom_mobile || '',
      role_ids: row.role_ids?.length ? row.role_ids : row.role_id ? [row.role_id] : [],
      enabled: row.enabled
    })
    setUserOpen(true)
  }

  async function saveUser() {
    let values: UserFormValues
    try {
      values = await userForm.validateFields()
    } catch {
      return
    }
    const roleIds = values.role_ids || []
    if (!roleIds.length) {
      message.warning('请选择角色')
      return
    }
    setSaving(true)
    try {
      if (userMode === 'create') {
        await createUser({
          username: values.username?.trim() || '',
          password: values.password || '',
          display_name: values.display_name?.trim() || '',
          wecom_mobile: values.wecom_mobile?.trim() || '',
          role_ids: roleIds,
          enabled: values.enabled !== false
        })
      } else if (editingUser) {
        await updateUser(editingUser.id, {
          display_name: values.display_name?.trim() || '',
          wecom_mobile: values.wecom_mobile?.trim() || '',
          role_ids: roleIds,
          enabled: values.enabled !== false
        })
      }
      message.success('已保存')
      setUserOpen(false)
      await load()
    } finally {
      setSaving(false)
    }
  }

  function openReset(row: UserDto) {
    setResetTarget(row)
    resetForm.resetFields()
    setResetOpen(true)
  }

  async function savePassword() {
    const values = await resetForm.validateFields()
    if (!resetTarget) return
    setSaving(true)
    try {
      await resetUserPassword(resetTarget.id, values.password || '')
      message.success('密码已重置')
      setResetOpen(false)
    } finally {
      setSaving(false)
    }
  }

  const userColumns: ColumnsType<UserDto> = [
    { title: '用户名', dataIndex: 'username', width: 140 },
    { title: '姓名', dataIndex: 'display_name', width: 160, render: (value) => value || '-' },
    { title: '企微手机号', dataIndex: 'wecom_mobile', width: 140, render: (value) => value || '-' },
    {
      title: '角色',
      dataIndex: 'role_names',
      width: 260,
      render: (_, row) => {
        const items = userRoleItems(row)
        if (!items.length) return '-'
        return (
          <Space size={[4, 4]} wrap>
            {items.map((item) => (
              <Tag key={`${row.id}-${item.id}`} color={item.code === 'admin' ? 'blue' : 'default'}>
                {item.name}
              </Tag>
            ))}
          </Space>
        )
      }
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      width: 100,
      render: (value) => <Tag color={value ? 'success' : 'default'}>{value ? '启用' : '停用'}</Tag>
    },
    { title: '创建时间', dataIndex: 'created_at', width: 180, render: (value) => formatTime(value, true) },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      fixed: 'right',
      render: (_, row) => (
        <Space>
          <Button size="small" onClick={() => openEditUser(row)}>
            编辑
          </Button>
          <Button size="small" onClick={() => openReset(row)}>
            重置密码
          </Button>
        </Space>
      )
    }
  ]

  return (
    <div className="page-card users-page">
      <section className="users-page__section">
        <div className="users-page__section-header">
          <h2>用户管理</h2>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreateUser}>
            新增用户
          </Button>
        </div>
        <DataTable
          bordered
          rowKey="id"
          loading={loading}
          dataSource={users}
          columns={userColumns}
          pagination={false}
          onRow={(row) => ({
            onDoubleClick: (event) => {
              if (shouldIgnoreTableRowDoubleClick(event.target)) return
              openEditUser(row)
            }
          })}
        />
      </section>

      <Modal
        open={userOpen}
        title={userMode === 'create' ? '新增用户' : '编辑用户'}
        confirmLoading={saving}
        maskClosable={false}
        width={560}
        onOk={saveUser}
        onCancel={() => setUserOpen(false)}
        destroyOnClose
      >
        <Form form={userForm} labelCol={{ span: 6 }} wrapperCol={{ span: 16 }} preserve={false}>
          <Form.Item label="用户名" name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input disabled={userMode === 'edit'} autoComplete="off" />
          </Form.Item>
          {userMode === 'create' ? (
            <Form.Item label="密码" name="password" rules={[{ required: true, message: '请输入密码' }]}>
              <Input.Password autoComplete="new-password" />
            </Form.Item>
          ) : null}
          <Form.Item label="姓名" name="display_name">
            <Input />
          </Form.Item>
          <Form.Item
            label="企微手机号"
            name="wecom_mobile"
            normalize={(value) => (typeof value === 'string' ? value.trim() : value)}
            rules={[
              {
                pattern: MAINLAND_MOBILE_PATTERN,
                message: '请输入正确的大陆手机号'
              }
            ]}
          >
            <Input inputMode="numeric" maxLength={11} autoComplete="tel" />
          </Form.Item>
          <Form.Item label="角色" name="role_ids" rules={[{ required: true, message: '请选择角色' }]}>
            <Select
              mode="multiple"
              disabled={isEditingAdminUser}
              placeholder="请选择角色"
              options={roleOptions}
              optionFilterProp="label"
            />
          </Form.Item>
          <Form.Item label="状态" name="enabled" valuePropName="checked">
            <Switch disabled={isEditingAdminUser} checkedChildren="启用" unCheckedChildren="停用" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={resetOpen}
        title="重置密码"
        confirmLoading={saving}
        maskClosable={false}
        width={420}
        onOk={savePassword}
        onCancel={() => setResetOpen(false)}
        destroyOnClose
      >
        <Form form={resetForm} labelCol={{ span: 6 }} wrapperCol={{ span: 16 }} preserve={false}>
          <Form.Item label="用户">
            <Input value={resetTarget?.username || ''} disabled />
          </Form.Item>
          <Form.Item label="新密码" name="password" rules={[{ required: true, message: '请输入新密码' }]}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
