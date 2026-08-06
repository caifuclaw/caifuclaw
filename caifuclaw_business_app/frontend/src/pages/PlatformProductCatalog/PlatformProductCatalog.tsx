import { useEffect, useMemo, useState } from 'react'
import {
  CalculatorOutlined,
  DeleteOutlined,
  EditOutlined,
  LinkOutlined,
  PictureOutlined,
  PlusOutlined,
  ReloadOutlined,
  SettingOutlined,
  SyncOutlined
} from '@ant-design/icons'
import { App, Button, Checkbox, Form, Input, InputNumber, Modal, Select, Space, Statistic, Tag, Tooltip } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import { DataTable, type DataTableConfig } from '@/components/DataTable'
import {
  createPlatformProductPricingRule,
  deletePlatformProductPricingRule,
  getPlatformProductCatalogOptions,
  listPlatformProductCatalog,
  listPlatformProductPricingRules,
  mapPlatformProductCatalogItem,
  recalculatePlatformProductCatalog,
  syncPlatformProductCatalog,
  updatePlatformProductPricingRule,
  type CatalogProductOption,
  type CatalogShopOption,
  type PlatformProductCatalogItemDto,
  type PlatformProductCatalogListParams,
  type PlatformProductPricingRuleDto,
  type PlatformProductPricingRuleInput
} from '@/api/platformProductCatalog'
import { formatMoney, formatNumber, formatTime } from '@/utils/format'
import { formatPlatformLabel } from '@/stores/dict'
import './PlatformProductCatalog.less'

interface CatalogFilters {
  platform?: string
  shop_id?: number
  keyword?: string
  calculation_status?: string
  mapped?: 'all' | 'mapped' | 'unmapped'
}

interface RuleFormValues extends PlatformProductPricingRuleInput {
  shop_id?: number | null
  product_id?: number | null
}

const TABLE_CONFIG: DataTableConfig = {
  tableKey: 'platform-product-catalog.list.v2',
  primaryColumnKey: 'product_name',
  widthMode: 'adaptive-left',
  columns: [
    { key: 'main_image_url', title: '主图', required: true, fixed: 'left', protectedWidth: 72, minWidth: 72, maxWidth: 72 },
    { key: 'product_name', title: '平台商品', required: true, fixed: 'left', minWidth: 210, maxWidth: 360 },
    { key: 'platform', title: '店铺 / 平台', minWidth: 150, maxWidth: 210 },
    { key: 'platform_sku', title: '平台 SKU', minWidth: 150, maxWidth: 240 },
    { key: 'internal_product', title: '内部产品', minWidth: 180, maxWidth: 280 },
    { key: 'warehouse_name', title: '平台仓库', minWidth: 140, maxWidth: 210 },
    { key: 'available_stock', title: '可售库存', minWidth: 96, maxWidth: 120 },
    { key: 'price', title: '当前售价', minWidth: 140, maxWidth: 180 },
    { key: 'cost_cny', title: '成本', minWidth: 110, maxWidth: 135 },
    { key: 'fees', title: '佣金 / 运费', minWidth: 145, maxWidth: 185 },
    { key: 'margin', title: '当前利润率', minWidth: 110, maxWidth: 135 },
    { key: 'suggested_price_cny', title: '建议价', minWidth: 120, maxWidth: 150 },
    { key: 'calculation_status', title: '计算状态', minWidth: 125, maxWidth: 180 },
    { key: 'last_synced_at', title: '同步时间', minWidth: 155, maxWidth: 175 },
    { key: 'actions', title: '操作', fixed: 'right', protectedWidth: 110, settingsHidden: true }
  ]
}

const CALCULATION_STATUS: Record<string, { label: string; color: string }> = {
  ready: { label: '可生成建议价', color: 'green' },
  missing_mapping: { label: '待映射产品', color: 'orange' },
  missing_rule: { label: '待配置费用规则', color: 'orange' },
  missing_cost: { label: '待维护成本', color: 'red' },
  missing_exchange_rate: { label: '缺少当天汇率', color: 'red' },
  invalid_rule: { label: '规则无效', color: 'red' }
}

function platformLabel(value: string) {
  return formatPlatformLabel(value)
}

function rate(value?: string | null) {
  if (value == null || value === '') return '-'
  return `${formatNumber(Number(value) * 100, 1)}%`
}

function moneyCny(value?: string | null) {
  return formatMoney(value, 'CNY')
}

