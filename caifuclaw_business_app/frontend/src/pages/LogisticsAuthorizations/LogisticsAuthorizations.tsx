/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { useEffect, useMemo, useState } from 'react'
import {
  CheckCircleOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined
} from '@ant-design/icons'
import { App, Button, Checkbox, Form, Input, InputNumber, Modal, Select, Space, Spin, Switch, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DataTable } from '@/components/DataTable'
import type { DataTableConfig } from '@/components/DataTable'
import {
  getLogisticsAuthorization,
  getLogisticsAuthorizationCredentials,
  listLogisticsAuthorizations,
  toggleLogisticsAuthorization,
  updateLogisticsAuthorization,
  verifyLogisticsAuthorization,
  type LogisticsAuthorizationDto
} from '@/api/logisticsAuthorizations'
import { formatTime } from '@/utils/format'
import { shouldIgnoreTableRowDoubleClick } from '@/utils/tableInteractions'
import './LogisticsAuthorizations.less'

type FieldKind = 'text' | 'password' | 'number' | 'boolean'

interface CredentialField {
  key: string
  label: string
  kind?: FieldKind
  required?: boolean
  placeholder?: string
}

interface CarrierSchema {
  carrierCode: string
  carrierName: string
  accountLabel: string
  credentialFields: CredentialField[]
  configFields: CredentialField[]
  labelConfig?: boolean
}

interface FilterValues {
  carrier_name?: string
  carrier_code?: string
  enabled?: boolean
}

interface DetailFormValues {
  carrier_code: string
  account_name: string
  enabled: boolean
  credential_type: string
  credentials: Record<string, string>
  config_json: {
    company_name_en?: string
    same_address_doorplate?: boolean
    auto_recipient_phone?: string
    auto_recipient_email?: string
    label_fields?: string[]
    base_url?: string
    warehouse_code?: string
    shipping_method?: string
    item_type?: string
    with_battery_type?: string
    default_weight_kg?: string
    length_cm?: string
    width_cm?: string
    height_cm?: string
    default_declared_name_en?: string
    default_declared_name_cn?: string
    default_declared_value?: string
    default_declared_currency?: string
    default_hs_code?: string
    production_company_name?: string
    production_company_uscc?: string
    auto_confirm?: boolean
    auto_create_drafts?: boolean
    callback_url?: string
    poland_channel_id?: number
    poland_channel_name?: string
    pan_eu_channel_id?: number
    pan_eu_channel_name?: string
  }
  authorization_expires_at?: string | null
}

const LABEL_FIELD_OPTIONS = [
  { label: '商品编号', value: 'product_code' },
  { label: '商品名称', value: 'product_name' },
  { label: '商品数量', value: 'quantity' },
  { label: '备注', value: 'remark' },
  { label: '仓库', value: 'warehouse' },
  { label: '仓位', value: 'location' },
  { label: '平台sku', value: 'platform_sku' }
]

