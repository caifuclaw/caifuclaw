import { useEffect, useMemo, useRef, useState } from 'react'
import {
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  ExportOutlined,
  ImportOutlined,
  MinusCircleOutlined,
  PictureOutlined,
  PlusOutlined
} from '@ant-design/icons'
import {
  App,
  Button,
  Form,
  Image,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Tag
} from 'antd'
import { DataTable } from '@/components/DataTable'
import type { DataTableColumnsType } from '@/components/DataTable'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import type { FormListFieldData } from 'antd/es/form/FormList'
import {
  batchSetProductEnabled,
  createProduct,
  deleteProduct,
  downloadProductImportTemplateBlob,
  exportProductsBlob,
  getProduct,
  importProducts,
  listProductOptions,
  listProducts,
  toggleProductEnabled,
  updateProduct,
  type ProductDto,
  type ProductListParams,
  type ProductPayload,
  type ShopOptionDto,
  type UserSimpleDto
} from '@/api/products'
import { PLATFORM_OPTIONS } from '@/stores/dict'
import { downloadBlob } from '@/utils/download'
import { shouldIgnoreTableRowDoubleClick } from '@/utils/tableInteractions'

interface FilterValues {
  keyword?: string
  enabled?: boolean
  is_slow_moving_material?: boolean
}

interface ProductFormValues {
  product_code?: string
  internal_name?: string
  english_name?: string
  cost?: number | null
  weight?: number | null
  gross_weight?: number | null
  package_length?: number | null
  package_width?: number | null
  package_height?: number | null
  ean?: string
  description?: string
  main_image_url?: string
  is_slow_moving_material?: boolean
  safety_stock?: number | null
  buyer_user_id?: number | null
  enabled?: boolean
  mappingRows?: ProductMappingRow[]
}

interface ProductMappingRow {
  shop_id?: number
  shop_sku?: string
}

function previewableProductImageUrl(value: unknown) {
  const url = `${value || ''}`.trim()
  return /^https?:\/\/\S+$/i.test(url) ? url : ''
}

function ProductImagePreview({
  value,
  alt,
  size = 'table'
}: {
  value: unknown
  alt: string
  size?: 'table' | 'editor'
}) {
  const url = previewableProductImageUrl(value)
  const hasValue = Boolean(`${value || ''}`.trim())
  if (!url) {
    if (size === 'table' && !hasValue) return <span>-</span>
    return (
      <div
        className={`product-image-preview product-image-preview--${size} product-image-preview--empty`}
        role="img"
        aria-label={hasValue ? `${alt}链接无法预览` : `${alt}暂无图片`}
      >
        <PictureOutlined aria-hidden />
        {size === 'editor' ? <span>{hasValue ? '无法预览' : '暂无图片'}</span> : null}
      </div>
    )
  }
  return (
    <div
      className={`product-image-preview product-image-preview--${size}`}
      onDoubleClick={(event) => event.stopPropagation()}
    >
      <Image src={url} alt={alt} width="100%" height="100%" />
    </div>
  )
}

