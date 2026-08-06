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
  deletePurchaseOrder,
  exportPurchaseOrdersBlob,
  getPurchaseOrderDetail,
  listPurchaseOrders,
  listUserOptions,
  releasePurchaseOrderLock,
  updatePurchaseOrder,
  updatePurchaseOrderItem,
  type PurchaseOrderDetailDto,
  type PurchaseOrderDto,
  type PurchaseOrderItemDto,
  type PurchaseOrderListParams,
  type UserOptionDto
} from '@/api/purchase'
import { downloadBlob } from '@/utils/download'
import { formatTime } from '@/utils/format'

interface FilterValues {
  purchase_no?: string
  purchaseRange?: [Dayjs, Dayjs]
}

const PURCHASE_ORDERS_TABLE_CONFIG: DataTableConfig = {
  tableKey: 'purchase-orders.list',
  primaryColumnKey: 'purchase_no',
  widthMode: 'adaptive-left',
  columns: [
    { key: 'purchase_no', title: '采购单号', required: true, fixed: 'left' },
    { key: 'purchase_date', title: '采购日期' },
    { key: 'source_count', title: '来源明细数' },
    { key: 'item_count', title: '采购明细数' },
    { key: 'total_required_qty', title: '总需求数量' },
    { key: 'created_by', title: '创建人' },
    { key: 'created_at', title: '创建时间' },
    { key: 'remark', title: '备注' },
    { key: 'actions', title: '操作', settingsHidden: true, fixed: 'right', protectedWidth: 100 }
  ]
}