const CARRIER_SCHEMAS: CarrierSchema[] = [
  {
    carrierCode: 'qianhai_weishi',
    carrierName: '深圳前海纬狮物流网络科技有限公司',
    accountLabel: '账户',
    credentialFields: [
      { key: 'token', label: '令牌', kind: 'password', required: true },
      { key: 'account', label: '账户', required: true }
    ],
    configFields: [
      { key: 'company_name_en', label: '物流公司名称(英文)', placeholder: '仅用于同步 magento, Woocommerce, shopline' },
      { key: 'auto_recipient_phone', label: '自动填写收件人电话' },
      { key: 'auto_recipient_email', label: '自动填写收件人邮箱' }
    ]
  },
  {
    carrierCode: 'wanbang_suda_new',
    carrierName: '万邦速达(新)',
    accountLabel: '客户代码',
    credentialFields: [
      { key: 'customer_code', label: '客户代码', required: true },
      { key: 'token', label: '令牌', kind: 'password', required: true }
    ],
    configFields: [
      { key: 'company_name_en', label: '物流公司名称(英文)' },
      { key: 'base_url', label: '万邦 API 地址', placeholder: 'https://api.wanbexpress.com' },
      { key: 'warehouse_code', label: '万邦仓库代码', required: true },
      { key: 'shipping_method', label: '万邦渠道代码', required: true },
      { key: 'item_type', label: '包裹类型', placeholder: '默认 SPX' },
      { key: 'with_battery_type', label: '电池类型', placeholder: '默认 NOBattery' },
      { key: 'default_weight_kg', label: '默认重量(kg)', placeholder: '0.2' },
      { key: 'length_cm', label: '长(cm)', placeholder: '1' },
      { key: 'width_cm', label: '宽(cm)', placeholder: '1' },
      { key: 'height_cm', label: '高(cm)', placeholder: '1' },
      { key: 'default_declared_name_en', label: '默认英文品名', placeholder: 'goods' },
      { key: 'default_declared_name_cn', label: '默认中文品名', placeholder: 'goods' },
      { key: 'default_declared_value', label: '默认申报单价', placeholder: '1' },
      { key: 'default_declared_currency', label: '申报币种', placeholder: 'USD' },
      { key: 'default_hs_code', label: '默认 HS Code' },
      { key: 'production_company_name', label: '生产/销售企业名称' },
      { key: 'production_company_uscc', label: '生产/销售企业统一信用代码' },
      { key: 'auto_recipient_phone', label: '自动填写收件人电话' },
      { key: 'auto_recipient_email', label: '自动填写收件人邮箱' }
    ],
    labelConfig: true
  },
  {
    carrierCode: 'bsi_overseas',
    carrierName: 'BSI海外仓',
    accountLabel: '客户代码',
    credentialFields: [
      { key: 'customer_code', label: 'CustomerCode', required: true },
      { key: 'app_id', label: 'AppId', required: true },
      { key: 'customer_secret', label: 'CustomerSecret', kind: 'password', required: true }
    ],
    configFields: [
      { key: 'auto_create_drafts', label: '自动创建备货草稿', kind: 'boolean' },
      { key: 'base_url', label: 'SDMS 正式地址', required: true, placeholder: 'https://gateway.gotofreight.com/sdmspanel' },
      { key: 'warehouse_code', label: 'WarehouseCode', required: true, placeholder: 'DEMO-WAREHOUSE' },
      { key: 'callback_url', label: '订单状态回调地址', required: true, placeholder: 'https://auth.example.invalid/api/logistics/bsi/callback/...' },
      { key: 'poland_channel_id', label: '波兰渠道 ID', kind: 'number', required: true, placeholder: '1061' },
      { key: 'poland_channel_name', label: '波兰渠道名称', placeholder: '校验授权后自动更新' },
      { key: 'pan_eu_channel_id', label: '泛欧预付渠道 ID', kind: 'number', required: true, placeholder: '3102' },
      { key: 'pan_eu_channel_name', label: '泛欧预付渠道名称', placeholder: '校验授权后自动更新' }
    ]
  }
]

const CARRIER_OPTIONS = CARRIER_SCHEMAS.map((schema) => ({
  value: schema.carrierCode,
  label: schema.carrierName
}))

const TABLE_CONFIG: DataTableConfig = {
  tableKey: 'logistics-authorizations.list',
  primaryColumnKey: 'carrier_name',
  widthMode: 'adaptive-left',
  columns: [
    { key: 'carrier_name', title: '物流公司', required: true, fixed: 'left', minWidth: 220 },
    { key: 'account_name', title: '授权账号' },
    { key: 'carrier_code', title: '物流编码' },
    { key: 'enabled', title: '启用状态' },
    { key: 'authorization_status', title: '授权状态' },
    { key: 'token_message', title: '授权提示' },
    { key: 'last_authorized_at', title: '最后授权时间' },
    { key: 'updated_at', title: '更新时间' },
    { key: 'actions', title: '操作', settingsHidden: true, fixed: 'right', protectedWidth: 190 }
  ]
}

function schemaFor(code?: string): CarrierSchema {
  return CARRIER_SCHEMAS.find((schema) => schema.carrierCode === code) || CARRIER_SCHEMAS[0]
}

function authStatusLabel(value?: string) {
  if (value === 'success') return '已授权'
  if (value === 'failed') return '授权异常'
  if (value === 'expired') return '已过期'
  return '未授权'
}

function authStatusColor(value?: string) {
  if (value === 'success') return 'success'
  if (value === 'failed' || value === 'expired') return 'error'
  return 'default'
}

function rowIdentity(row: LogisticsAuthorizationDto) {
  return `${row.carrier_name || row.carrier_code}-${row.account_name || row.id}`
}