function ruleFormValues(rule?: PlatformProductPricingRuleDto | null): RuleFormValues {
  return {
    name: rule?.name || '',
    platform: rule?.platform || '',
    shop_id: rule?.shop_id || undefined,
    product_id: rule?.product_id || undefined,
    warehouse_code: rule?.warehouse_code || '',
    logistics_type: rule?.logistics_type || '',
    commission_rate: rule?.commission_rate || '0',
    base_shipping_fee_cny: rule?.base_shipping_fee_cny || '0',
    shipping_fee_per_kg_cny: rule?.shipping_fee_per_kg_cny || '0',
    target_margin_rate: rule?.target_margin_rate || '0',
    price_increment_cny: rule?.price_increment_cny || '0.01',
    priority: rule?.priority ?? 100,
    enabled: rule?.enabled ?? true,
    remark: rule?.remark || ''
  }
}

export function PlatformProductCatalog() {
  const { message, modal } = App.useApp()
  const [filterForm] = Form.useForm<CatalogFilters>()
  const [mappingForm] = Form.useForm<{ product_id?: number }>()
  const [ruleForm] = Form.useForm<RuleFormValues>()
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [recalculating, setRecalculating] = useState(false)
  const [savingRule, setSavingRule] = useState(false)
  const [rows, setRows] = useState<PlatformProductCatalogItemDto[]>([])
  const [total, setTotal] = useState(0)
  const [summary, setSummary] = useState<Record<string, number>>({})
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [submittedFilters, setSubmittedFilters] = useState<CatalogFilters>({ mapped: 'all' })
  const [shops, setShops] = useState<CatalogShopOption[]>([])
  const [products, setProducts] = useState<CatalogProductOption[]>([])
  const [rules, setRules] = useState<PlatformProductPricingRuleDto[]>([])
  const [mappingItem, setMappingItem] = useState<PlatformProductCatalogItemDto | null>(null)
  const [mappingOpen, setMappingOpen] = useState(false)
  const [rulesOpen, setRulesOpen] = useState(false)
  const [ruleEditorOpen, setRuleEditorOpen] = useState(false)
  const [editingRule, setEditingRule] = useState<PlatformProductPricingRuleDto | null>(null)

  const platformOptions = useMemo(
    () => [...new Set(shops.map((shop) => shop.platform).filter(Boolean))].map((value) => ({ value, label: platformLabel(value) })),
    [shops]
  )
  const selectedRulePlatform = Form.useWatch('platform', ruleForm)
  const eligibleRuleShops = useMemo(
    () => shops.filter((shop) => !selectedRulePlatform || shop.platform === selectedRulePlatform),
    [shops, selectedRulePlatform]
  )

  function requestParams(filters: CatalogFilters, nextPage: number, nextPageSize: number): PlatformProductCatalogListParams {
    return {
      platform: filters.platform || undefined,
      shop_id: filters.shop_id || undefined,
      keyword: filters.keyword?.trim() || undefined,
      calculation_status: filters.calculation_status || undefined,
      mapped: filters.mapped === 'mapped' ? true : filters.mapped === 'unmapped' ? false : undefined,
      page: nextPage,
      page_size: nextPageSize
    }
  }

  async function loadCatalog(nextPage = page, nextPageSize = pageSize, filters = submittedFilters) {
    setLoading(true)
    try {
      const data = await listPlatformProductCatalog(requestParams(filters, nextPage, nextPageSize))
      setRows(data.items || [])
      setTotal(data.total || 0)
      setSummary(data.summary || {})
      setPage(data.page || nextPage)
      setPageSize(data.page_size || nextPageSize)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '平台产品目录加载失败')
    } finally {
      setLoading(false)
    }
  }

  async function loadOptions() {
    const data = await getPlatformProductCatalogOptions()
    setShops(data.shops || [])
    setProducts(data.products || [])
  }

  async function loadRules() {
    try {
      setRules(await listPlatformProductPricingRules())
    } catch (error) {
      message.error(error instanceof Error ? error.message : '费用规则加载失败')
    }
  }

  useEffect(() => {
    void loadCatalog(1, pageSize, { mapped: 'all' })
    void loadOptions().catch(() => message.error('目录维护选项加载失败'))
    void loadRules()
  }, [])

  async function onSearch(values: CatalogFilters) {
    const filters = { ...values, mapped: values.mapped || 'all' }
    setSubmittedFilters(filters)
    await loadCatalog(1, pageSize, filters)
  }

  async function resetFilters() {
    const filters = { mapped: 'all' as const }
    filterForm.setFieldsValue(filters)
    setSubmittedFilters(filters)
    await loadCatalog(1, pageSize, filters)
  }

  async function synchronize(mode: 'full' | 'incremental' = 'full') {
    setSyncing(true)
    try {
      const targetShopIds = submittedFilters.shop_id ? [submittedFilters.shop_id] : []
      const result = await syncPlatformProductCatalog(targetShopIds, mode)
      const failed = result.shops.filter((shop) => shop.status === 'failed')
      const syncLabel = mode === 'incremental' ? '增量' : '全量'
      if (failed.length) {
        modal.warning({
          title: `${syncLabel}同步已完成 ${result.synced} 条，${failed.length} 个店铺失败`,
          content: failed.map((shop) => `${shop.shop_name}：${shop.message || '未知错误'}`).join('\n')
        })
      } else {
        message.success(`已完成${syncLabel}同步 ${result.synced} 条平台商品`)
      }
      await loadCatalog(1, pageSize)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '同步失败')
    } finally {
      setSyncing(false)
    }
  }

  async function recalculate() {
    setRecalculating(true)
    try {
      const result = await recalculatePlatformProductCatalog()
      message.success(`已重新计算 ${result.recalculated} 条商品`)
      await loadCatalog()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '重新计算失败')
    } finally {
      setRecalculating(false)
    }
  }

  function openMapping(row: PlatformProductCatalogItemDto) {
    setMappingItem(row)
    mappingForm.setFieldsValue({ product_id: row.product_id || undefined })
    setMappingOpen(true)
  }

  async function saveMapping() {
    if (!mappingItem) return
    try {
      const values = await mappingForm.validateFields()
      await mapPlatformProductCatalogItem(mappingItem.id, values.product_id || null)
      message.success(values.product_id ? '产品映射已保存' : '已解除产品映射')
      setMappingOpen(false)
      await loadCatalog()
    } catch (error) {
      if (error && typeof error === 'object' && 'errorFields' in error) return
      message.error(error instanceof Error ? error.message : '产品映射保存失败')
    }
  }

  function openRuleEditor(rule?: PlatformProductPricingRuleDto) {
    setEditingRule(rule || null)
    ruleForm.setFieldsValue(ruleFormValues(rule))
    setRuleEditorOpen(true)
  }

  async function saveRule() {
    try {
      const values = await ruleForm.validateFields()
      setSavingRule(true)
      if (editingRule) {
        await updatePlatformProductPricingRule(editingRule.id, values)
        message.success('费用规则已更新')
      } else {
        await createPlatformProductPricingRule(values)
        message.success('费用规则已新增')
      }
      setRuleEditorOpen(false)
      await loadRules()
      await loadCatalog()
    } catch (error) {
      if (error && typeof error === 'object' && 'errorFields' in error) return
      message.error(error instanceof Error ? error.message : '费用规则保存失败')
    } finally {
      setSavingRule(false)
    }
  }

  function removeRule(rule: PlatformProductPricingRuleDto) {
    modal.confirm({
      title: '删除费用规则',
      content: `确定删除“${rule.name}”吗？已有商品会在重新计算后标记为待配置规则。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        await deletePlatformProductPricingRule(rule.id)
        message.success('费用规则已删除')
        await loadRules()
        await loadCatalog()
      }
    })
  }

  const columns = useMemo<ColumnsType<PlatformProductCatalogItemDto>>(
    () => [
      {
        title: '主图',
        dataIndex: 'main_image_url',
        minWidth: 72,
        maxWidth: 72,
        align: 'center',
        render: (value, row) => {
          const imageUrl = typeof value === 'string' ? value.trim() : ''
          if (!imageUrl) {
            return (
              <span className="platform-catalog-image platform-catalog-image--empty" aria-label="无主图">
                <PictureOutlined />
              </span>
            )
          }
          return (
            <a
              className="platform-catalog-image"
              href={imageUrl}
              target="_blank"
              rel="noreferrer"
              title="打开主图"
              aria-label={`打开主图 ${row.product_name || row.platform_sku || ''}`.trim()}
            >
              <img src={imageUrl} alt={row.product_name ? `${row.product_name}主图` : '平台商品主图'} loading="lazy" decoding="async" />
            </a>
          )
        }
      },
      {
        title: '平台商品',
        dataIndex: 'product_name',
        minWidth: 210,
        maxWidth: 360,
        ellipsis: true,
        render: (value, row) => (
          <div className="platform-catalog-product">
            <span className="platform-catalog-product__name">{value || '-'}</span>
            {row.listing_status ? <span className="platform-catalog-product__meta">{row.listing_status}</span> : null}
          </div>
        )
      },
      {
        title: '店铺 / 平台',
        key: 'platform',
        minWidth: 150,
        maxWidth: 210,
        render: (_, row) => (
          <div className="platform-catalog-store">
            <span>{row.shop_name || '-'}</span>
            <Tag>{platformLabel(row.platform)}</Tag>
          </div>
        )
      },
      { title: '平台 SKU', dataIndex: 'platform_sku', minWidth: 150, maxWidth: 240, ellipsis: true },
      {
        title: '内部产品',
        key: 'internal_product',
        minWidth: 180,
        maxWidth: 280,
        render: (_, row) =>
          row.product_id ? (
            <div className="platform-catalog-product">
              <span className="platform-catalog-product__name">{row.internal_product_name}</span>
              <span className="platform-catalog-product__meta">{row.product_code}</span>
            </div>
          ) : (
            <Tag color="orange">待映射</Tag>
          )
      },
      {
        title: '平台仓库',
        key: 'warehouse_name',
        minWidth: 140,
        maxWidth: 210,
        ellipsis: true,
        render: (_, row) => row.warehouse_name || row.warehouse_code || '-'
      },
      { title: '可售库存', dataIndex: 'available_stock', minWidth: 96, maxWidth: 120, align: 'right', render: (value) => formatNumber(value) },
      {
        title: '当前售价',
        key: 'price',
        minWidth: 140,
        maxWidth: 180,
        align: 'right',
        render: (_, row) => (
          <div className="platform-catalog-money">
            <span>{formatMoney(row.price_amount, row.price_currency)}</span>
            <span className="platform-catalog-money__sub">{moneyCny(row.current_price_cny)}</span>
          </div>
        )
      },
      { title: '成本', dataIndex: 'cost_cny', minWidth: 110, maxWidth: 135, align: 'right', render: moneyCny },
      {
        title: '佣金 / 运费',
        key: 'fees',
        minWidth: 145,
        maxWidth: 185,
        align: 'right',
        render: (_, row) => (
          <div className="platform-catalog-money">
            <span>{rate(row.commission_rate)}</span>
            <span className="platform-catalog-money__sub">{moneyCny(row.shipping_fee_cny)}</span>
          </div>
        )
      },
      { title: '当前利润率', dataIndex: 'current_margin_rate', minWidth: 110, maxWidth: 135, align: 'right', render: rate },
      {
        title: '建议价',
        dataIndex: 'suggested_price_cny',
        minWidth: 120,
        maxWidth: 150,
        align: 'right',
        render: (value) => <strong className="platform-catalog-suggested-price">{moneyCny(value)}</strong>
      },
      {
        title: '计算状态',
        dataIndex: 'calculation_status',
        minWidth: 125,
        maxWidth: 180,
        render: (value, row) => {
          const status = CALCULATION_STATUS[value] || { label: value || '-', color: 'default' }
          return row.calculation_message ? (
            <Tooltip title={row.calculation_message}>
              <Tag color={status.color}>{status.label}</Tag>
            </Tooltip>
          ) : (
            <Tag color={status.color}>{status.label}</Tag>
          )
        }
      },
      { title: '同步时间', dataIndex: 'last_synced_at', minWidth: 155, maxWidth: 175, render: (value) => formatTime(value, true) },
      {
        title: '操作',
        key: 'actions',
        fixed: 'right',
        width: 110,
        render: (_, row) => (
          <Button type="link" icon={<LinkOutlined />} onClick={() => openMapping(row)}>
            映射
          </Button>
        )
      }
    ],
    [products]
  )

  const ruleColumns = useMemo<ColumnsType<PlatformProductPricingRuleDto>>(
    () => [
      { title: '规则名称', dataIndex: 'name', minWidth: 170, maxWidth: 260, ellipsis: true },
      { title: '平台', dataIndex: 'platform', minWidth: 100, maxWidth: 130, render: platformLabel },
      { title: '店铺', dataIndex: 'shop_name', minWidth: 140, maxWidth: 200, render: (value) => value || '全部店铺' },
      { title: '匹配范围', key: 'scope', minWidth: 180, maxWidth: 260, render: (_, row) => row.product_name || row.warehouse_code || row.logistics_type || '平台默认' },
      { title: '佣金率', dataIndex: 'commission_rate', minWidth: 95, maxWidth: 110, align: 'right', render: rate },
      { title: '起始 / 每公斤', key: 'shipping', minWidth: 150, maxWidth: 185, align: 'right', render: (_, row) => `${moneyCny(row.base_shipping_fee_cny)} / ${moneyCny(row.shipping_fee_per_kg_cny)}` },
      { title: '目标利润率', dataIndex: 'target_margin_rate', minWidth: 110, maxWidth: 130, align: 'right', render: rate },
      { title: '优先级', dataIndex: 'priority', minWidth: 85, maxWidth: 100, align: 'right' },
      { title: '状态', dataIndex: 'enabled', minWidth: 85, maxWidth: 105, render: (value) => <Tag color={value ? 'green' : 'default'}>{value ? '启用' : '停用'}</Tag> },
      {
        title: '操作',
        key: 'actions',
        fixed: 'right',
        width: 130,
        render: (_, row) => (
          <Space size={0}>
            <Button type="link" icon={<EditOutlined />} onClick={() => openRuleEditor(row)}>编辑</Button>
            <Button type="link" danger icon={<DeleteOutlined />} onClick={() => removeRule(row)}>删除</Button>
          </Space>
        )
      }
    ],
    [rules]
  )

  return (
    <div className="platform-catalog-page">
      <div className="platform-catalog-page__header">
        <div>
          <h2>平台产品目录</h2>
          <p>平台可售库存、人民币核算与建议价（全量每日 4 点，增量每小时 30 分）</p>
        </div>
        <Space wrap>
          <Button icon={<SettingOutlined />} onClick={() => setRulesOpen(true)}>费用规则</Button>
          <Button icon={<CalculatorOutlined />} loading={recalculating} onClick={recalculate}>重新计算</Button>
          <Button icon={<SyncOutlined />} type="primary" loading={syncing} onClick={() => synchronize('full')}>全量同步</Button>
          <Button loading={syncing} onClick={() => synchronize('incremental')}>增量同步</Button>
        </Space>
      </div>

      <section className="platform-catalog-page__summary" aria-label="目录状态汇总">
        <Statistic title="目录商品" value={summary.total || 0} />
        <Statistic title="可生成建议价" value={summary.ready || 0} valueStyle={{ color: '#1f7a4c' }} />
        <Statistic title="待映射" value={summary.missing_mapping || 0} valueStyle={{ color: '#b45309' }} />
        <Statistic title="待配置规则" value={summary.missing_rule || 0} valueStyle={{ color: '#b45309' }} />
        <Statistic title="需处理" value={(summary.missing_cost || 0) + (summary.missing_exchange_rate || 0) + (summary.invalid_rule || 0)} valueStyle={{ color: '#b42318' }} />
      </section>

      <Form className="platform-catalog-page__filter" form={filterForm} layout="inline" initialValues={{ mapped: 'all' }} onFinish={onSearch}>
        <Form.Item name="keyword" label="关键词">
          <Input allowClear placeholder="商品名、SKU、产品编码" />
        </Form.Item>
        <Form.Item name="platform" label="平台">
          <Select allowClear options={platformOptions} placeholder="全部平台" />
        </Form.Item>
        <Form.Item name="shop_id" label="店铺">
          <Select allowClear showSearch optionFilterProp="label" options={shops.map((shop) => ({ value: shop.id, label: `${shop.label} · ${platformLabel(shop.platform)}` }))} placeholder="全部店铺" />
        </Form.Item>
        <Form.Item name="calculation_status" label="计算状态">
          <Select allowClear options={Object.entries(CALCULATION_STATUS).map(([value, item]) => ({ value, label: item.label }))} placeholder="全部状态" />
        </Form.Item>
        <Form.Item name="mapped" label="映射">
          <Select options={[{ value: 'all', label: '全部' }, { value: 'mapped', label: '已映射' }, { value: 'unmapped', label: '待映射' }]} />
        </Form.Item>
        <Form.Item className="platform-catalog-page__filter-actions">
          <Space>
            <Button htmlType="submit" type="primary">查询</Button>
            <Button onClick={resetFilters}>重置</Button>
            <Button icon={<ReloadOutlined />} aria-label="刷新平台产品目录" onClick={() => void loadCatalog()} />
          </Space>
        </Form.Item>
      </Form>

      <div className="platform-catalog-page__table" aria-busy={loading}>
        <DataTable
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={rows}
          tableConfig={TABLE_CONFIG}
          fitContainerHeight
          showFullTextOnHover
          scroll={{ x: 2120 }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (value) => `共 ${value} 条`
          }}
          onChange={(pagination: TablePaginationConfig) => {
            void loadCatalog(pagination.current || 1, pagination.pageSize || pageSize)
          }}
        />
      </div>

      <Modal
        open={mappingOpen}
        title="映射内部产品"
        okText="保存"
        cancelText="取消"
        onCancel={() => setMappingOpen(false)}
        onOk={saveMapping}
        destroyOnHidden
      >
        <Form form={mappingForm} layout="vertical">
          <Form.Item label="平台商品">
            <Input value={mappingItem ? `${mappingItem.product_name || '-'} · ${mappingItem.platform_sku || mappingItem.platform_product_id}` : ''} readOnly />
          </Form.Item>
          <Form.Item name="product_id" label="内部产品">
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              options={products.map((product) => ({ value: product.id, label: `${product.product_code} · ${product.internal_name}` }))}
              placeholder="选择内部产品；清空后解除映射"
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={rulesOpen}
        title="费用规则"
        width={1260}
        footer={<Button onClick={() => setRulesOpen(false)}>关闭</Button>}
        onCancel={() => setRulesOpen(false)}
        destroyOnHidden
      >
        <div className="platform-catalog-rules__toolbar">
          <span>优先级数值越小越先匹配；商品、仓库和物流方式可覆盖平台默认规则。</span>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openRuleEditor()}>新增规则</Button>
        </div>
        <DataTable rowKey="id" columns={ruleColumns} dataSource={rules} scroll={{ x: 1320, y: 420 }} pagination={false} showFullTextOnHover />
      </Modal>

      <Modal
        open={ruleEditorOpen}
        title={editingRule ? '编辑费用规则' : '新增费用规则'}
        width={760}
        okText="保存"
        cancelText="取消"
        confirmLoading={savingRule}
        onCancel={() => setRuleEditorOpen(false)}
        onOk={saveRule}
        destroyOnHidden
      >
        <Form form={ruleForm} layout="vertical" className="platform-catalog-rule-editor">
          <div className="platform-catalog-rule-editor__grid">
            <Form.Item name="name" label="规则名称" rules={[{ required: true, message: '请输入规则名称' }]}>
              <Input placeholder="例如：OZON 标准仓默认规则" />
            </Form.Item>
            <Form.Item name="platform" label="平台" rules={[{ required: true, message: '请选择平台' }]}>
              <Select options={platformOptions} onChange={() => ruleForm.setFieldValue('shop_id', undefined)} />
            </Form.Item>
            <Form.Item name="shop_id" label="店铺">
              <Select allowClear showSearch optionFilterProp="label" options={eligibleRuleShops.map((shop) => ({ value: shop.id, label: shop.label }))} placeholder="全部店铺" />
            </Form.Item>
            <Form.Item name="priority" label="优先级">
              <InputNumber min={1} precision={0} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="product_id" label="内部产品">
              <Select allowClear showSearch optionFilterProp="label" options={products.map((product) => ({ value: product.id, label: `${product.product_code} · ${product.internal_name}` }))} placeholder="全部产品" />
            </Form.Item>
            <Form.Item name="warehouse_code" label="平台仓库代码">
              <Input placeholder="全部仓库" />
            </Form.Item>
            <Form.Item name="logistics_type" label="物流方式">
              <Input placeholder="全部物流方式" />
            </Form.Item>
            <Form.Item name="commission_rate" label="佣金率（0-1）" rules={[{ required: true, message: '请输入佣金率' }]}>
              <InputNumber min={0} max={0.9999} step={0.01} precision={4} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="target_margin_rate" label="目标利润率（0-1）" rules={[{ required: true, message: '请输入目标利润率' }]}>
              <InputNumber min={0} max={0.9999} step={0.01} precision={4} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="base_shipping_fee_cny" label="起始运费（CNY）" rules={[{ required: true, message: '请输入起始运费' }]}>
              <InputNumber min={0} step={0.01} precision={2} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="shipping_fee_per_kg_cny" label="每公斤运费（CNY）" rules={[{ required: true, message: '请输入每公斤运费' }]}>
              <InputNumber min={0} step={0.01} precision={2} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="price_increment_cny" label="建议价取整步长（CNY）" rules={[{ required: true, message: '请输入取整步长' }]}>
              <InputNumber min={0.01} step={0.01} precision={2} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="enabled" label="启用" valuePropName="checked" className="platform-catalog-rule-editor__switch">
              <Checkbox>规则生效</Checkbox>
            </Form.Item>
          </div>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={3} maxLength={500} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
