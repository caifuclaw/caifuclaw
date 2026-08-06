import { useEffect, useMemo, useState } from 'react'
import {
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined
} from '@ant-design/icons'
import { App, Button, Form, Input, InputNumber, Modal, Select, Space, Switch, Tag } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import { DataTable } from '@/components/DataTable'
import type { DataTableConfig } from '@/components/DataTable'
import {
  createLogisticsRule,
  deleteLogisticsRule,
  listLogisticsChannelOptions,
  listLogisticsRules,
  rematchLogisticsRules,
  toggleLogisticsRule,
  updateLogisticsRule,
  type LogisticsChannelOptionDto,
  type LogisticsMatchRuleDto,
  type LogisticsMatchRulePayload
} from '@/api/logisticsRules'
import { listShops, type ShopDto } from '@/api/shops'
import { useEnabledPlatformOptions, type EnabledPlatformOption } from '@/hooks/useEnabledPlatformOptions'
import { formatTime } from '@/utils/format'
import { shouldIgnoreTableRowDoubleClick } from '@/utils/tableInteractions'
import './LogisticsRules.less'

interface FilterValues {
  name?: string
  platform?: string
  enabled?: boolean
}

interface RuleFormValues {
  name: string
  platform: string
  priority: number
  enabled: boolean
  shop_names: string[]
  is_overseas_warehouse: 'all' | boolean
  country_codes: string[]
  logistics_channel: string
  remark?: string
}

const TABLE_CONFIG: DataTableConfig = {
  tableKey: 'logistics-rules.list',
  primaryColumnKey: 'name',
  widthMode: 'adaptive-left',
  columns: [
    { key: 'name', title: '规则名称', required: true, fixed: 'left', minWidth: 180, maxWidth: 260 },
    { key: 'platform', title: '平台', minWidth: 120, maxWidth: 160 },
    { key: 'priority', title: '优先级', minWidth: 80, maxWidth: 100 },
    { key: 'shop_names', title: '来源店铺', minWidth: 220, maxWidth: 360 },
    { key: 'is_overseas_warehouse', title: '是否海外仓', minWidth: 100, maxWidth: 120 },
    { key: 'country_codes', title: '目的国家', minWidth: 140, maxWidth: 240 },
    { key: 'logistics_channel', title: '物流渠道', minWidth: 160, maxWidth: 260 },
    { key: 'enabled', title: '状态', minWidth: 88, maxWidth: 110 },
    { key: 'updated_at', title: '更新时间', minWidth: 150, maxWidth: 180 },
    { key: 'actions', title: '操作', fixed: 'right', protectedWidth: 220, settingsHidden: true }
  ]
}

const COUNTRY_OPTIONS = [
  { value: 'CN', label: '中国(CN)' },
  { value: 'RU', label: '俄罗斯(RU)' },
  { value: 'BY', label: '白俄罗斯(BY)' },
  { value: 'KZ', label: '哈萨克斯坦(KZ)' },
  { value: 'PL', label: '波兰(PL)' },
  { value: 'US', label: '美国(US)' },
  { value: 'BR', label: '巴西(BR)' },
  { value: 'MX', label: '墨西哥(MX)' },
  { value: 'DE', label: '德国(DE)' },
  { value: 'FR', label: '法国(FR)' },
  { value: 'ES', label: '西班牙(ES)' },
  { value: 'IT', label: '意大利(IT)' }
]

const countryLabelByCode = new Map(COUNTRY_OPTIONS.map((item) => [item.value, item.label]))

function normalizeCountryCode(value: string) {
  return value.trim().toUpperCase()
}

function tags(values: string[], emptyText = '不限制') {
  const list = values || []
  if (!list.length) return <span className="logistics-rule-condition__empty">{emptyText}</span>
  return (
    <span className="logistics-rule-condition">
      {list.map((value) => (
        <Tag key={value}>{countryLabelByCode.get(value) || value}</Tag>
      ))}
    </span>
  )
}

function platformLabel(platforms: EnabledPlatformOption[], value?: string) {
  if (!value) return '-'
  return platforms.find((item) => item.value === value)?.label || value
}

const PLATFORM_ALIASES: Record<string, string> = {
  joom: 'joom_logistics',
  joomlogistics: 'joom_logistics',
  mercado: 'mercadolibre',
  mercado_global: 'mercadolibre',
  mercadoglobal: 'mercadolibre',
  mercado_libre: 'mercadolibre',
  tiktok: 'tiktok_shop',
  tiktokshop: 'tiktok_shop',
  ali_express: 'aliexpress',
  shopify_admin: 'shopify',
  ebay_sell: 'ebay',
  walmart_marketplace: 'walmart',
  shein_open: 'shein',
  coupang_openapi: 'coupang',
  wayfair_partner: 'wayfair',
  dms_matrix: 'dmsmatrix',
  'dms-matrix': 'dmsmatrix',
  dms_matrix_erp: 'dmsmatrix',
  dmsmatrix_erp: 'dmsmatrix'
}