function accountNameFromCredentials(schema: CarrierSchema, credentials: Record<string, string> = {}) {
  const accountField = schema.credentialFields.find((field) => field.kind !== 'password')
  if (!accountField) return ''
  return String(credentials[accountField.key] || '').trim()
}

function detailFormValues(row?: LogisticsAuthorizationDto | null, credentials: Record<string, string> = {}): DetailFormValues {
  const schema = schemaFor(row?.carrier_code)
  return {
    carrier_code: row?.carrier_code || schema.carrierCode,
    account_name: row?.account_name || accountNameFromCredentials(schema, credentials),
    enabled: row?.enabled ?? true,
    credential_type: row?.credential_type || 'api_key',
    credentials,
    config_json: {
      ...(row?.config_json || {}),
      company_name_en: String(row?.config_json?.company_name_en || ''),
      same_address_doorplate: Boolean(row?.config_json?.same_address_doorplate),
      auto_recipient_phone: String(row?.config_json?.auto_recipient_phone || ''),
      auto_recipient_email: String(row?.config_json?.auto_recipient_email || ''),
      label_fields: Array.isArray(row?.config_json?.label_fields) ? (row?.config_json?.label_fields as string[]) : []
    },
    authorization_expires_at: row?.authorization_expires_at || null
  }
}

function fieldInput(field: CredentialField) {
  if (field.kind === 'password') return <Input.Password placeholder={field.placeholder} />
  if (field.kind === 'number') {
    return <InputNumber min={1} precision={0} placeholder={field.placeholder} style={{ width: '100%' }} />
  }
  if (field.kind === 'boolean') return <Switch checkedChildren="启用" unCheckedChildren="停用" />
  return <Input placeholder={field.placeholder} />
}

