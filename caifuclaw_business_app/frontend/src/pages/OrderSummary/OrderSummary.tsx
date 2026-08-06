import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from '@/router/navigation'
import { ExportOutlined, ShoppingCartOutlined } from '@ant-design/icons'
import { App, Button, Checkbox, DatePicker, Descriptions, Form, Input, Modal, Select, Space, Spin, Tabs, Tag } from 'antd'
import { DataTable } from '@/components/DataTable'
import type { DataTableColumnsType, DataTableConfig, DataTableVisibleColumn } from '@/components/DataTable'
import type { TablePaginationConfig } from 'antd/es/table'
import type { Dayjs } from 'dayjs'
import { fetchOrderDetail, type OrderDetailDto, type OrderDetailItemDto } from '@/api/orders'
import { OrderOperationLogTable } from '@/components/OrderOperationLogTable'
import { ShopMultiSelect } from '@/components/ShopMultiSelect'
import {
  exportOrderSummaryBlob,
  generatePurchaseOrder,
  listOrderSummary,
  type OrderSummaryDto,
  type OrderSummaryParams
} from '@/api/purchase'
import { useEnabledPlatformOptions } from '@/hooks/useEnabledPlatformOptions'
import { formatPlatformLabel, ORDER_STATUS_COLOR, ORDER_STATUSES } from '@/stores/dict'
import { downloadBlob } from '@/utils/download'
import { formatTime } from '@/utils/format'
import './OrderSummary.less'

interface FilterValues {
  status?: string
  platform?: string
  shopIds?: number[]
  number?: string
  productKeyword?: string
  warning?: string
  paymentRange?: [Dayjs, Dayjs]
  pickingRange?: [Dayjs, Dayjs]
  oldCustomerOnly?: boolean
}

const ORDER_DETAIL_MODAL_WIDTH = 1300
const ORDER_DETAIL_MODAL_BODY_HEIGHT = 'min(700px, calc(100dvh - 120px))'
const ORDER_SUMMARY_STATUS_OPTIONS = ORDER_STATUSES.filter((status) => status.code !== 'pending')

const ORDER_SUMMARY_TABLE_CONFIG: DataTableConfig = {
  tableKey: 'order-summary.list',
  primaryColumnKey: 'order_no',
  widthMode: 'adaptive-left',
  columns: [
    { key: 'picking_at', title: '配货日' },
    { key: 'platform', title: '平台' },
    { key: 'shop_name', title: '店铺名' },
    { key: 'platform_created_at', title: '创建时间' },
    { key: 'order_no', title: '订单编号', required: true, fixed: false },
    { key: 'status', title: '状态' },
    { key: 'platform_status', title: '平台状态' },
    { key: 'country_name_cn', title: '国家' },
    { key: 'customer_name', title: '客户姓名' },
    { key: 'sku', title: 'SKU' },
    { key: 'platform_product_name', title: '产品名称' },
    { key: 'quantity', title: '数量' },
    { key: 'unit_price', title: '单价' },
    { key: 'currency', title: '币种' },
    { key: 'buyer_selected_logistics', title: '自选物流' },
    { key: 'shipping_deadline_at', title: '最后发货期限' },
    { key: 'shipment_tracking_number', title: '货运单号' },
    { key: 'dispatch_deadline_at', title: '发出截止时间' },
    { key: 'product_name', title: '产品中文名称' },
    { key: 'customer_confirm', title: '客户确认' },
    { key: 'warning', title: '预警' },
    { key: 'purchase_no', title: '采购单号' },
    { key: 'shipping_time', title: 'Shipping time' }
  ]
}