export function PurchaseOrders() {
  const { message } = App.useApp()
  const [form] = Form.useForm<FilterValues>()
  const [editForm] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<PurchaseOrderDto[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [detail, setDetail] = useState<PurchaseOrderDetailDto | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [dirtyItemIds, setDirtyItemIds] = useState<Set<number>>(new Set())
  const [users, setUsers] = useState<UserOptionDto[]>([])
  const [submittedFilters, setSubmittedFilters] = useState<FilterValues>({})

  const params = useMemo<PurchaseOrderListParams & { purchase_start?: string; purchase_end?: string }>(() => {
    return {
      page,
      page_size: pageSize,
      purchase_no: submittedFilters.purchase_no?.trim() || undefined,
      purchase_start: submittedFilters.purchaseRange?.[0]?.format('YYYY-MM-DD'),
      purchase_end: submittedFilters.purchaseRange?.[1]?.format('YYYY-MM-DD')
    }
  }, [submittedFilters, page, pageSize])

  async function load() {
    setLoading(true)
    try {
      const resp = await listPurchaseOrders(params)
      setData(resp.items)
      setTotal(resp.total)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [params])

  async function ensureUsers() {
    if (users.length) return
    try {
      setUsers(await listUserOptions())
    } catch {
      setUsers([])
    }
  }

  async function openDetail(row: PurchaseOrderDto) {
    try {
      await ensureUsers()
      const lock = await acquirePurchaseOrderLock(row.id)
      if (!lock.lock_acquired) {
        message.warning(lock.message || '采购单当前不可编辑')
        return
      }
      const next = await getPurchaseOrderDetail(row.id)
      setDetail(next)
      setDirtyItemIds(new Set())
      editForm.setFieldsValue({
        purchase_date: next.purchase_date ? next.purchase_date : null,
        remark: next.remark || ''
      })
      setDetailOpen(true)
    } catch (e) {
      const detailText = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      message.error(detailText || '打开采购单失败')
    }
  }

  async function closeDetail() {
    const purchaseOrderId = detail?.id
    setDetailOpen(false)
    setDetail(null)
    setDirtyItemIds(new Set())
    editForm.resetFields()
    if (purchaseOrderId) {
      await releasePurchaseOrderLock(purchaseOrderId).catch(() => undefined)
    }
  }

  function updateDetailItem(itemId: number, patch: Partial<PurchaseOrderItemDto>) {
    setDetail((current) => {
      if (!current) return current
      return {
        ...current,
        items: current.items.map((item) => (item.id === itemId ? { ...item, ...patch } : item))
      }
    })
    setDirtyItemIds((current) => {
      const next = new Set(current)
      next.add(itemId)
      return next
    })
  }

  function syncBuyerName(itemId: number, buyerUserId: number | null) {
    const user = users.find((item) => item.id === buyerUserId)
    updateDetailItem(itemId, {
      buyer_user_id: buyerUserId,
      buyer: user?.display_name || user?.username || ''
    })
  }

  async function persistDetail(successMessage = '已保存') {
    if (!detail) return
    try {
      const values = await editForm.validateFields()
      const headerPayload = {
        purchase_date: values.purchase_date || null,
        remark: values.remark || ''
      }
      const dirtyItems = detail.items.filter((item) => dirtyItemIds.has(item.id))
      await Promise.all(
        dirtyItems.map((item) =>
          updatePurchaseOrderItem(detail.id, item.id, {
            buyer_user_id: item.buyer_user_id,
            buyer: item.buyer,
            total_cost_record: item.total_cost_record,
            purchase_cost: item.purchase_cost,
            purchase_channel: item.purchase_channel || '',
            purchase_qty: item.purchase_qty || 0,
            remark: item.remark || ''
          })
        )
      )
      await updatePurchaseOrder(detail.id, headerPayload)
      const next = await getPurchaseOrderDetail(detail.id)
      setDetail(next)
      setDirtyItemIds(new Set())
      editForm.setFieldsValue({
        purchase_date: next.purchase_date ? next.purchase_date : null,
        remark: next.remark || ''
      })
      if (successMessage) message.success(successMessage)
      load()
      return true
    } catch (e) {
      const detailText = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      message.error(detailText || '保存失败')
      return false
    }
  }

  function removeRow(row: PurchaseOrderDto, options?: { closeAfterDelete?: boolean }) {
    Modal.confirm({
      title: '删除确认',
      content: `确认删除采购单「${row.purchase_no}」吗？`,
      centered: true,
      okType: 'danger',
      onOk: async () => {
        await deletePurchaseOrder(row.id)
        message.success('已删除')
        if (options?.closeAfterDelete) {
          await closeDetail()
        }
        await load()
      }
    })
  }

  async function onExport() {
    setExporting(true)
    try {
      const blob = await exportPurchaseOrdersBlob({ ...params, page: undefined, page_size: undefined })
      downloadBlob(blob, `purchase-orders-${Date.now()}.xlsx`)
      message.success('已导出')
    } finally {
      setExporting(false)
    }
  }

  const columns: ColumnsType<PurchaseOrderDto> = [
    { title: '采购单号', dataIndex: 'purchase_no', width: 150, fixed: 'left' },
    { title: '采购日期', dataIndex: 'purchase_date', width: 120 },
    { title: '来源明细数', dataIndex: 'source_count', width: 110, align: 'right' },
    { title: '采购明细数', dataIndex: 'item_count', width: 110, align: 'right' },
    { title: '总需求数量', dataIndex: 'total_required_qty', width: 110, align: 'right' },
    { title: '创建人', dataIndex: 'created_by', width: 110 },
    { title: '创建时间', dataIndex: 'created_at', width: 170, render: (v) => formatTime(v) },
    { title: '备注', dataIndex: 'remark', ellipsis: true, width: 240 },
    {
      key: 'actions',
      title: '操作',
      width: 100,
      fixed: 'right',
      render: (_, row) => (
        <Space size={4}>
          <Button type="link" size="small" onClick={() => openDetail(row)}>
            查看/编辑
          </Button>
        </Space>
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

  function renderDetailFooter() {
    return (
      <Space>
        <Button type="primary" onClick={() => persistDetail('采购信息已保存')}>
          保存
        </Button>
        <Button danger onClick={() => detail && removeRow(detail, { closeAfterDelete: true })}>
          删除
        </Button>
      </Space>
    )
  }

  return (
    <div className="page-card">
      <div className="orders-header">
        <h2>采购单管理</h2>
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
        <Form.Item label="采购日期" name="purchaseRange">
          <DatePicker.RangePicker style={{ width: 240 }} />
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
        rowKey="id"
        loading={loading}
        dataSource={data}
        columns={columns}
        tableConfig={PURCHASE_ORDERS_TABLE_CONFIG}
        pagination={pagination}
        onRow={(row) => ({ onDoubleClick: () => openDetail(row) })}
      />
      <Modal
        open={detailOpen}
        title={detail ? `${detail.purchase_no} 详情` : '采购单详情'}
        className="purchase-detail-modal"
        width="min(1520px, 96vw)"
        footer={renderDetailFooter()}
        onCancel={closeDetail}
      >
        <div className="purchase-detail-layout">
          <section className="purchase-detail-side">
            <div className="purchase-detail-side__title">采购信息</div>
            <Form
              form={editForm}
              layout="horizontal"
              className="purchase-detail-header"
              colon={false}
              labelAlign="left"
              labelCol={{ flex: '72px' }}
              wrapperCol={{ flex: '1 1 0' }}
            >
              <Form.Item label="采购日期" name="purchase_date">
                <Input placeholder="YYYY-MM-DD" />
              </Form.Item>
              <Form.Item label="创建时间">
                <Input disabled value={formatTime(detail?.created_at)} />
              </Form.Item>
              <Form.Item label="备注" name="remark">
                <Input />
              </Form.Item>
            </Form>
          </section>
          <section className="purchase-detail-main">
            <h3 className="purchase-detail-title">采购明细</h3>
            <div className="purchase-detail-table-shell">
              <DataTable
                rowKey="id"
                size="small"
                className="purchase-detail-table"
                pagination={false}
                scroll={{ y: 'calc(100vh - 340px)' }}
                dataSource={detail?.items || []}
                columns={[
                  { title: '产品', dataIndex: 'product_name', width: 280 },
                  { title: '需求数量', dataIndex: 'required_qty', width: 90 },
                  {
                    title: '采购人',
                    dataIndex: 'buyer_user_id',
                    width: 160,
                    render: (value, row) => (
                      <Select
                        allowClear
                        showSearch
                        optionFilterProp="label"
                        placeholder="选择采购人"
                        value={value}
                        style={{ width: '100%' }}
                        options={users.map((user) => ({
                          value: user.id,
                          label: user.display_name || user.username
                        }))}
                        onChange={(next) => syncBuyerName(row.id, next ?? null)}
                      />
                    )
                  },
                  {
                    title: '总表成本记录',
                    dataIndex: 'total_cost_record',
                    width: 120,
                    render: (value, row) => (
                      <InputNumber
                        min={0}
                        precision={2}
                        value={value}
                        style={{ width: '100%' }}
                        onChange={(next) => updateDetailItem(row.id, { total_cost_record: next == null ? null : Number(next) })}
                      />
                    )
                  },
                  {
                    title: '采购数量',
                    dataIndex: 'purchase_qty',
                    width: 110,
                    render: (value, row) => (
                      <InputNumber
                        min={0}
                        precision={0}
                        value={value}
                        style={{ width: '100%' }}
                        onChange={(next) => updateDetailItem(row.id, { purchase_qty: Number(next || 0) })}
                      />
                    )
                  },
                  {
                    title: '采购成本',
                    dataIndex: 'purchase_cost',
                    width: 120,
                    render: (value, row) => (
                      <InputNumber
                        min={0}
                        precision={2}
                        value={value}
                        style={{ width: '100%' }}
                        onChange={(next) => updateDetailItem(row.id, { purchase_cost: next == null ? null : Number(next) })}
                      />
                    )
                  },
                  {
                    title: '采购渠道',
                    dataIndex: 'purchase_channel',
                    width: 180,
                    render: (value, row) => (
                      <Input
                        value={value}
                        onChange={(event) => updateDetailItem(row.id, { purchase_channel: event.target.value })}
                      />
                    )
                  },
                  {
                    title: '备注',
                    dataIndex: 'remark',
                    width: 220,
                    render: (value, row) => (
                      <Input
                        value={value}
                        onChange={(event) => updateDetailItem(row.id, { remark: event.target.value })}
                      />
                    )
                  }
                ]}
              />
            </div>
          </section>
        </div>
      </Modal>
    </div>
  )
}
