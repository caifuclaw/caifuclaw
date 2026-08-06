/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { useEffect, useMemo, useState } from 'react'
import { ExportOutlined } from '@ant-design/icons'
import { App, Button, DatePicker, Form, Input, InputNumber, Modal, Select, Space } from 'antd'
import { DataTable } from '@/components/DataTable'
import type { DataTableConfig } from '@/components/DataTable'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import type { Dayjs } from 'dayjs'
import {
  acquirePurchaseOrderLock,
  exportPurchaseDetailsBlob,
  listPurchaseDetails,
  listUserOptions,
  releasePurchaseOrderLock,
  updatePurchaseOrderItem,
  type PurchaseDetailDto,
  type PurchaseDetailListParams,
  type UserOptionDto
} from '@/api/purchase'
import { downloadBlob } from '@/utils/download'
import { formatDate, formatMoney } from '@/utils/format'

interface FilterValues {
  purchase_no?: string
  product_name?: string
  pickingRange?: [Dayjs, Dayjs]
  buyer?: string
}

const PURCHASE_DETAILS_TABLE_CONFIG: DataTableConfig = {
  tableKey: 'purchase-details.list',
  primaryColumnKey: 'purchase_no',
  widthMode: 'adaptive-left',
  columns: [
    { key: 'purchase_no', title: '采购单号', required: true, fixed: 'left' },
    { key: 'purchase_date', title: '采购日期' },
    { key: 'picking_date', title: '配货日' },
    { key: 'product_name', title: '产品名称' },
    { key: 'daily_order_qty', title: '订单数量' },
    { key: 'stock_qty', title: '库存' },
    { key: 'pending_purchase_qty', title: '待采购' },
    { key: 'buyer', title: '采购员' },
    { key: 'purchase_cost', title: '采购成本' },
    { key: 'purchase_channel', title: '采购渠道' },
    { key: 'purchase_qty', title: '采购数量' },
    { key: 'remark', title: '备注' }
  ]
}