export function Products() {
  const { message } = App.useApp()
  const [filterForm] = Form.useForm<FilterValues>()
  const [editForm] = Form.useForm<ProductFormValues>()
  const editorProductCode = Form.useWatch('product_code', editForm)
  const editorProductName = Form.useWatch('internal_name', editForm)
  const editorMainImageUrl = Form.useWatch('main_image_url', editForm)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const optionsLoadedRef = useRef(false)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [data, setData] = useState<ProductDto[]>([])
  const [shops, setShops] = useState<ShopOptionDto[]>([])
  const [users, setUsers] = useState<UserSimpleDto[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [submittedFilters, setSubmittedFilters] = useState<FilterValues>({})
  const editorTitle =
    editingId && editorProductCode && editorProductCode !== '保存后自动生成'
      ? `编辑产品：${editorProductCode}`
      : editingId
        ? '编辑产品'
        : '新增产品'

  const platformLabelMap = useMemo(
    () => new Map(PLATFORM_OPTIONS.map((item) => [item.code, item.label])),
    []
  )

  const groupedShops = useMemo(
    () =>
      [...shops].sort((a, b) => {
        const platformCompare = (platformLabelMap.get(a.platform) || a.platform).localeCompare(
          platformLabelMap.get(b.platform) || b.platform
        )
        if (platformCompare !== 0) return platformCompare
        return (a.display_name || '').localeCompare(b.display_name || '')
      }),
    [platformLabelMap, shops]
  )

  const shopOptions = useMemo(
    () =>
      groupedShops.map((shop) => ({
        value: shop.id,
        label: shop.display_name || shop.platform
      })),
    [groupedShops]
  )

  const shopById = useMemo(() => new Map(shops.map((shop) => [shop.id, shop])), [shops])

  function normalizeMappingValues(values: unknown): string[] {
    if (Array.isArray(values)) {
      return values.map((value) => `${value ?? ''}`.trim()).filter(Boolean)
    }
    if (values == null) return []
    const text = `${values}`.trim()
    return text ? [text] : []
  }

  function mappingValuesForShop(mappings: unknown, shopId: number): string[] {
    if (!mappings || typeof mappings !== 'object') return []
    return normalizeMappingValues((mappings as Record<string, unknown>)[String(shopId)])
  }

  function mappingsToRows(mappings: unknown = {}): ProductMappingRow[] {
    if (!mappings || typeof mappings !== 'object') return []
    return Object.entries(mappings as Record<string, unknown>).flatMap(([shopId, values]) =>
      normalizeMappingValues(values).map((value) => ({
        shop_id: Number(shopId),
        shop_sku: value
      }))
    )
  }

  function defaultMappingRows(): ProductMappingRow[] {
    return groupedShops.map((shop) => ({
      shop_id: shop.id,
      shop_sku: ''
    }))
  }

  const params = useMemo<ProductListParams>(() => {
    return {
      keyword: submittedFilters.keyword?.trim() || undefined,
      enabled: submittedFilters.enabled,
      is_slow_moving_material: submittedFilters.is_slow_moving_material,
      page,
      page_size: pageSize
    }
  }, [submittedFilters, page, pageSize])

  async function loadOptions() {
    try {
      const resp = await listProductOptions()
      optionsLoadedRef.current = true
      setShops(resp.shops || [])
      setUsers(resp.users || [])
    } catch {
      // 产品列表可先展示，店铺和采购人选项稍后再补。
    }
  }

  async function load() {
    setLoading(true)
    try {
      const includeOptions = !optionsLoadedRef.current
      const resp = await listProducts({ ...params, include_options: includeOptions })
      setData(resp.items || [])
      if (includeOptions) {
        optionsLoadedRef.current = true
        setShops(resp.shops || [])
        setUsers(resp.users || [])
      }
      setTotal(resp.total || 0)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [params])

  useEffect(() => {
    if (!drawerOpen || editingId !== null || !groupedShops.length) return
    const rows: ProductMappingRow[] = editForm.getFieldValue('mappingRows') || []
    if (!rows.length) editForm.setFieldValue('mappingRows', defaultMappingRows())
  }, [drawerOpen, editForm, editingId, groupedShops])

  function buildPayload(values: ProductFormValues): ProductPayload {
    const mappings: Record<string, string[]> = {}
    const seen = new Set<string>()
    for (const row of values.mappingRows || []) {
      if (!row?.shop_id) continue
      const text = `${row.shop_sku || ''}`.trim()
      if (!text) continue
      const key = `${row.shop_id}::${text}`
      if (seen.has(key)) continue
      seen.add(key)
      const shopKey = String(row.shop_id)
      if (!mappings[shopKey]) mappings[shopKey] = []
      mappings[shopKey].push(text)
    }
    return {
      internal_name: values.internal_name?.trim() || '',
      english_name: values.english_name?.trim() || '',
      cost: values.cost ?? null,
      weight: values.weight ?? null,
      gross_weight: values.gross_weight ?? null,
      package_length: values.package_length ?? null,
      package_width: values.package_width ?? null,
      package_height: values.package_height ?? null,
      ean: values.ean?.trim() || '',
      description: values.description?.trim() || '',
      main_image_url: values.main_image_url?.trim() || '',
      is_slow_moving_material: values.is_slow_moving_material === true,
      safety_stock: values.safety_stock ?? null,
      buyer_user_id: values.buyer_user_id ?? null,
      enabled: values.enabled !== false,
      mappings
    }
  }

  function openCreate() {
    setEditingId(null)
    if (!optionsLoadedRef.current) loadOptions()
    editForm.resetFields()
    editForm.setFieldsValue({
      product_code: 'DEMO-PRODUCT-0001',
      enabled: true,
      is_slow_moving_material: false,
      mappingRows: defaultMappingRows()
    })
    setDrawerOpen(true)
  }

  async function openEdit(row: ProductDto) {
    setEditingId(row.id)
    const detail = await getProduct(row.id)
    if (!optionsLoadedRef.current) loadOptions()
    editForm.setFieldsValue({
      product_code: detail.product_code,
      internal_name: detail.internal_name,
      english_name: detail.english_name,
      cost: detail.cost,
      weight: detail.weight,
      gross_weight: detail.gross_weight,
      package_length: detail.package_length,
      package_width: detail.package_width,
      package_height: detail.package_height,
      ean: detail.ean,
      description: detail.description,
      main_image_url: detail.main_image_url,
      is_slow_moving_material: detail.is_slow_moving_material,
      safety_stock: detail.safety_stock,
      buyer_user_id: detail.buyer_user_id,
      enabled: detail.enabled,
      mappingRows: mappingsToRows(detail.mappings || {})
    })
    setDrawerOpen(true)
  }

  async function onSave() {
    const values = await editForm.validateFields()
    const payload = buildPayload(values)
    setSaving(true)
    try {
      if (editingId) await updateProduct(editingId, payload)
      else await createProduct(payload)
      message.success('已保存')
      setDrawerOpen(false)
      await load()
    } finally {
      setSaving(false)
    }
  }

  async function onToggleEnabled(row: ProductDto) {
    await toggleProductEnabled(row.id)
    message.success(row.enabled ? '已停用' : '已启用')
    await load()
  }

  async function onDelete(row: ProductDto) {
    await deleteProduct(row.id)
    message.success('已删除')
    await load()
  }

  async function onBatchEnabled(enabled: boolean) {
    const ids = selectedRowKeys.map(Number)
    if (!ids.length) {
      message.warning('请选择产品')
      return
    }
    const resp = await batchSetProductEnabled(ids, enabled)
    message.success(resp.message || `已更新 ${resp.updated || ids.length} 个产品`)
    setSelectedRowKeys([])
    await load()
  }

  async function onImportChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    const result = await importProducts(file)
    const text = `导入完成：新增 ${result.created || 0}，更新 ${result.updated || 0}，失败 ${result.failed || 0}`
    if (result.failed) message.warning(text)
    else message.success(text)
    await load()
  }

  async function onExport() {
    const blob = await exportProductsBlob(params)
    downloadBlob(blob, `products_${Date.now()}.xlsx`)
    message.success('已导出')
  }

  async function onDownloadImportTemplate() {
    const blob = await downloadProductImportTemplateBlob()
    downloadBlob(blob, 'product_import_template.xlsx')
    message.success('已下载导入模版')
  }

  const renderMappingEditor = (
    fields: FormListFieldData[],
    add: (defaultValue?: ProductMappingRow, insertIndex?: number) => void,
    remove: (index: number | number[]) => void
  ) => {
    const columns: ColumnsType<FormListFieldData> = [
      {
        title: '店铺',
        width: 220,
        render: (_, field) => (
          <Form.Item name={[field.name, 'shop_id']} style={{ marginBottom: 0 }}>
            <Select
              showSearch
              placeholder="请选择店铺"
              optionFilterProp="label"
              options={shopOptions}
              onChange={() => editForm.validateFields(['mappingRows']).catch(() => undefined)}
            />
          </Form.Item>
        )
      },
      {
        title: '平台',
        width: 120,
        render: (_, field) => {
          const shopId = editForm.getFieldValue(['mappingRows', field.name, 'shop_id'])
          const shop = shopId ? shopById.get(shopId) : null
          return shop ? platformLabelMap.get(shop.platform) || shop.platform : '-'
        }
      },
      {
        title: '店铺 SKU',
        width: 380,
        render: (_, field) => (
          <Form.Item
            name={[field.name, 'shop_sku']}
            rules={[
              {
                validator: async (_, value) => {
                  const shopId = editForm.getFieldValue(['mappingRows', field.name, 'shop_id'])
                  const text = `${value || ''}`.trim()
                  if (!text) return
                  if (!shopId) throw new Error('请选择店铺')
                  const rows: ProductMappingRow[] = editForm.getFieldValue('mappingRows') || []
                  const duplicate = rows.some(
                    (row, index) =>
                      index !== field.name && row?.shop_id === shopId && `${row.shop_sku || ''}`.trim() === text
                  )
                  if (duplicate) throw new Error('同一店铺下 SKU 不能重复')
                }
              }
            ]}
            style={{ marginBottom: 0 }}
          >
            <Input allowClear placeholder="请输入店铺 SKU" onBlur={() => editForm.validateFields(['mappingRows']).catch(() => undefined)} />
          </Form.Item>
        )
      },
      {
        title: '操作',
        width: 90,
        align: 'center',
        render: (_, field) => (
          <Button danger type="link" size="small" icon={<MinusCircleOutlined />} onClick={() => remove(field.name)}>
            删除
          </Button>
        )
      }
    ]

    return (
      <Space direction="vertical" size={12} className="products-editor__mapping" style={{ width: '100%' }}>
        <Button type="primary" className="products-mapping-add" icon={<PlusOutlined />} onClick={() => add({})}>
          新增行
        </Button>
        <DataTable<FormListFieldData>
          rowKey="key"
          bordered
          size="small"
          pagination={false}
          dataSource={fields}
          columns={columns}
          scroll={{ y: 158 }}
          locale={{ emptyText: '暂无映射，请新增行' }}
        />
      </Space>
    )
  }

  const shopSkuColumns: ColumnsType<ProductDto> = shops.map((shop) => ({
    title: shop.display_name,
    key: `shop-${shop.id}`,
    width: 220,
    render: (_: unknown, row: ProductDto) => {
      const values = mappingValuesForShop(row.mappings, shop.id)
      return values.length ? <div style={{ whiteSpace: 'pre-line' }}>{values.join('\n')}</div> : '-'
    }
  }))

  const columns: DataTableColumnsType<ProductDto> = [
    {
      title: '产品图片',
      dataIndex: 'main_image_url',
      width: 96,
      userFixedWidth: true,
      align: 'center',
      fixed: 'left',
      render: (value, row) => (
        <ProductImagePreview value={value} alt={`${row.internal_name || row.product_code}主图`} />
      )
    },
    { title: '编码', dataIndex: 'product_code', width: 130, fixed: 'left' },
    { title: '产品中文名', dataIndex: 'internal_name', width: 240, ellipsis: true },
    { title: '产品英文名', dataIndex: 'english_name', width: 220, ellipsis: true, render: (value) => value || '-' },
    ...shopSkuColumns,
    { title: '成本', dataIndex: 'cost', width: 90, render: (value) => value ?? '-' },
    { title: '净重', dataIndex: 'weight', width: 90, render: (value) => value ?? '-' },
    { title: '毛重', dataIndex: 'gross_weight', width: 90, render: (value) => value ?? '-' },
    { title: '包装长', dataIndex: 'package_length', width: 90, render: (value) => value ?? '-' },
    { title: '包装宽', dataIndex: 'package_width', width: 90, render: (value) => value ?? '-' },
    { title: '包装高', dataIndex: 'package_height', width: 90, render: (value) => value ?? '-' },
    { title: 'EAN', dataIndex: 'ean', width: 140, ellipsis: true, render: (value) => value || '-' },
    { title: '描述', dataIndex: 'description', width: 220, ellipsis: true, render: (value) => value || '-' },
    {
      title: '是否呆滞料',
      dataIndex: 'is_slow_moving_material',
      width: 110,
      render: (value) => <Tag color={value ? 'warning' : 'default'}>{value ? '是' : '否'}</Tag>
    },
    { title: '安全库存', dataIndex: 'safety_stock', width: 100, render: (value) => value ?? '-' },
    { title: '采购人', dataIndex: 'buyer_name', width: 110, render: (value) => value || '-' },
    {
      title: '状态',
      dataIndex: 'enabled',
      width: 90,
      render: (value) => <Tag color={value ? 'success' : 'default'}>{value ? '启用' : '停用'}</Tag>
    },
    {
      title: '操作',
      key: 'action',
      width: 180,
      fixed: 'right',
      render: (_, row) => (
        <Space size={4}>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(row)}>
            编辑
          </Button>
          <Button type="link" size="small" onClick={() => onToggleEnabled(row)}>
            {row.enabled ? '停用' : '启用'}
          </Button>
          <Popconfirm title="确认删除该产品？" onConfirm={() => onDelete(row)}>
            <Button danger type="link" size="small" icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      )
    }
  ]

  const pagination: TablePaginationConfig = {
    current: page,
    pageSize,
    total,
    pageSizeOptions: [50, 100, 200, 500],
    showSizeChanger: true,
    showTotal: (value) => `共 ${value} 条`,
    onChange: (nextPage, nextPageSize) => {
      setPage(nextPage)
      setPageSize(nextPageSize)
    }
  }

  return (
    <div className="page-card products-page">
      <div className="orders-header products-page__header">
        <h2>产品管理</h2>
        <Space wrap>
          <input ref={fileInputRef} hidden type="file" accept=".xlsx,.xls" onChange={onImportChange} />
          <Button icon={<ImportOutlined />} onClick={() => fileInputRef.current?.click()}>
            导入
          </Button>
          <Button icon={<DownloadOutlined />} onClick={onDownloadImportTemplate}>
            导入模版
          </Button>
          <Button icon={<ExportOutlined />} onClick={onExport}>
            导出
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新增产品
          </Button>
        </Space>
      </div>

      <Form
        form={filterForm}
        layout="inline"
        className="orders-filter products-page__filter"
        onFinish={(values) => {
          setSubmittedFilters(values)
          setPage(1)
        }}
      >
        <Form.Item label="关键词" name="keyword" className="products-page__keyword">
          <Input allowClear placeholder="编码 / 产品中文名 / 产品英文名 / EAN / 店铺 SKU" />
        </Form.Item>
        <Form.Item label="呆滞料" name="is_slow_moving_material">
          <Select
            allowClear
            placeholder="全部"
            options={[
              { value: true, label: '是' },
              { value: false, label: '否' }
            ]}
          />
        </Form.Item>
        <Form.Item label="状态" name="enabled">
          <Select
            allowClear
            placeholder="全部"
            options={[
              { value: true, label: '启用' },
              { value: false, label: '停用' }
            ]}
          />
        </Form.Item>
        <Form.Item className="products-page__filter-actions">
          <Space>
            <Button type="primary" htmlType="submit">
              查询
            </Button>
            <Button
              onClick={() => {
                filterForm.resetFields()
                setSubmittedFilters({})
                setPage(1)
              }}
            >
              重置
            </Button>
          </Space>
        </Form.Item>
      </Form>

      <div className="toolbar-row">
        <Button disabled={!selectedRowKeys.length} onClick={() => onBatchEnabled(true)}>
          批量启用
        </Button>
        <Button danger disabled={!selectedRowKeys.length} onClick={() => onBatchEnabled(false)}>
          批量停用
        </Button>
      </div>

      <DataTable
        rowKey="id"
        loading={loading}
        dataSource={data}
        columns={columns}
        pagination={pagination}
        rowSelection={{ selectedRowKeys, onChange: setSelectedRowKeys }}
        onRow={(row) => ({
          onDoubleClick: (event) => {
            if (shouldIgnoreTableRowDoubleClick(event.target)) return
            openEdit(row)
          }
        })}
      />

      <Modal
        open={drawerOpen}
        width="min(1580px, calc(100vw - 48px))"
        title={editorTitle}
        className="products-editor-modal"
        centered
        destroyOnClose
        onCancel={() => setDrawerOpen(false)}
        footer={
          <Space>
            <Button onClick={() => setDrawerOpen(false)}>取消</Button>
            <Button type="primary" loading={saving} onClick={onSave}>
              保存
            </Button>
          </Space>
        }
      >
        <Form
          form={editForm}
          layout="vertical"
          className="products-editor"
          initialValues={{ enabled: true, is_slow_moving_material: false, mappingRows: [] }}
        >
          <Form.Item name="product_code" hidden>
            <Input />
          </Form.Item>
          <div className="products-editor__layout">
            <section className="products-editor__panel products-editor__panel--basic">
              <div className="products-editor__panel-title">基础信息</div>
              <div className="products-editor__identity-row">
                <Form.Item
                  label="产品中文名"
                  name="internal_name"
                  className="products-editor__field--full"
                  rules={[{ required: true, message: '请输入产品中文名' }]}
                >
                  <Input placeholder="产品中文名" />
                </Form.Item>
                <Form.Item label="产品英文名" name="english_name" className="products-editor__field--full">
                  <Input allowClear placeholder="产品英文名" />
                </Form.Item>
              </div>
              <div className="products-editor__text-grid">
                <Form.Item label="描述" name="description">
                  <Input.TextArea allowClear autoSize={{ minRows: 1, maxRows: 4 }} placeholder="描述" />
                </Form.Item>
                <Form.Item label="图片链接">
                  <div className="products-editor__image-control">
                    <ProductImagePreview
                      value={editorMainImageUrl}
                      alt={`${editorProductName || editorProductCode || '产品'}主图`}
                      size="editor"
                    />
                    <Form.Item name="main_image_url" noStyle>
                      <Input.TextArea
                        allowClear
                        aria-label="图片链接"
                        autoSize={{ minRows: 4, maxRows: 4 }}
                        placeholder="图片链接"
                      />
                    </Form.Item>
                  </div>
                </Form.Item>
              </div>
            </section>
            <section className="products-editor__panel products-editor__panel--business">
              <div className="products-editor__panel-title">业务信息</div>
              <div className="products-editor__numeric-grid">
                <Form.Item label="成本" name="cost">
                  <InputNumber min={0} precision={2} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item label="净重" name="weight">
                  <InputNumber min={0} precision={3} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item label="毛重" name="gross_weight">
                  <InputNumber min={0} precision={3} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item label="包装长" name="package_length">
                  <InputNumber min={0} precision={2} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item label="包装宽" name="package_width">
                  <InputNumber min={0} precision={2} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item label="包装高" name="package_height">
                  <InputNumber min={0} precision={2} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item label="EAN" name="ean">
                  <Input allowClear placeholder="EAN" />
                </Form.Item>
                <Form.Item label="安全库存" name="safety_stock">
                  <InputNumber min={0} precision={0} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item label="采购人" name="buyer_user_id">
                  <Select
                    allowClear
                    placeholder="请选择采购人"
                    options={users.map((user) => ({
                      value: user.id,
                      label: user.display_name || user.username
                    }))}
                  />
                </Form.Item>
                <Form.Item label="启用状态" name="enabled" valuePropName="checked">
                  <Switch checkedChildren="启用" unCheckedChildren="停用" />
                </Form.Item>
                <Form.Item label="是否呆滞料" name="is_slow_moving_material" valuePropName="checked">
                  <Switch checkedChildren="是" unCheckedChildren="否" />
                </Form.Item>
              </div>
              <Form.List name="mappingRows">
                {(fields, { add, remove }) => renderMappingEditor(fields, add, remove)}
              </Form.List>
            </section>
          </div>
        </Form>
      </Modal>
    </div>
  )
}
