import { useEffect, useMemo, useState } from 'react'
import { AimOutlined, ExportOutlined } from '@ant-design/icons'
import { App, Button, DatePicker, Form, Input, Select, Space, Tag } from 'antd'
import { DataTable } from '@/components/DataTable'
import type { DataTableConfig, DataTableVisibleColumn } from '@/components/DataTable'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import type { Dayjs } from 'dayjs'
import { useNavigate } from '@/router/navigation'
import http from '@/api/http'
import {
  listOutboundScans,
  type OutboundScanListParams,
  type OutboundScanRecordDto
} from '@/api/outbound'
import { listShops, type ShopDto } from '@/api/shops'
import { useEnabledPlatformOptions } from '@/hooks/useEnabledPlatformOptions'
import { formatPlatformLabel } from '@/stores/dict'
import { downloadBlob } from '@/utils/download'
import { formatTime } from '@/utils/format'

const { RangePicker } = DatePicker
const DEFAULT_RESULT = 'success'
const AUTO_SUBMIT_FILTER_KEYS = new Set(['platform', 'shop_name', 'result', 'scannedRange'])

interface FilterValues {
  platform?: string
  shop_name?: string
  number?: string
  result?: string
  scanned_by?: string
  scannedRange?: [Dayjs, Dayjs]
}

const resultOptions = [
  { value: 'success', label: '成功' },
  { value: 'duplicate', label: '重复' },
  { value: 'not_found', label: '未找到' },
  { value: 'invalid', label: '无效' },
  { value: 'error', label: '异常' }
]

const OUTBOUND_SCANS_TABLE_CONFIG: DataTableConfig = {
  tableKey: 'outbound-scans.list',
  primaryColumnKey: 'tracking_number',
  widthMode: 'adaptive-left',
  columns: [
    { key: 'scanned_at', title: '扫描时间' },
    { key: 'result', title: '结果' },
    { key: 'tracking_number', title: '货运单号', required: true, fixed: false },
    { key: 'platform', title: '平台' },
    { key: 'shop_name', title: '店铺' },
    { key: 'platform_order_no', title: '订单编号' },
    { key: 'order_status', title: '订单状态' },
    { key: 'platform_status', title: '平台状态' },
    { key: 'message', title: '提示' },
    { key: 'scanned_by', title: '扫描人' }
  ]
}

function resultLabel(value?: string) {
  return resultOptions.find((item) => item.value === value)?.label || value || '-'
}

function resultColor(value?: string) {
  if (value === 'success') return 'success'
  if (value === 'duplicate') return 'warning'
  if (value === 'not_found' || value === 'invalid') return 'default'
  return 'error'
}

function isClearedFilterValue(value: unknown) {
  return value === undefined || value === null || value === '' || (Array.isArray(value) && value.length === 0)
}

function shopDisplayName(shop: ShopDto) {
  return shop.display_name || shop.account_id || shop.shop_id || '-'
}