function normalizePlatform(value?: string | null) {
  const normalized = (value || '').trim().toLowerCase()
  return PLATFORM_ALIASES[normalized] || normalized
}

function shopOptionText(shop: ShopDto) {
  return (shop.display_name || shop.account_id || shop.shop_id || '').trim()
}

function shopOptionLabel(shop: ShopDto) {
  const displayName = (shop.display_name || '').trim()
  const accountId = (shop.account_id || shop.shop_id || '').trim()
  return displayName || accountId
}

function logisticsChannelDisplayName(option: LogisticsChannelOptionDto) {
  return (option.carrier_name || option.value || option.label || '').trim()
}

function ruleToForm(row?: LogisticsMatchRuleDto | null): RuleFormValues {
  return {
    name: row?.name || '',
    platform: row?.platform || '',
    priority: row?.priority ?? 10,
    enabled: row?.enabled ?? true,
    shop_names: row?.shop_names || [],
    is_overseas_warehouse: row?.is_overseas_warehouse ?? 'all',
    country_codes: row?.country_codes || [],
    logistics_channel: row?.logistics_channel || '',
    remark: row?.remark || ''
  }
}

function formToPayload(values: RuleFormValues): LogisticsMatchRulePayload {
  return {
    name: values.name?.trim() || '',
    platform: values.platform || '',
    priority: Number(values.priority || 10),
    enabled: Boolean(values.enabled),
    shop_names: values.shop_names || [],
    is_overseas_warehouse: values.is_overseas_warehouse === 'all' ? null : values.is_overseas_warehouse,
    country_codes: (values.country_codes || []).map(normalizeCountryCode).filter(Boolean),
    logistics_channel: values.logistics_channel?.trim() || '',
    remark: values.remark?.trim() || ''
  }
}