export function PurchaseDetails() {
  const { message } = App.useApp()
  const [form] = Form.useForm<FilterValues>()
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<PurchaseDetailDto[]>([])
  const [users, setUsers] = useState<UserOptionDto[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [editing, setEditing] = useState<PurchaseDetailDto | null>(null)
  const [editOpen, setEditOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [submittedFilters, setSubmittedFilters] = useState<FilterValues>({})

  const params = useMemo<PurchaseDetailListParams>(() => {
    return {
      page,
      page_size: pageSize,
      purchase_no: submittedFilters.purchase_no?.trim() || undefined,
      product_name: submittedFilters.product_name?.trim() || undefined,
      picking_start: submittedFilters.pickingRange?.[0]?.format('YYYY-MM-DD'),
      picking_end: submittedFilters.pickingRange?.[1]?.format('YYYY-MM-DD'),
      buyer: submittedFilters.buyer?.trim() || undefined
    }
  }, [submittedFilters, page, pageSize])

  async function load() {
    setLoading(true)
    try {
      const resp = await listPurchaseDetails(params)
      setData(resp.items)
      setTotal(resp.total)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [params])

  useEffect(() => {
    listUserOptions()
      .then(setUsers)
      .catch(() => setUsers([]))
  }, [])

  function updateEditing(patch: Partial<PurchaseDetailDto>) {
    setEditing((current) => (current ? { ...current, ...patch } : current))
  }

  function syncBuyerName(buyerUserId: number | null) {
    const user = users.find((item) => item.id === buyerUserId)
    updateEditing({
      buyer_user_id: buyerUserId,
      buyer: user?.display_name || user?.username || ''
    })
  }

  async function openEdit(row: PurchaseDetailDto) {
    try {
      const lock = await acquirePurchaseOrderLock(row.purchase_order_id)
      if (!lock.lock_acquired) {
        message.warning(lock.message || '采购单当前不可编辑')
        return
      }
      setEditing(row)
      setEditOpen(true)
    } catch (e) {
      const detailText = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      message.error(detailText || '打开采购明细失败')
    }
  }

  async function closeEdit() {
    const purchaseOrderId = editing?.purchase_order_id
    setEditOpen(false)
    setEditing(null)
    if (purchaseOrderId) {
      await releasePurchaseOrderLock(purchaseOrderId).catch(() => undefined)
    }
  }

  async function saveEdit() {
    if (!editing) return
    setSaving(true)
    try {
      await updatePurchaseOrderItem(editing.purchase_order_id, editing.item_id, {
        buyer_user_id: editing.buyer_user_id,
        buyer: editing.buyer,
        total_cost_record: editing.total_cost_record,
        purchase_cost: editing.purchase_cost,
        purchase_channel: editing.purchase_channel || '',
        purchase_qty: editing.purchase_qty || 0,
        remark: editing.remark || ''
      })
      message.success('采购明细已保存')
      await closeEdit()
      await load()
    } catch (e) {
      const detailText = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      message.error(detailText || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  async function onExport() {
    setExporting(true)
    try {
      const blob = await exportPurchaseDetailsBlob({ ...params, page: undefined, page_size: undefined })
      downloadBlob(blob, `purchase-details-${Date.now()}.xlsx`)
      message.success('已导出')
    } finally {
      setExporting(false)
    }
  }

  function renderEditTitle() {
    return (
      <div className="purchase-item-edit-title">
        <span className="purchase-item-edit-title__main">编辑采购明细</span>
        <span className="purchase-item-edit-title__sub">{editing?.purchase_no || '-'}</span>
      </div>
    )
  }

  const columns: ColumnsType<PurchaseDetailDto> = [
    { title: '采购单号', dataIndex: 'purchase_no', width: 150 },
    { title: '采购日期', dataIndex: 'purchase_date', width: 120, render: (v) => formatDate(v) },
    { title: '配货日', dataIndex: 'picking_date', width: 120, render: (v) => formatDate(v) },
    { title: '产品名称', dataIndex: 'product_name', width: 240, ellipsis: true },
    { title: '订单数量', dataIndex: 'daily_order_qty', width: 100, align: 'right' },
    { title: '库存', dataIndex: 'stock_qty', width: 90, align: 'right' },
    { title: '待采购', dataIndex: 'pending_purchase_qty', width: 100, align: 'right' },
    { title: '采购员', dataIndex: 'buyer', width: 120 },
    { title: '采购成本', dataIndex: 'purchase_cost', width: 120, render: (v) => formatMoney(v, 'CNY') },
    { title: '采购渠道', dataIndex: 'purchase_channel', width: 140 },
    { title: '采购数量', dataIndex: 'purchase_qty', width: 100, align: 'right' },
    { title: '备注', dataIndex: 'remark', ellipsis: true }
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
        <h2>采购明细</h2>
        <Button icon={<ExportOutlined />} loading={exporting} onClick={onExport}>
          导出
        </Button>
      </div>
      <Form
        form={form}
        layout="inline"
        className="orders-filter"
        onFinish={(values) => {
          setSubmittedFilters(values)
          setPage(1)
        }}
      >
        <Form.Item label="采购单号" name="purchase_no">
          <Input allowClear placeholder="输入采购单号" style={{ width: 200 }} />
        </Form.Item>
        <Form.Item label="产品名称" name="product_name">
          <Input allowClear placeholder="输入产品名称" style={{ width: 220 }} />
        </Form.Item>
        <Form.Item label="配货日" name="pickingRange">
          <DatePicker.RangePicker style={{ width: 240 }} />
        </Form.Item>
        <Form.Item label="采购员" name="buyer">
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="请选择采购员"
            style={{ width: 180 }}
            options={users.map((user) => ({
              value: user.display_name || user.username,
              label: user.display_name || user.username
            }))}
          />
        </Form.Item>
        <Form.Item>
          <Space>
            <Button type="primary" htmlType="submit">
              查询
            </Button>
            <Button
              onClick={() => {
                form.resetFields()
                setSubmittedFilters({})
                setPage(1)
              }}
            >
              重置
            </Button>
          </Space>
        </Form.Item>
      </Form>
      <DataTable
        rowKey={(row) => `${row.purchase_order_id}-${row.item_id}`}
        loading={loading}
        dataSource={data}
        columns={columns}
        tableConfig={PURCHASE_DETAILS_TABLE_CONFIG}
        pagination={pagination}
        onRow={(row) => ({ onDoubleClick: () => openEdit(row) })}
      />
      <Modal
        open={editOpen}
        title={renderEditTitle()}
        className="purchase-item-edit-modal"
        width="min(840px, 94vw)"
        onCancel={closeEdit}
        footer={
          <div className="purchase-item-edit-actions">
            <Button onClick={closeEdit}>取消</Button>
            <Button type="primary" loading={saving} onClick={saveEdit}>
              保存
            </Button>
          </div>
        }
      >
        <Form layout="vertical" className="purchase-item-edit-form">
          <div className="purchase-item-edit-summary">
            <span className="purchase-item-edit-summary__label">产品</span>
            <span className="purchase-item-edit-summary__value">{editing?.product_name || '-'}</span>
          </div>
          <div className="purchase-item-edit-grid">
            <Form.Item label="采购人" className="purchase-item-edit-field">
              <Select
                allowClear
                showSearch
                optionFilterProp="label"
                placeholder="选择采购人"
                value={editing?.buyer_user_id}
                style={{ width: '100%' }}
                options={users.map((user) => ({
                  value: user.id,
                  label: user.display_name || user.username
                }))}
                onChange={(next) => syncBuyerName(next ?? null)}
              />
            </Form.Item>
            <Form.Item label="总表成本记录" className="purchase-item-edit-field">
              <InputNumber
                min={0}
                precision={2}
                value={editing?.total_cost_record}
                style={{ width: '100%' }}
                onChange={(next) => updateEditing({ total_cost_record: next == null ? null : Number(next) })}
              />
            </Form.Item>
            <Form.Item label="采购数量" className="purchase-item-edit-field">
              <InputNumber
                min={0}
                precision={0}
                value={editing?.purchase_qty}
                style={{ width: '100%' }}
                onChange={(next) => updateEditing({ purchase_qty: Number(next || 0) })}
              />
            </Form.Item>
            <Form.Item label="采购成本" className="purchase-item-edit-field">
              <InputNumber
                min={0}
                precision={2}
                value={editing?.purchase_cost}
                style={{ width: '100%' }}
                onChange={(next) => updateEditing({ purchase_cost: next == null ? null : Number(next) })}
              />
            </Form.Item>
            <Form.Item label="采购渠道" className="purchase-item-edit-field purchase-item-edit-field--wide">
              <Input
                value={editing?.purchase_channel}
                style={{ width: '100%' }}
                onChange={(event) => updateEditing({ purchase_channel: event.target.value })}
              />
            </Form.Item>
            <Form.Item label="备注" className="purchase-item-edit-field purchase-item-edit-field--full">
              <Input.TextArea
                value={editing?.remark}
                autoSize={{ minRows: 3, maxRows: 5 }}
                onChange={(event) => updateEditing({ remark: event.target.value })}
              />
            </Form.Item>
          </div>
        </Form>
      </Modal>
    </div>
  )
}