export function OutboundScans() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [form] = Form.useForm<FilterValues>()
  const selectedPlatform = Form.useWatch('platform', form)
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<OutboundScanRecordDto[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [shops, setShops] = useState<ShopDto[]>([])
  const [visibleExportColumns, setVisibleExportColumns] = useState<DataTableVisibleColumn[]>([])
  const [submittedFilters, setSubmittedFilters] = useState<FilterValues>({ result: DEFAULT_RESULT })
  const platformOptions = useEnabledPlatformOptions()

  function submitFilters(values: FilterValues) {
    setSubmittedFilters(values)
    setPage(1)
  }

  function isShopInPlatform(shopName?: string, platform?: string) {
    if (!shopName || !platform) return true
    return shops.some((shop) => shop.platform === platform && shopDisplayName(shop) === shopName)
  }

  function handleFilterValuesChange(changedValues: Partial<FilterValues>, values: FilterValues) {
    const nextValues = { ...values }
    if (Object.prototype.hasOwnProperty.call(changedValues, 'platform') && !isShopInPlatform(values.shop_name, values.platform)) {
      nextValues.shop_name = undefined
      form.setFieldValue('shop_name', undefined)
    }
    const shouldSubmit = Object.entries(changedValues).some(
      ([key, value]) => AUTO_SUBMIT_FILTER_KEYS.has(key) || isClearedFilterValue(value)
    )
    if (shouldSubmit) submitFilters(nextValues)
  }

  function resetFilters() {
    form.resetFields()
    submitFilters({ result: DEFAULT_RESULT })
  }

  const shopOptions = useMemo(
    () => {
      const seenNames = new Set<string>()
      return [...shops]
        .filter((shop) => !selectedPlatform || shop.platform === selectedPlatform)
        .sort((a, b) => {
          const platformCompare = formatPlatformLabel(a.platform).localeCompare(formatPlatformLabel(b.platform))
          if (platformCompare !== 0) return platformCompare
          return shopDisplayName(a).localeCompare(shopDisplayName(b))
        })
        .flatMap((shop) => {
          const name = shopDisplayName(shop)
          if (seenNames.has(name)) return []
          seenNames.add(name)
          return [{
            value: name,
            label: name
          }]
        })
    },
    [shops, selectedPlatform]
  )

  const params = useMemo<OutboundScanListParams>(() => {
    const hasResultField = Object.prototype.hasOwnProperty.call(submittedFilters, 'result')
    const [start, end] = submittedFilters.scannedRange || []
    return {
      platform: submittedFilters.platform || undefined,
      shop_name: submittedFilters.shop_name?.trim() || undefined,
      number: submittedFilters.number?.trim() || undefined,
      result: (hasResultField ? submittedFilters.result : DEFAULT_RESULT) || undefined,
      scanned_by: submittedFilters.scanned_by?.trim() || undefined,
      scanned_start: start?.startOf('day').format('YYYY-MM-DD HH:mm:ss'),
      scanned_end: end?.endOf('day').format('YYYY-MM-DD HH:mm:ss'),
      page,
      page_size: pageSize
    }
  }, [submittedFilters, page, pageSize])

  async function load() {
    setLoading(true)
    try {
      const resp = await listOutboundScans(params)
      setData(resp.items || [])
      setTotal(resp.total || 0)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [params])

  useEffect(() => {
    listShops({ enabled: true, sort_by: 'display_name', sort_order: 'asc' }, { background: true, silent: true })
      .then((items) => setShops(items || []))
      .catch(() => setShops([]))
  }, [])

  async function onExport() {
    const resp = await http.get<Blob>('/api/v1/outbound-scans/export', {
      params: {
        ...params,
        columns: visibleExportColumns.length ? visibleExportColumns.map((column) => column.key).join(',') : undefined
      },
      responseType: 'blob'
    })
    downloadBlob(resp.data, `outbound_scans_${Date.now()}.xlsx`)
    message.success('已导出')
  }

  const columns: ColumnsType<OutboundScanRecordDto> = [
    { title: '扫描时间', dataIndex: 'scanned_at', width: 170, render: (value) => formatTime(value, true) },
    {
      title: '结果',
      dataIndex: 'result',
      width: 90,
      render: (value) => <Tag color={resultColor(value)}>{resultLabel(value)}</Tag>
    },
    { title: '货运单号', dataIndex: 'tracking_number', width: 190, ellipsis: true },
    { title: '平台', dataIndex: 'platform', width: 120, render: (value: string) => formatPlatformLabel(value) },
    { title: '店铺', dataIndex: 'shop_name', width: 180, ellipsis: true },
    { title: '订单编号', dataIndex: 'platform_order_no', width: 170, ellipsis: true },
    { title: '订单状态', dataIndex: 'order_status', width: 110 },
    { title: '平台状态', dataIndex: 'platform_status', width: 150, ellipsis: true },
    { title: '提示', dataIndex: 'message', width: 260, ellipsis: true },
    { title: '扫描人', dataIndex: 'scanned_by', width: 110 }
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
        <h2>扫码记录</h2>
        <Space>
          <Button icon={<AimOutlined />} type="primary" onClick={() => navigate('/scan-outbound')}>
            扫码出库
          </Button>
          <Button icon={<ExportOutlined />} onClick={onExport}>
            导出
          </Button>
        </Space>
      </div>

      <Form
        form={form}
        layout="inline"
        initialValues={{ result: DEFAULT_RESULT }}
        className="orders-filter"
        onFinish={submitFilters}
        onValuesChange={handleFilterValuesChange}
      >
        <Form.Item label="平台" name="platform">
          <Select
            allowClear
            placeholder="全部"
            style={{ width: 150 }}
            options={platformOptions}
          />
        </Form.Item>
        <Form.Item label="店铺" name="shop_name">
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="全部店铺"
            style={{ width: 180 }}
            options={shopOptions}
          />
        </Form.Item>
        <Form.Item label="单号" name="number">
          <Input allowClear placeholder="交易号 / 订单编号 / 货运单号" style={{ width: 310 }} onPressEnter={() => form.submit()} />
        </Form.Item>
        <Form.Item label="结果" name="result">
          <Select allowClear placeholder="全部" style={{ width: 120 }} options={resultOptions} />
        </Form.Item>
        <Form.Item label="扫描时间" name="scannedRange">
          <RangePicker allowClear style={{ width: 250 }} />
        </Form.Item>
        <Form.Item>
          <Space>
            <Button type="primary" htmlType="submit">
              查询
            </Button>
            <Button onClick={resetFilters}>重置</Button>
          </Space>
        </Form.Item>
      </Form>

      <DataTable
        rowKey="id"
        loading={loading}
        dataSource={data}
        columns={columns}
        tableConfig={OUTBOUND_SCANS_TABLE_CONFIG}
        onVisibleColumnsChange={setVisibleExportColumns}
        pagination={pagination}
      />
    </div>
  )
}
