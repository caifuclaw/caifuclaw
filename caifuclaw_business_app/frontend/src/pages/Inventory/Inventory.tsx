/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { DownloadOutlined, ExportOutlined, ImportOutlined, PlusOutlined } from '@ant-design/icons'
import { App, Button, Checkbox, Form, Input, InputNumber, Modal, Select, Space, Tag } from 'antd'
import { DataTable } from '@/components/DataTable'
import type { DataTableConfig, DataTableVisibleColumn } from '@/components/DataTable'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import {
  createInventory,
  downloadInventoryImportTemplateBlob,
  exportInventoryBlob,
  importInventory,
  listInventory,
  searchProductsForInventory,
  updateInventory,
  type InventoryDto,
  type InventoryListParams,
  type InventoryPayload,
  type ProductSearchDto
} from '@/api/inventory'
import { downloadBlob } from '@/utils/download'
import { formatTime } from '@/utils/format'
import { shouldIgnoreTableRowDoubleClick } from '@/utils/tableInteractions'

interface FilterValues {
  product_code?: string
  product_name?: string
  stock_status?: string
  hide_zero_safety_stock?: boolean
}

interface InventoryFormValues {
  product_id?: number
  stock_qty?: number
  last_count_qty?: number
  safety_stock?: number
  remark?: string
}

const INVENTORY_TABLE_CONFIG: DataTableConfig = {
  tableKey: 'inventory.list',
  primaryColumnKey: 'product_code',
  widthMode: 'adaptive-left',
  columns: [
    { key: 'product_code', title: '产品编号', required: true, fixed: 'left' },
    { key: 'product_name', title: '产品名称' },
    { key: 'stock_qty', title: '库存数量' },
    { key: 'last_count_qty', title: '上次盘点' },
    { key: 'safety_stock', title: '安全库存' },
    { key: 'stock_status', title: '库存状态' },
    { key: 'remark', title: '备注' },
    { key: 'updated_at', title: '更新时间' },
    { key: 'actions', title: '操作', settingsHidden: true, fixed: 'right', protectedWidth: 90 }
  ]
}