export function LogisticsRules() {
  const { message, modal } = App.useApp()
  const [filterForm] = Form.useForm<FilterValues>()
  const [ruleForm] = Form.useForm<RuleFormValues>()
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [rematching, setRematching] = useState(false)
  const [rows, setRows] = useState<LogisticsMatchRuleDto[]>([])
  const platformOptions = useEnabledPlatformOptions()
  const [shops, setShops] = useState<ShopDto[]>([])
  const [logisticsChannelOptions, setLogisticsChannelOptions] = useState<LogisticsChannelOptionDto[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [submittedFilters, setSubmittedFilters] = useState<FilterValues>({})
  const [editing, setEditing] = useState<LogisticsMatchRuleDto | null>(null)
  const [editorOpen, setEditorOpen] = useState(false)
  const selectedPlatform = Form.useWatch('platform', ruleForm)

  const availableShopOptions = useMemo(() => {
    const platform = normalizePlatform(selectedPlatform)
    if (!platform) return []

    const options = new Map<string, { value: string; label: string }>()
    shops
      .filter((shop) => normalizePlatform(shop.platform) === platform)
      .sort((a, b) => shopOptionLabel(a).localeCompare(shopOptionLabel(b)))
      .forEach((shop) => {
        const value = shopOptionText(shop)
        if (!value) return
        const key = value.toLowerCase()
        if (!options.has(key)) options.set(key, { value, label: shopOptionLabel(shop) || value })
      })
    return [...options.values()]
  }, [shops, selectedPlatform])
  const channelOptions = useMemo(
    () => logisticsChannelOptions.map((item) => ({ value: item.value, label: logisticsChannelDisplayName(item) })),
    [logisticsChannelOptions]
  )
  const channelValues = useMemo(() => new Set(channelOptions.map((item) => item.value)), [channelOptions])

  async function loadRules(nextPage = page, nextPageSize = pageSize, filters = submittedFilters) {
    setLoading(true)
    try {
      const data = await listLogisticsRules({
        name: filters.name,
        platform: filters.platform,
        enabled: filters.enabled,
        page: nextPage,
        page_size: nextPageSize
      })
      setRows(data.items || [])
      setTotal(data.total || 0)
      setPage(data.page || nextPage)
      setPageSize(data.page_size || nextPageSize)
    } finally {
      setLoading(false)
    }
  }

  async function loadShops() {
    const data = await listShops({}, { background: true })
    setShops(data || [])
  }

  useEffect(() => {
    void loadRules(1, pageSize, {})
    void listLogisticsChannelOptions()
      .then((data) => setLogisticsChannelOptions(data || []))
      .catch(() => setLogisticsChannelOptions([]))
    void loadShops()
      .catch(() => setShops([]))
  }, [])

  const columns = useMemo<ColumnsType<LogisticsMatchRuleDto>>(
    () => [
      { title: '规则名称', dataIndex: 'name', minWidth: 180, maxWidth: 260, ellipsis: true },
      { title: '平台', dataIndex: 'platform', minWidth: 120, maxWidth: 160, render: (value) => platformLabel(platformOptions, value) },
      { title: '优先级', dataIndex: 'priority', minWidth: 80, maxWidth: 100, align: 'right' },
      { title: '来源店铺', dataIndex: 'shop_names', minWidth: 220, maxWidth: 360, render: (value) => tags(value, '全部店铺') },
      {
        title: '是否海外仓',
        dataIndex: 'is_overseas_warehouse',
        minWidth: 100,
        maxWidth: 120,
        render: (value) => (value == null ? '全部' : value ? '是' : '否')
      },
      { title: '目的国家', dataIndex: 'country_codes', minWidth: 140, maxWidth: 240, render: (value) => tags(value, '全部国家') },
      { title: '物流渠道', dataIndex: 'logistics_channel', minWidth: 160, maxWidth: 260, ellipsis: true },
      {
        title: '状态',
        dataIndex: 'enabled',
        minWidth: 88,
        maxWidth: 110,
        render: (value) => <Tag color={value ? 'success' : 'default'}>{value ? '启用' : '停用'}</Tag>
      },
      { title: '更新时间', dataIndex: 'updated_at', minWidth: 150, maxWidth: 180, render: (value) => formatTime(value, true) },
      {
        title: '操作',
        key: 'actions',
        width: 220,
        fixed: 'right',
        render: (_, row) => (
          <Space size={4}>
            <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEditor(row)}>
              编辑
            </Button>
            <Button type="link" size="small" icon={<CopyOutlined />} onClick={() => copyRule(row)}>
              复制
            </Button>
            <Button type="link" size="small" onClick={() => onToggle(row)}>
              {row.enabled ? '停用' : '启用'}
            </Button>
            <Button danger type="link" size="small" icon={<DeleteOutlined />} onClick={() => onDelete(row)}>
              删除
            </Button>
          </Space>
        )
      }
    ],
    [platformOptions]
  )

  const pagination: TablePaginationConfig = {
    current: page,
    pageSize,
    total,
    showSizeChanger: true,
    pageSizeOptions: [50, 100, 500],
    showTotal: (value) => `共 ${value} 条`,
    onChange: (nextPage, nextPageSize) => void loadRules(nextPage, nextPageSize)
  }

  function openEditor(row?: LogisticsMatchRuleDto | null) {
    setEditing(row || null)
    ruleForm.setFieldsValue(ruleToForm(row))
    setEditorOpen(true)
  }

  function copyRule(row: LogisticsMatchRuleDto) {
    setEditing(null)
    ruleForm.setFieldsValue({
      ...ruleToForm(row),
      name: `${row.name} - 复制`,
      enabled: false
    })
    setEditorOpen(true)
  }

  async function submitFilters(values: FilterValues) {
    setSubmittedFilters(values)
    await loadRules(1, pageSize, values)
  }

  async function saveRule() {
    const values = await ruleForm.validateFields()
    const payload = formToPayload(values)
    if (!channelValues.has(payload.logistics_channel)) {
      message.error('请选择已启用的物流授权')
      return
    }
    setSaving(true)
    try {
      if (editing) await updateLogisticsRule(editing.id, payload)
      else await createLogisticsRule(payload)
      message.success('物流规则已保存')
      setEditorOpen(false)
      await loadRules()
    } finally {
      setSaving(false)
    }
  }

  async function onToggle(row: LogisticsMatchRuleDto) {
    await toggleLogisticsRule(row.id)
    message.success(row.enabled ? '物流规则已停用' : '物流规则已启用')
    await loadRules()
  }

  function onDelete(row: LogisticsMatchRuleDto) {
    modal.confirm({
      title: '删除物流规则',
      content: `确认删除「${row.name}」吗？已匹配订单会保留当前显示结果，后续重新匹配时可能变化。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        await deleteLogisticsRule(row.id)
        message.success('物流规则已删除')
        await loadRules()
      }
    })
  }

  function onRematch() {
    modal.confirm({
      title: '重新匹配未发货订单',
      content: (
        <>
          <div>系统会按当前启用规则重新匹配未发货订单。</div>
          <div className="logistics-rule-rematch-note">人工指定的物流渠道不会被覆盖。</div>
        </>
      ),
      okText: '开始匹配',
      cancelText: '取消',
      onOk: async () => {
        setRematching(true)
        try {
          const result = await rematchLogisticsRules({ include_manual: false, include_shipped: false })
          message.success(result.message || `已匹配 ${result.total} 个订单`)
        } finally {
          setRematching(false)
        }
      }
    })
  }

  return (
    <div className="page-card logistics-rules-page">
      <div className="orders-header">
        <h2>物流规则</h2>
        <Space>
          <Button icon={<ReloadOutlined />} loading={rematching} onClick={onRematch}>
            重新匹配未发货订单
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openEditor()}>
            新增物流规则
          </Button>
        </Space>
      </div>

      <Form form={filterForm} layout="inline" className="orders-filter" onFinish={submitFilters}>
        <Form.Item label="关键词" name="name">
          <Input allowClear placeholder="规则名称 / 物流渠道" style={{ width: 260 }} />
        </Form.Item>
        <Form.Item label="平台" name="platform">
          <Select allowClear placeholder="全部平台" style={{ width: 180 }} options={platformOptions} />
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
                void loadRules(1, pageSize, {})
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
        pagination={pagination}
        tableConfig={TABLE_CONFIG}
        fitContentColumns
        onRow={(row) => ({
          onDoubleClick: (event) => {
            if (shouldIgnoreTableRowDoubleClick(event.target)) return
            openEditor(row)
          }
        })}
      />

      <Modal
        open={editorOpen}
        title={editing ? '编辑物流规则' : '新增物流规则'}
        width={760}
        okText="保存"
        cancelText="取消"
        confirmLoading={saving}
        forceRender
        onOk={saveRule}
        onCancel={() => setEditorOpen(false)}
      >
        <Form form={ruleForm} layout="vertical" preserve={false}>
          <div className="logistics-rule-form-grid">
            <Form.Item label="规则名称" name="name" rules={[{ required: true, message: '请输入规则名称' }]}>
              <Input placeholder="例如：WB DEMO SHOP 中国订单" />
            </Form.Item>
            <Form.Item label="指定物流渠道" name="logistics_channel" rules={[{ required: true, message: '请选择物流渠道' }]}>
              <Select
                placeholder="请选择已启用的物流授权"
                options={channelOptions}
                showSearch
                optionFilterProp="label"
                notFoundContent="暂无启用的物流授权"
              />
            </Form.Item>
            <Form.Item label="平台" name="platform" rules={[{ required: true, message: '请选择平台' }]}>
              <Select
                placeholder="选择平台"
                options={platformOptions}
                showSearch
                optionFilterProp="label"
                onChange={() => {
                  ruleForm.setFieldValue('shop_names', [])
                }}
              />
            </Form.Item>
            <Form.Item label="优先级" name="priority" rules={[{ required: true, message: '请输入优先级' }]}>
              <InputNumber min={1} max={9999} precision={0} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item label="启用状态" name="enabled" valuePropName="checked">
              <Switch checkedChildren="启用" unCheckedChildren="停用" />
            </Form.Item>
            <Form.Item className="logistics-rule-form-full" label="来源店铺" name="shop_names">
              <Select
                mode="multiple"
                allowClear
                disabled={!selectedPlatform}
                placeholder={selectedPlatform ? '选择来源店铺；不填表示该平台全部店铺' : '请先选择平台'}
                options={availableShopOptions}
                showSearch
                optionFilterProp="label"
              />
            </Form.Item>
            <Form.Item className="logistics-rule-form-full" label="是否海外仓" name="is_overseas_warehouse">
              <Select
                options={[
                  { value: 'all', label: '全部' },
                  { value: true, label: '是' },
                  { value: false, label: '否' }
                ]}
              />
            </Form.Item>
            <Form.Item className="logistics-rule-form-full" label="目的国家" name="country_codes">
              <Select
                mode="tags"
                allowClear
                placeholder="选择或输入国家二字码；不填表示全部国家"
                options={COUNTRY_OPTIONS}
                tokenSeparators={[',', '，']}
                onChange={(values: string[]) => {
                  ruleForm.setFieldValue('country_codes', values.map(normalizeCountryCode).filter(Boolean))
                }}
              />
            </Form.Item>
            <Form.Item className="logistics-rule-form-full" label="备注" name="remark">
              <Input.TextArea rows={3} placeholder="可填写这条规则的适用说明" />
            </Form.Item>
          </div>
        </Form>
      </Modal>
    </div>
  )
}