export function LogisticsAuthorizations() {
  const { message, modal } = App.useApp()
  const [filterForm] = Form.useForm<FilterValues>()
  const [detailForm] = Form.useForm<DetailFormValues>()
  const [loading, setLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [rows, setRows] = useState<LogisticsAuthorizationDto[]>([])
  const [detail, setDetail] = useState<LogisticsAuthorizationDto | null>(null)
  const [editorOpen, setEditorOpen] = useState(false)
  const [submittedFilters, setSubmittedFilters] = useState<FilterValues>({})
  const activeCarrierCode = Form.useWatch('carrier_code', detailForm) || detail?.carrier_code
  const activeSchema = schemaFor(activeCarrierCode)

  async function loadList(values: FilterValues = submittedFilters) {
    setLoading(true)
    try {
      const data = await listLogisticsAuthorizations(values)
      setRows(data)
    } finally {
      setLoading(false)
    }
  }

  async function loadDetail(id: number) {
    setDetailLoading(true)
    try {
      const [data, credentials] = await Promise.all([
        getLogisticsAuthorization(id),
        getLogisticsAuthorizationCredentials(id)
      ])
      setDetail(data)
      detailForm.setFieldsValue(detailFormValues(data, credentials))
    } finally {
      setDetailLoading(false)
    }
  }

  useEffect(() => {
    void loadList()
  }, [])

  const columns = useMemo<ColumnsType<LogisticsAuthorizationDto>>(
    () => [
      { title: '物流公司', dataIndex: 'carrier_name', minWidth: 220, maxWidth: 320, ellipsis: true },
      { title: '授权账号', dataIndex: 'account_name', minWidth: 130, maxWidth: 220, ellipsis: true },
      { title: '物流编码', dataIndex: 'carrier_code', minWidth: 150, maxWidth: 220, ellipsis: true },
      {
        title: '启用状态',
        dataIndex: 'enabled',
        minWidth: 96,
        maxWidth: 120,
        render: (value) => <Tag color={value ? 'success' : 'default'}>{value ? '启用' : '停用'}</Tag>
      },
      {
        title: '授权状态',
        dataIndex: 'authorization_status',
        minWidth: 110,
        maxWidth: 130,
        render: (value) => <Tag color={authStatusColor(value)}>{authStatusLabel(value)}</Tag>
      },
      { title: '授权提示', dataIndex: 'token_message', minWidth: 150, maxWidth: 260, ellipsis: true },
      { title: '最后授权时间', dataIndex: 'last_authorized_at', minWidth: 168, maxWidth: 190, render: (value) => formatTime(value, true) },
      { title: '更新时间', dataIndex: 'updated_at', minWidth: 168, maxWidth: 190, render: (value) => formatTime(value, true) },
      {
        title: '操作',
        key: 'actions',
        width: 190,
        fixed: 'right',
        render: (_, row) => (
          <Space size={4}>
            <Button type="link" size="small" onClick={() => openEdit(row)}>
              编辑授权
            </Button>
            <Button type="link" size="small" onClick={() => onToggleEnabled(row)}>
              {row.enabled ? '停用' : '启用'}
            </Button>
          </Space>
        )
      }
    ],
    []
  )

  async function submitFilters(values: FilterValues) {
    setSubmittedFilters(values)
    await loadList(values)
  }

  async function onToggleEnabled(row: LogisticsAuthorizationDto) {
    const action = row.enabled ? '停用' : '启用'
    modal.confirm({
      title: '状态切换',
      content: `确认${action}物流授权「${rowIdentity(row)}」吗？`,
      okText: action,
      cancelText: '取消',
      onOk: async () => {
        await toggleLogisticsAuthorization(row.id)
        message.success(`物流授权已${action}`)
        await loadList()
      }
    })
  }

  async function openEdit(row: LogisticsAuthorizationDto) {
    setDetail(row)
    detailForm.resetFields()
    detailForm.setFieldsValue(detailFormValues(row, {}))
    setEditorOpen(true)
    await loadDetail(row.id)
  }

  function closeEditor() {
    setEditorOpen(false)
    setDetail(null)
    detailForm.resetFields()
  }

  async function saveDetail() {
    const values = await detailForm.validateFields()
    const currentDetailId = detail?.id
    if (!currentDetailId) {
      message.warning('授权信息加载完成后再保存')
      return
    }
    setSaving(true)
    try {
      const selectedSchema = schemaFor(values.carrier_code)
      const accountName = accountNameFromCredentials(selectedSchema, values.credentials || {})
      const payload = {
        carrier_code: values.carrier_code,
        carrier_name: selectedSchema.carrierName,
        account_name: accountName,
        enabled: values.enabled,
        credential_type: values.credential_type || 'api_key',
        credentials: values.credentials || {},
        config_json: values.config_json || {},
        settings_json: detail?.settings_json || {},
        authorization_expires_at: values.authorization_expires_at || null
      }
      const saved = await updateLogisticsAuthorization(currentDetailId, payload)
      message.success('物流授权已保存')
      setDetail(saved)
      const credentials = await getLogisticsAuthorizationCredentials(saved.id)
      detailForm.setFieldsValue(detailFormValues(saved, credentials))
      setEditorOpen(false)
      await loadList()
    } finally {
      setSaving(false)
    }
  }

  async function verifyDetail() {
    const currentDetailId = detail?.id
    if (!currentDetailId) {
      message.warning('请先保存授权信息')
      return
    }
    setVerifying(true)
    try {
      const result = await verifyLogisticsAuthorization(currentDetailId)
      message[result.token_valid ? 'success' : 'warning'](result.token_message)
      await loadDetail(currentDetailId)
    } finally {
      setVerifying(false)
    }
  }

  return (
    <div className="page-card logistics-auth-page">
      <div className="orders-header">
        <h2>物流授权</h2>
      </div>

      <Form form={filterForm} name="logisticsAuthorizationFilters" layout="inline" className="orders-filter" onFinish={submitFilters}>
        <Form.Item label="物流公司" name="carrier_name">
          <Input allowClear placeholder="输入物流公司/账号" style={{ width: 220 }} />
        </Form.Item>
        <Form.Item label="物流编码" name="carrier_code">
          <Select allowClear placeholder="全部物流公司" style={{ width: 220 }} options={CARRIER_OPTIONS} />
        </Form.Item>
        <Form.Item label="状态" name="enabled">
          <Select
            allowClear
            placeholder="全部状态"
            style={{ width: 140 }}
            options={[
              { value: true, label: '启用' },
              { value: false, label: '停用' }
            ]}
          />
        </Form.Item>
        <Form.Item>
          <Space>
            <Button type="primary" htmlType="submit">
              查询
            </Button>
            <Button
              onClick={() => {
                filterForm.resetFields()
                setSubmittedFilters({})
                void loadList({})
              }}
            >
              重置
            </Button>
          </Space>
        </Form.Item>
      </Form>

      <DataTable
        rowKey="id"
        loading={loading}
        dataSource={rows}
        columns={columns}
        pagination={false}
        tableConfig={TABLE_CONFIG}
        fitContentColumns
        onRow={(row) => ({
          onDoubleClick: (event) => {
            if (shouldIgnoreTableRowDoubleClick(event.target)) return
            void openEdit(row)
          }
        })}
      />

      <Modal
        open={editorOpen}
        title={
          <div className="logistics-auth-title">
            <span className="logistics-auth-title__icon">
              <SafetyCertificateOutlined />
            </span>
            <div>
              <h2>{detail?.carrier_name || '编辑物流授权'}</h2>
              <p>{activeSchema.accountLabel}授权信息维护</p>
            </div>
          </div>
        }
        width="min(1040px, calc(100vw - 32px))"
        centered
        maskClosable={false}
        keyboard={false}
        className="logistics-auth-modal"
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        onOk={saveDetail}
        onCancel={closeEditor}
        footer={(_, { OkBtn, CancelBtn }) => (
          <div className="logistics-auth-modal__footer">
            <Button icon={<ReloadOutlined />} loading={verifying} onClick={verifyDetail}>
              校验授权
            </Button>
            <Space>
              <CancelBtn />
              <OkBtn />
            </Space>
          </div>
        )}
      >
        <Spin spinning={detailLoading}>
          <Form
            form={detailForm}
            name="logisticsAuthorizationEditor"
            layout="horizontal"
            labelCol={{ flex: '132px' }}
            wrapperCol={{ flex: 1 }}
            colon={false}
            className="logistics-auth-form"
            preserve
          >
            <section className="logistics-auth-section">
              <div className="logistics-auth-section__title">基础信息</div>
              <div className="logistics-auth-grid">
                <Form.Item label="物流公司" name="carrier_code" rules={[{ required: true, message: '请选择物流公司' }]}>
                  <Select disabled options={CARRIER_OPTIONS} />
                </Form.Item>
                <Form.Item label="启用状态" name="enabled" valuePropName="checked">
                  <Switch checkedChildren="启用" unCheckedChildren="停用" />
                </Form.Item>
              </div>
            </section>

            <section className="logistics-auth-section">
              <div className="logistics-auth-section__title">授权信息</div>
              <div className="logistics-auth-grid">
                <Form.Item name="credential_type" hidden>
                  <Input />
                </Form.Item>
                {activeSchema.credentialFields.map((field) => (
                  <Form.Item
                    key={field.key}
                    label={field.label}
                    name={['credentials', field.key]}
                    rules={field.required ? [{ required: true, message: `请输入${field.label}` }] : undefined}
                  >
                    {fieldInput(field)}
                  </Form.Item>
                ))}
              </div>
            </section>

            {activeSchema.labelConfig ? (
              <section className="logistics-auth-section">
                <div className="logistics-auth-section__title">官方标签配置</div>
                <Form.Item label="标签配置信息" name={['config_json', 'label_fields']}>
                  <Checkbox.Group options={LABEL_FIELD_OPTIONS} />
                </Form.Item>
              </section>
            ) : null}

            <section className="logistics-auth-section">
              <div className="logistics-auth-section__title">交运补充配置</div>
              <Form.Item label="门牌号配置" name={['config_json', 'same_address_doorplate']} valuePropName="checked">
                <Checkbox>同意当邮寄地址/备用地址含门牌号时，无需单独推送门牌号信息</Checkbox>
              </Form.Item>
              <div className="logistics-auth-grid">
                {activeSchema.configFields.map((field) => (
                  <Form.Item
                    key={field.key}
                    label={field.label}
                    name={['config_json', field.key]}
                    valuePropName={field.kind === 'boolean' ? 'checked' : undefined}
                    rules={field.required ? [{ required: true, message: `请输入${field.label}` }] : undefined}
                  >
                    {fieldInput(field)}
                  </Form.Item>
                ))}
              </div>
            </section>

            {detail ? (
              <section className="logistics-auth-status">
                <Tag color={authStatusColor(detail.authorization_status)} icon={detail.authorization_status === 'success' ? <CheckCircleOutlined /> : undefined}>
                  {authStatusLabel(detail.authorization_status)}
                </Tag>
                <span>{detail.token_message || '未验证'}</span>
                <span>最后授权：{formatTime(detail.last_authorized_at, true)}</span>
              </section>
            ) : null}
          </Form>
        </Spin>
      </Modal>
    </div>
  )
}