export function Inventory() {
  const { message } = App.useApp()
  const [filterForm] = Form.useForm<FilterValues>()
  const [editForm] = Form.useForm<InventoryFormValues>()
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [data, setData] = useState<InventoryDto[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [productOptions, setProductOptions] = useState<ProductSearchDto[]>([])
  const [productLoading, setProductLoading] = useState(false)
  const [visibleExportColumns, setVisibleExportColumns] = useState<DataTableVisibleColumn[]>([])
  const [submittedFilters, setSubmittedFilters] = useState<FilterValues>({ hide_zero_safety_stock: true })
  const params = useMemo<InventoryListParams>(() => {
    return {
      product_code: submittedFilters.product_code?.trim() || undefined,
      product_name: submittedFilters.product_name?.trim() || undefined,
      stock_status: submittedFilters.stock_status || undefined,
      hide_zero_safety_stock: submittedFilters.hide_zero_safety_stock !== false,
      page,
      page_size: pageSize
    }
  }, [submittedFilters, page, pageSize])

  async function load() {
    setLoading(true)
    try {
      const resp = await listInventory(params)
      setData(resp.items || [])
      setTotal(resp.total || 0)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [params])

  async function searchProducts(keyword: string) {
    setProductLoading(true)
    try {
      setProductOptions(await searchProductsForInventory(keyword))
    } finally {
      setProductLoading(false)
    }
  }

  async function openCreate() {
    setEditingId(null)
    editForm.resetFields()
    editForm.setFieldsValue({ stock_qty: 0, last_count_qty: 0, safety_stock: 0, remark: '' })
    await searchProducts('')
    setDrawerOpen(true)
  }

  function openEdit(row: InventoryDto) {
    setEditingId(row.id)
    setProductOptions([
      {
        id: row.product_id,
        product_code: row.product_code,
        internal_name: row.product_name,
        safety_stock: row.safety_stock
      }
    ])
    editForm.setFieldsValue({
      product_id: row.product_id,
      stock_qty: row.stock_qty,
      last_count_qty: row.last_count_qty,
      safety_stock: row.safety_stock ?? 0,
      remark: row.remark || ''
    })
    setDrawerOpen(true)
  }

  async function onSave() {
    const values = await editForm.validateFields()
    if (!values.product_id) {
      message.warning('请选择产品')
      return
    }
    const payload: InventoryPayload = {
      product_id: values.product_id,
      stock_qty: values.stock_qty ?? 0,
      last_count_qty: values.last_count_qty ?? 0,
      safety_stock: values.safety_stock ?? 0,
      remark: values.remark || ''
    }
    setSaving(true)
    try {
      if (editingId) await updateInventory(editingId, payload)
      else await createInventory(payload)
      message.success('已保存')
      setDrawerOpen(false)
      await load()
    } finally {
      setSaving(false)
    }
  }

  async function onImportChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    const result = await importInventory(file)
    const text = `新增 ${result.created || 0} 条，更新 ${result.updated || 0} 条，失败 ${result.failed || 0} 条`
    if (result.failed) message.warning(text)
    else message.success(text)
    await load()
  }

  async function onExport() {
    const blob = await exportInventoryBlob({
      ...params,
      columns: visibleExportColumns.length ? visibleExportColumns.map((column) => column.key).join(',') : undefined
    })
    downloadBlob(blob, `inventory_${Date.now()}.xlsx`)
    message.success('已导出')
  }

  async function onDownloadImportTemplate() {
    const blob = await downloadInventoryImportTemplateBlob()
    downloadBlob(blob, 'inventory_import_template.xlsx')
    message.success('已下载导入模版')
  }

  const columns: ColumnsType<InventoryDto> = [
    { title: '产品编号', dataIndex: 'product_code', width: 130, fixed: 'left' },
    { title: '产品名称', dataIndex: 'product_name', width: 280, ellipsis: true },
    { title: '库存数量', dataIndex: 'stock_qty', width: 100 },
    { title: '上次盘点', dataIndex: 'last_count_qty', width: 100 },
    { title: '安全库存', dataIndex: 'safety_stock', width: 100 },
    {
      title: '库存状态',
      dataIndex: 'stock_status',
      width: 100,
      render: (value) => (value ? <Tag color={value === '低库存' ? 'warning' : 'success'}>{value}</Tag> : '-')
    },
    { title: '备注', dataIndex: 'remark', width: 200, ellipsis: true },
    { title: '更新时间', dataIndex: 'updated_at', width: 170, render: (value) => formatTime(value, true) },
    {
      key: 'actions',
      title: '操作',
      width: 90,
      fixed: 'right',
      render: (_, row) => (
        <Button type="link" size="small" onClick={() => openEdit(row)}>
          编辑
        </Button>
      )
    }
  ]

  const pagination: TablePaginationConfig = {
    current: page,
    pageSize,
    total,
    pageSizeOptions: [50, 100, 500],
    showSizeChanger: true,
    showTotal: (value) => `共 ${value} 条`,
    onChange: (nextPage, nextPageSize) => {
      setPage(nextPage)
      setPageSize(nextPageSize)
    }
  }

  return (
    <div className="page-card">
      <div className="orders-header">
        <h2>产品库存</h2>
        <Space wrap>
          <input ref={fileInputRef} hidden type="file" accept=".xlsx" onChange={onImportChange} />
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
            新增库存
          </Button>
        </Space>
      </div>
      <Form
        form={filterForm}
        layout="inline"
        initialValues={{ hide_zero_safety_stock: true }}
        className="orders-filter"
        onFinish={(values) => {
          setSubmittedFilters(values)
          setPage(1)
        }}
      >
        <Form.Item label="产品编号" name="product_code">
          <Input allowClear placeholder="输入产品编号" style={{ width: 160 }} />
        </Form.Item>
        <Form.Item label="产品名称" name="product_name">
          <Input allowClear placeholder="输入产品名称" style={{ width: 200 }} />
        </Form.Item>
        <Form.Item label="库存状态" name="stock_status">
          <Select
            allowClear
            placeholder="全部状态"
            style={{ width: 140 }}
            options={[
              { value: 'normal', label: '正常' },
              { value: 'low', label: '低库存' }
            ]}
          />
        </Form.Item>
        <Form.Item name="hide_zero_safety_stock" valuePropName="checked">
          <Checkbox>安全库存为0不显示</Checkbox>
        </Form.Item>
        <Form.Item>
          <Space>
            <Button type="primary" htmlType="submit">
              查询
            </Button>
            <Button
              onClick={() => {
                const nextFilters = { hide_zero_safety_stock: true }
                filterForm.resetFields()
                setSubmittedFilters(nextFilters)
                setPage(1)
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
        dataSource={data}
        columns={columns}
        tableConfig={INVENTORY_TABLE_CONFIG}
        onVisibleColumnsChange={setVisibleExportColumns}
        pagination={pagination}
        onRow={(row) => ({
          onDoubleClick: (event) => {
            if (shouldIgnoreTableRowDoubleClick(event.target)) return
            openEdit(row)
          }
        })}
      />
      <Modal
        open={drawerOpen}
        title={editingId ? '编辑库存' : '新增库存'}
        className="inventory-edit-modal"
        width="min(920px, 96vw)"
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
          layout="horizontal"
          colon={false}
          labelAlign="left"
          labelCol={{ flex: '88px' }}
          wrapperCol={{ flex: '1 1 0' }}
          className="inventory-edit-form"
        >
          <div className="inventory-edit-layout">
            <section className="inventory-edit-panel">
              <div className="inventory-edit-panel__title">产品信息</div>
              <Form.Item label="产品" name="product_id" rules={[{ required: true, message: '请选择产品' }]}>
                <Select
                  showSearch
                  allowClear
                  filterOption={false}
                  loading={productLoading}
                  placeholder="搜索产品名称或编号"
                  onSearch={searchProducts}
                  onChange={(productId) => {
                    const product = productOptions.find((item) => item.id === productId)
                    editForm.setFieldValue('safety_stock', product?.safety_stock ?? 0)
                  }}
                  options={productOptions.map((p) => ({
                    value: p.id,
                    label: `${p.product_code} / ${p.internal_name}`
                  }))}
                />
              </Form.Item>
              <Form.Item
                label="安全库存"
                name="safety_stock"
                rules={[
                  { required: true, message: '请输入安全库存' },
                  { type: 'number', min: 0, message: '安全库存不能小于 0' }
                ]}
              >
                <InputNumber min={0} precision={0} style={{ width: '100%' }} />
              </Form.Item>
            </section>
            <section className="inventory-edit-panel">
              <div className="inventory-edit-panel__title">库存信息</div>
              <div className="inventory-edit-stock-grid">
                <Form.Item label="库存数量" name="stock_qty">
                  <InputNumber min={0} precision={0} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item label="上次盘点" name="last_count_qty">
                  <InputNumber min={0} precision={0} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item label="备注" name="remark" className="inventory-edit-field--full">
                  <Input.TextArea rows={5} maxLength={500} showCount />
                </Form.Item>
              </div>
            </section>
          </div>
        </Form>
      </Modal>
    </div>
  )
}
