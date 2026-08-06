/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { useEffect, useMemo, useState } from 'react'
import { CloseOutlined, CopyOutlined, DeleteOutlined, EditOutlined, PlusOutlined, SaveOutlined } from '@ant-design/icons'
import { App, Button, Checkbox, Empty, Form, Input, Space } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DataTable } from '@/components/DataTable'
import { createRole, deleteRole, listRoles, updateRole, type RoleDto } from '@/api/users'
import { flattenMenus, menus, type MenuItem } from '@/menus'

interface RoleFormValues {
  name?: string
}

interface RoleDraft {
  name?: string
  menus: string[]
}

interface PermissionRow {
  key: string
  menu: string
  submenu: string
  rowSpan: number
  isGroupStart: boolean
}

function roleLabel(role?: Pick<RoleDto, 'code' | 'name'> | null) {
  if (role?.code === 'admin') return '超级管理员'
  return role?.name || '-'
}

function normalizeMenuCode(code: string) {
  return code === 'order-outbound' ? 'outbound-scans' : code
}

function normalizeMenuCodes(codes?: string[]) {
  return Array.from(new Set((codes || []).map(normalizeMenuCode)))
}

export function Permissions() {
  const { message, modal } = App.useApp()
  const [roleForm] = Form.useForm<RoleFormValues>()
  const [roles, setRoles] = useState<RoleDto[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [selectedRoleId, setSelectedRoleId] = useState<number | 'new' | null>(null)
  const [mode, setMode] = useState<'preview' | 'edit' | 'create'>('preview')
  const [draftRole, setDraftRole] = useState<RoleDraft | null>(null)
  const [selectedMenus, setSelectedMenus] = useState<string[]>([])

  const permissionMenus = useMemo(
    () =>
      flattenMenus(menus)
        .filter((item) => !item.hideInMenu && !item.children?.length)
        .map((item) => ({ ...item, code: normalizeMenuCode(item.code) })),
    []
  )
  const permissionRows = useMemo<PermissionRow[]>(() => {
    const toAssignable = (items?: MenuItem[]) =>
      (items || [])
        .filter((item) => !item.hideInMenu && !item.children?.length)
        .map((item) => ({ ...item, code: normalizeMenuCode(item.code) }))
    return menus.flatMap((item) => {
      const children = item.children?.length ? toAssignable(item.children) : toAssignable([item])

      return children.map((child, index) => ({
        key: child.code,
        menu: item.title,
        submenu: child.title,
        rowSpan: index === 0 ? children.length : 0,
        isGroupStart: index === 0
      }))
    })
  }, [])
  const selectedRole = useMemo(
    () => (typeof selectedRoleId === 'number' ? roles.find((role) => role.id === selectedRoleId) || null : null),
    [roles, selectedRoleId]
  )
  const isAdminRole = selectedRole?.code === 'admin'
  const isEditable = (mode === 'create' || mode === 'edit') && !isAdminRole
  const canOperateSelected = Boolean(selectedRole && selectedRole.code !== 'admin' && mode === 'preview')
  const checkedMenuCodes = isAdminRole ? permissionMenus.map((item) => item.code) : selectedMenus

  async function load() {
    setLoading(true)
    try {
      const nextRoles = await listRoles()
      setRoles(nextRoles || [])
      setSelectedRoleId((current) => {
        if (current === 'new') return current
        if (current && nextRoles?.some((role) => role.id === current)) return current
        return nextRoles?.[0]?.id ?? null
      })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  useEffect(() => {
    if (selectedRoleId === 'new') {
      roleForm.resetFields()
      roleForm.setFieldsValue({
        name: draftRole?.name || ''
      })
      setSelectedMenus(normalizeMenuCodes(draftRole?.menus))
      return
    }
    if (selectedRole) {
      roleForm.setFieldsValue({
        name: selectedRole.name
      })
      setSelectedMenus(normalizeMenuCodes(selectedRole.menus))
      return
    }
    setSelectedMenus([])
  }, [draftRole, roleForm, selectedRole, selectedRoleId])

  function openCreateRole() {
    setDraftRole({ name: '', menus: [] })
    setSelectedRoleId('new')
    setMode('create')
  }

  function openCopyRole() {
    if (!selectedRole || selectedRole.code === 'admin') return
    setDraftRole({
      name: `${selectedRole.name}副本`,
      menus: normalizeMenuCodes(selectedRole.menus)
    })
    setSelectedRoleId('new')
    setMode('create')
  }

  function openEditRole() {
    if (!selectedRole || selectedRole.code === 'admin') return
    setDraftRole(null)
    setMode('edit')
  }

  function cancelEditing() {
    setDraftRole(null)
    setMode('preview')
    if (selectedRoleId === 'new') {
      setSelectedRoleId(roles[0]?.id ?? null)
      return
    }
    if (selectedRole) {
      roleForm.setFieldsValue({
        name: selectedRole.name
      })
      setSelectedMenus(normalizeMenuCodes(selectedRole.menus))
    }
  }

  function selectRole(roleId: number) {
    if (mode !== 'preview') return
    setDraftRole(null)
    setSelectedRoleId(roleId)
  }

  function roleNameEditor(disabled = false) {
    return (
      <Form.Item name="name" rules={[{ required: true, message: '请输入角色名称' }]}>
        <Input autoFocus={!disabled} disabled={disabled} placeholder="角色名称" />
      </Form.Item>
    )
  }

  function setMenus(nextMenus: string[]) {
    if (!isEditable) return
    setSelectedMenus(Array.from(new Set(nextMenus)))
  }

  function setMenuChecked(code: string, checked: boolean) {
    const current = selectedMenus || []
    setMenus(checked ? [...current, code] : current.filter((item) => item !== code))
  }

  function roleInternalCode(name: string) {
    const suffix = Date.now().toString(36)
    const normalized = name
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9_-]+/g, '_')
      .replace(/^_+|_+$/g, '')
      .slice(0, 48)
    return `role_${normalized || suffix}_${suffix}`
  }

  async function saveRole() {
    const values = await roleForm.validateFields()
    const name = values.name?.trim() || ''
    if (!name) {
      message.warning('请输入角色名称')
      return
    }
    const finalMenus = selectedMenus
    let createdRoleId: number | null = null
    setSaving(true)
    try {
      if (mode === 'create') {
        const created = await createRole({
          code: roleInternalCode(name),
          name,
          description: name,
          enabled: true,
          menus: finalMenus
        })
        createdRoleId = created.id
      } else if (selectedRole && selectedRole.code !== 'admin') {
        await updateRole(selectedRole.id, {
          name,
          description: selectedRole.description || '',
          enabled: selectedRole.enabled,
          menus: finalMenus
        })
      }
      message.success('已保存')
      await load()
      setDraftRole(null)
      setMode('preview')
      if (createdRoleId) setSelectedRoleId(createdRoleId)
    } finally {
      setSaving(false)
    }
  }

  function onDeleteRole(row: RoleDto) {
    modal.confirm({
      title: '删除确认',
      content: `确认删除角色「${row.name}」？`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        await deleteRole(row.id)
        message.success('已删除')
        setMode('preview')
        setDraftRole(null)
        setSelectedRoleId(null)
        await load()
      }
    })
  }

  const permissionColumns: ColumnsType<PermissionRow> = [
    {
      title: '菜单',
      dataIndex: 'menu',
      width: '32%',
      onCell: (row) => ({ rowSpan: row.rowSpan }),
      render: (value: string, row) =>
        row.rowSpan ? <span className="permission-table__menu-cell">- {value}</span> : value
    },
    {
      title: '子菜单',
      dataIndex: 'submenu',
      width: '36%'
    },
    {
      title: '权限',
      key: 'permission',
      render: (_, row) => (
        <Checkbox
          checked={checkedMenuCodes.includes(row.key)}
          disabled={!isEditable}
          onChange={(event) => setMenuChecked(row.key, event.target.checked)}
        >
          可访问
        </Checkbox>
      )
    }
  ]

  return (
    <div className="page-card users-page permissions-page">
      <section className="users-page__section users-page__section--roles">
        <div className="users-page__section-header">
          <h2>权限管理</h2>
          <Space className="role-maintenance__toolbar">
            {mode === 'preview' ? (
              <>
                <Button type="primary" icon={<PlusOutlined />} onClick={openCreateRole}>
                  新建
                </Button>
                <Button icon={<CopyOutlined />} disabled={!canOperateSelected} onClick={openCopyRole}>
                  复制
                </Button>
                <Button icon={<EditOutlined />} disabled={!canOperateSelected} onClick={openEditRole}>
                  编辑
                </Button>
                <Button danger icon={<DeleteOutlined />} disabled={!canOperateSelected} onClick={() => selectedRole && onDeleteRole(selectedRole)}>
                  删除
                </Button>
              </>
            ) : (
              <>
                <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={saveRole}>
                  保存
                </Button>
                <Button icon={<CloseOutlined />} disabled={saving} onClick={cancelEditing}>
                  取消
                </Button>
              </>
            )}
          </Space>
        </div>

        <Form form={roleForm} preserve={false} component={false}>
          <div className="role-maintenance">
            <aside className="role-maintenance__list">
              <div className="role-maintenance__list-title">角色</div>
              {selectedRoleId === 'new' ? (
                <div className="role-maintenance__item is-active role-maintenance__item--editing">
                  {roleNameEditor()}
                </div>
              ) : null}
              {roles.map((role) => (
                selectedRoleId === role.id && mode === 'edit' ? (
                  <div className="role-maintenance__item is-active role-maintenance__item--editing" key={role.id}>
                    {roleNameEditor(!isEditable)}
                  </div>
                ) : (
                  <button
                    type="button"
                    key={role.id}
                    className={`role-maintenance__item${selectedRoleId === role.id ? ' is-active' : ''}`}
                    disabled={mode !== 'preview'}
                    onClick={() => selectRole(role.id)}
                  >
                    <span className="role-maintenance__item-name">{roleLabel(role)}</span>
                  </button>
                )
              ))}
            </aside>

            <main className="role-maintenance__detail" aria-busy={loading}>
              {selectedRoleId ? (
                <DataTable
                  className="permission-table"
                  rowKey="key"
                  columns={permissionColumns}
                  dataSource={permissionRows}
                  pagination={false}
                  size="middle"
                  bordered
                  scroll={{ y: 'calc(100vh - 236px)' }}
                  rowClassName={(row) => (row.isGroupStart ? 'permission-table__group-start' : '')}
                />
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </main>
          </div>
        </Form>
      </section>
    </div>
  )
}