export function OrderSummary() {
  const navigate = useNavigate()
  const { message } = App.useApp()
  const [form] = Form.useForm<FilterValues>()
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<OrderSummaryDto[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [selectedRows, setSelectedRows] = useState<OrderSummaryDto[]>([])
  const [exporting, setExporting] = useState(false)
  const [visibleExportColumns, setVisibleExportColumns] = useState<DataTableVisibleColumn[]>([])
  const [submittedFilters, setSubmittedFilters] = useState<FilterValues>({ status: 'all' })
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detail, setDetail] = useState<OrderDetailDto | null>(null)
  const platformOptions = useEnabledPlatformOptions()
  const selectedPlatform = Form.useWatch('platform', form)

  function submitFilters(values: FilterValues) {
    setSubmittedFilters(values)
    setPage(1)
    setSelectedRowKeys([])
    setSelectedRows([])
  }

  function resetFilters() {
    form.resetFields()
    submitFilters({ status: 'all' })
  }

  const queryParams = useMemo<OrderSummaryParams>(() => {
    return {
      status: submittedFilters.status && !['all', 'pending'].includes(submittedFilters.status) ? submittedFilters.status : undefined,
      platform: submittedFilters.platform,
      shop_ids: submittedFilters.shopIds?.length ? submittedFilters.shopIds.join(',') : undefined,
      number: submittedFilters.number?.trim() || undefined,
      product_keyword: submittedFilters.productKeyword?.trim() || undefined,
      warning: submittedFilters.warning && submittedFilters.warning !== 'all' ? submittedFilters.warning : undefined,
      payment_start: submittedFilters.paymentRange?.[0]?.format('YYYY-MM-DD'),
      payment_end: submittedFilters.paymentRange?.[1]?.format('YYYY-MM-DD'),
      picking_start: submittedFilters.pickingRange?.[0]?.format('YYYY-MM-DD'),
      picking_end: submittedFilters.pickingRange?.[1]?.format('YYYY-MM-DD'),
      old_customer_only: submittedFilters.oldCustomerOnly || undefined,
      page,
      page_size: pageSize
    }
  }, [page, pageSize, submittedFilters])

  async function load() {
    setLoading(true)
    try {
      const resp = await listOrderSummary(queryParams)
      setData(resp.items || [])
      setTotal(resp.total || 0)
      setSelectedRowKeys([])
      setSelectedRows([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [queryParams])

  async function onGeneratePurchase() {
    const itemIds = Array.from(new Set(selectedRows.map((row) => row.item_id)))
    if (!itemIds.length) {
      message.warning('请先选择订单明细')
      return
    }
    const resp = await generatePurchaseOrder(itemIds)
    message.success(`已生成采购单 ${resp.purchase_no}`)
    await load()
    navigate('/purchase-orders')
  }

  async function onExport() {
    setExporting(true)
    try {
      const exportParams: OrderSummaryParams & { item_ids?: string; columns?: string } = {
        ...queryParams,
        page: undefined,
        page_size: undefined,
        lazy: undefined,
        item_ids: selectedRowKeys.length ? selectedRowKeys.map(String).join(',') : undefined,
        columns: visibleExportColumns.length ? visibleExportColumns.map((column) => column.key).join(',') : undefined
      }
      const blob = await exportOrderSummaryBlob(exportParams)
      downloadBlob(blob, `order-summary-${Date.now()}.xlsx`)
      message.success('已导出')
    } finally {
      setExporting(false)
    }
  }

  async function openDetail(row: OrderSummaryDto) {
    setDetailOpen(true)
    setDetailLoading(true)
    try {
      setDetail(await fetchOrderDetail(row.order_id))
    } finally {
      setDetailLoading(false)
    }
  }

  function detailOrderNumber(order: OrderDetailDto): string {
    return order.platform_order_no || order.posting_number || order.platform_order_id || String(order.id)
  }

  const columns: DataTableColumnsType<OrderSummaryDto> = [
    {
      title: '配货日',
      dataIndex: 'picking_at',
      width: 158,
      responsiveWidth: { mobile: 142, tablet: 150, desktop: 158 },
      render: (v) => formatTime(v, true)
    },
    {
      title: '平台',
      dataIndex: 'platform',
      width: 110,
      responsiveWidth: { mobile: 92, tablet: 100, desktop: 110 },
      render: (value: string) => formatPlatformLabel(value)
    },
    { title: '店铺名', dataIndex: 'shop_name', minWidth: 126, flex: 0.8, maxWidth: 220, ellipsis: true },
    { title: '创建时间', dataIndex: 'platform_created_at', minWidth: 148, flex: 0.7, maxWidth: 190, render: (v) => formatTime(v) },
    { title: '订单编号', dataIndex: 'order_no', minWidth: 154, flex: 1.2, maxWidth: 240, ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      width: 96,
      responsiveWidth: { mobile: 86, tablet: 92, desktop: 96 },
      render: (value: string) => (value ? <Tag color={ORDER_STATUS_COLOR[value] || 'default'}>{value}</Tag> : '-')
    },
    { title: '平台状态', dataIndex: 'platform_status', minWidth: 118, flex: 0.6, maxWidth: 180, ellipsis: true, render: (value) => value || '-' },
    {
      title: '国家',
      dataIndex: 'country_name_cn',
      width: 92,
      responsiveWidth: { mobile: 78, tablet: 86, desktop: 92 },
      render: (_, row) => row.country_name_cn || row.country_code || '-'
    },
    { title: '客户姓名', dataIndex: 'customer_name', minWidth: 118, flex: 0.8, maxWidth: 200, ellipsis: true },
    { title: 'SKU', dataIndex: 'sku', minWidth: 150, flex: 1.5, maxWidth: 280, ellipsis: true },
    { title: '产品名称', dataIndex: 'platform_product_name', minWidth: 180, flex: 2, maxWidth: 360, ellipsis: true },
    { title: '数量', dataIndex: 'quantity', width: 72, responsiveWidth: { mobile: 64, tablet: 68, desktop: 72 }, align: 'right' },
    { title: '单价', dataIndex: 'unit_price', minWidth: 88, flex: 0.4, maxWidth: 120, align: 'right' },
    { title: '币种', dataIndex: 'currency', width: 68, responsiveWidth: { mobile: 62, tablet: 64, desktop: 68 } },
    { title: '自选物流', dataIndex: 'buyer_selected_logistics', minWidth: 130, flex: 0.8, maxWidth: 220, ellipsis: true },
    { title: '最后发货期限', dataIndex: 'shipping_deadline_at', minWidth: 148, flex: 0.7, maxWidth: 190, render: (v) => formatTime(v) },
    { title: '货运单号', dataIndex: 'shipment_tracking_number', minWidth: 148, flex: 0.9, maxWidth: 240, ellipsis: true },
    { title: '发出截止时间', dataIndex: 'dispatch_deadline_at', minWidth: 148, flex: 0.7, maxWidth: 190, render: (v) => formatTime(v) },
    { title: '产品中文名称', dataIndex: 'product_name', minWidth: 170, flex: 1.6, maxWidth: 320, ellipsis: true },
    {
      title: '客户确认',
      dataIndex: 'customer_confirm',
      width: 96,
      responsiveWidth: { mobile: 86, tablet: 92, desktop: 96 },
      render: (value: string) => (value === '老客户' ? <Tag color="red">{value}</Tag> : value || '-')
    },
    {
      title: '预警',
      dataIndex: 'warning',
      width: 96,
      responsiveWidth: { mobile: 86, tablet: 92, desktop: 96 },
      render: (value: string) => <span className={`warn-${String(value || '').toLowerCase()}`}>{value || '-'}</span>
    },
    { title: '采购单号', dataIndex: 'purchase_no', minWidth: 136, flex: 0.8, maxWidth: 220, render: (v) => (v ? <Tag color="blue">{v}</Tag> : '-') },
    { title: 'Shipping time', dataIndex: 'shipping_time', minWidth: 148, flex: 0.7, maxWidth: 190, render: (v) => formatTime(v) }
  ]

  const detailItemColumns: DataTableColumnsType<OrderDetailItemDto> = [
    { title: '产品编码', dataIndex: 'product_code', width: 130, ellipsis: true, render: (value) => value || '-' },
    { title: '产品中文名称', dataIndex: 'product_name', minWidth: 180, flex: 1, maxWidth: 260, ellipsis: true, render: (value) => value || '-' },
    { title: 'SKU', dataIndex: 'sku', width: 160, ellipsis: true },
    { title: '商品名称', dataIndex: 'platform_product_name', minWidth: 260, flex: 1.4, maxWidth: 420, ellipsis: true },
    { title: '数量', dataIndex: 'quantity', width: 72, align: 'right' },
    { title: '单价', dataIndex: 'unit_price', width: 110, align: 'right', render: (value, row) => `${value || '-'}${row.currency ? ` ${row.currency}` : ''}` }
  ]

  const pagination: TablePaginationConfig = {
    current: page,
    pageSize,
    total,
    showSizeChanger: true,
    showLessItems: true,
    pageSizeOptions: [50, 100, 500],
    showTotal: (value) => `共 ${value} 条`,
    onChange: (nextPage, nextPageSize) => {
      setPage(nextPage)
      setPageSize(nextPageSize)
    }
  }

  return (
    <div className="page-card order-summary-page">
      <div className="orders-header">
        <h2>订单明细表</h2>
      </div>
      <Form
        form={form}
        layout="inline"
        initialValues={{ status: 'all' }}
        className="orders-filter order-summary-filter"
        onFinish={submitFilters}
        onValuesChange={(changedValues, values) => {
          const shouldSubmit = ['status', 'platform', 'shopIds', 'warning', 'paymentRange', 'pickingRange', 'oldCustomerOnly'].some(
            (key) => Object.prototype.hasOwnProperty.call(changedValues, key)
          )
          if (shouldSubmit) submitFilters(values)
        }}
      >
        <Form.Item label="状态" name="status" className="order-summary-filter__status">
          <Select style={{ width: 130 }} options={ORDER_SUMMARY_STATUS_OPTIONS.map((s) => ({ value: s.code, label: s.label }))} />
        </Form.Item>
        <Form.Item label="平台" name="platform" className="order-summary-filter__platform">
          <Select
            allowClear
            placeholder="全部"
            style={{ width: 160 }}
            options={platformOptions}
          />
        </Form.Item>
        <Form.Item label="店铺" name="shopIds" className="order-summary-filter__shop">
          <ShopMultiSelect platform={selectedPlatform} />
        </Form.Item>
        <Form.Item label="预警" name="warning" className="order-summary-filter__warning">
          <Select
            allowClear
            placeholder="全部"
            style={{ width: 130 }}
            options={[
              { value: 'Urgent', label: 'Urgent' }
            ]}
          />
        </Form.Item>
        <Form.Item label="单号" name="number" className="order-summary-filter__number">
          <Input allowClear placeholder="交易号 / 订单编号 / 物流单号" style={{ width: 280 }} onPressEnter={() => form.submit()} />
        </Form.Item>
        <Form.Item label="商品" name="productKeyword" className="order-summary-filter__product">
          <Input allowClear placeholder="商品名称 / 中文名称 / SKU" style={{ width: 280 }} onPressEnter={() => form.submit()} />
        </Form.Item>
        <Form.Item label="付款时间" name="paymentRange" className="order-summary-filter__date">
          <DatePicker.RangePicker style={{ width: 240 }} />
        </Form.Item>
        <Form.Item label="配货日" name="pickingRange" className="order-summary-filter__date">
          <DatePicker.RangePicker style={{ width: 240 }} />
        </Form.Item>
        <Form.Item name="oldCustomerOnly" valuePropName="checked" className="order-summary-filter__check">
          <Checkbox>老客户</Checkbox>
        </Form.Item>
        <Form.Item className="order-summary-filter__actions">
          <Space>
            <Button type="primary" htmlType="submit">
              查询
            </Button>
            <Button onClick={resetFilters}>
              重置
            </Button>
          </Space>
        </Form.Item>
      </Form>
      <div className="toolbar-row">
        <Space size={10}>
          <Button type="primary" icon={<ShoppingCartOutlined />} disabled={!selectedRows.length} onClick={onGeneratePurchase}>
            生成采购单
          </Button>
          <Button icon={<ExportOutlined />} loading={exporting} onClick={onExport}>
            导出Excel
          </Button>
        </Space>
      </div>
      <DataTable
        rowKey="item_id"
        loading={loading}
        dataSource={data}
        columns={columns}
        tableConfig={ORDER_SUMMARY_TABLE_CONFIG}
        onVisibleColumnsChange={setVisibleExportColumns}
        pagination={pagination}
        rowSelection={{ selectedRowKeys, onChange: (keys, rows) => { setSelectedRowKeys(keys); setSelectedRows(rows) }, fixed: true }}
        onRow={(row) => ({
          onDoubleClick: () => openDetail(row)
        })}
      />
      <Modal
        open={detailOpen}
        title="订单详情"
        width={ORDER_DETAIL_MODAL_WIDTH}
        className="order-detail-modal"
        centered
        footer={null}
        destroyOnClose
        styles={{ body: { height: ORDER_DETAIL_MODAL_BODY_HEIGHT, overflow: 'hidden' } }}
        onCancel={() => {
          setDetailOpen(false)
          setDetail(null)
        }}
      >
        <div className="order-detail-content">
          <Spin spinning={detailLoading}>
            {detail ? (
              <Tabs
                className="order-detail-tabs"
                items={[
                  {
                    key: 'info',
                    label: '订单信息',
                    children: (
                      <>
                        <h3 className="section-title">订单信息</h3>
                        <Descriptions column={3} bordered size="small">
                          <Descriptions.Item label="平台/站点">
                            {formatPlatformLabel(detail.platform)}
                            {detail.site ? ' / ' + detail.site : ''}
                          </Descriptions.Item>
                          <Descriptions.Item label="店铺">{detail.shop_name || '-'}</Descriptions.Item>
                          <Descriptions.Item label="状态">{detail.status || '-'}</Descriptions.Item>
                          <Descriptions.Item label="交易号">{detail.transaction_id || '-'}</Descriptions.Item>
                          <Descriptions.Item label="订单编号">{detailOrderNumber(detail)}</Descriptions.Item>
                          <Descriptions.Item label="交运单号">{detail.posting_number || '-'}</Descriptions.Item>
                          <Descriptions.Item label="货运单号">{detail.tracking_number || '-'}</Descriptions.Item>
                          <Descriptions.Item label="平台状态">{detail.platform_status || '-'}</Descriptions.Item>
                          <Descriptions.Item label="订单金额">
                            {detail.order_amount || '-'}{detail.currency ? ` ${detail.currency}` : ''}
                          </Descriptions.Item>
                        </Descriptions>

                        <h3 className="section-title">客户与物流</h3>
                        <Descriptions column={3} bordered size="small">
                          <Descriptions.Item label="客户ID">{detail.customer_id || '-'}</Descriptions.Item>
                          <Descriptions.Item label="客户姓名">{detail.customer_name || '-'}</Descriptions.Item>
                          <Descriptions.Item label="国家">{detail.country_name_cn || detail.country_code || '-'}</Descriptions.Item>
                          <Descriptions.Item label="买家自选物流" span={2}>
                            {detail.buyer_selected_logistics || '-'}
                          </Descriptions.Item>
                          <Descriptions.Item label="内部单号">{detail.internal_order_no || '-'}</Descriptions.Item>
                        </Descriptions>

                        <h3 className="section-title">时间节点</h3>
                        <Descriptions column={3} bordered size="small">
                          <Descriptions.Item label="付款时间">{formatTime(detail.payment_at)}</Descriptions.Item>
                          <Descriptions.Item label="导入时间">{formatTime(detail.created_at)}</Descriptions.Item>
                          <Descriptions.Item label="配货时间">{formatTime(detail.picking_at)}</Descriptions.Item>
                          <Descriptions.Item label="打印标签时间">{formatTime(detail.label_printed_at)}</Descriptions.Item>
                          <Descriptions.Item label="标记发货时间">{formatTime(detail.marked_shipped_at)}</Descriptions.Item>
                          <Descriptions.Item label="交运时间">{formatTime(detail.handover_at)}</Descriptions.Item>
                          <Descriptions.Item label="最后发货期限">{formatTime(detail.shipping_deadline_at)}</Descriptions.Item>
                          <Descriptions.Item label="剩余发货时间">{detail.remaining_shipping_time || '-'}</Descriptions.Item>
                        </Descriptions>

                        <h3 className="section-title">商品明细</h3>
                        <DataTable
                          rowKey="id"
                          size="small"
                          dataSource={detail.items || []}
                          columns={detailItemColumns}
                          pagination={false}
                        />
                      </>
                    )
                  },
                  {
                    key: 'operationLogs',
                    label: '操作日志',
                    children: <OrderOperationLogTable orderId={detail.id} />
                  }
                ]}
              />
            ) : null}
          </Spin>
        </div>
      </Modal>
    </div>
  )
}
