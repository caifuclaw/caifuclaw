import { useEffect, useMemo, useState } from 'react'
import { Button, DatePicker, Descriptions, Form, Input, Modal, Select, Space, Tag } from 'antd'
import { DataTable } from '@/components/DataTable'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import type { Dayjs } from 'dayjs'
import dayjs from 'dayjs'
import {
  getSyncApiLog,
  listSyncApiLogs,
  listSyncApiLogSummaries,
  type SyncApiLogDto,
  type SyncApiLogQueryParams,
  type SyncApiLogSummaryDto
} from '@/api/logs'
import { listPlatforms, type PlatformOptionDto } from '@/api/shops'
import { formatTime } from '@/utils/format'

const { RangePicker } = DatePicker

type ViewMode = 'summary' | 'detail'

interface SummaryRow extends SyncApiLogSummaryDto {
  row_key: string
}

interface FilterValues {
  viewMode?: ViewMode
  platform?: string
  account_id?: string
  operation?: string
  status?: string
  keyword?: string
  dateRange?: [Dayjs, Dayjs]
}

const operations = [
  { value: 'orders_sync', label: '订单同步' },
  { value: 'logistics_sync', label: '物流同步' },
  { value: 'label_print', label: '面单打印' },
  { value: 'token_refresh', label: '令牌刷新' },
  { value: 'manual_request', label: '手动请求' },
  { value: 'text_translation', label: '文字翻译' }
]

const statusOptions = [
  { value: 'success', label: '成功' },
  { value: 'failed', label: '失败' }
]

function operationLabel(value?: string | null) {
  return operations.find((item) => item.value === value)?.label || value || '-'
}

function pretty(value: unknown) {
  if (value == null || value === '') return '-'
  if (typeof value === 'string') {
    try {
      return JSON.stringify(JSON.parse(value), null, 2)
    } catch {
      return value
    }
  }
  return JSON.stringify(value, null, 2)
}

function defaultDateRange(): [Dayjs, Dayjs] {
  const end = dayjs()
  return [end.subtract(7, 'day'), end]
}

export function SyncApiLogs() {
  const [form] = Form.useForm<FilterValues>()
  const [loading, setLoading] = useState(false)
  const [rows, setRows] = useState<SyncApiLogDto[]>([])
  const [summaryRows, setSummaryRows] = useState<SummaryRow[]>([])
  const [platforms, setPlatforms] = useState<PlatformOptionDto[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detail, setDetail] = useState<SyncApiLogDto | null>(null)
  const [submittedFilters, setSubmittedFilters] = useState<FilterValues>(() => ({
    viewMode: 'summary',
    dateRange: defaultDateRange()
  }))
  const watchedViewMode = Form.useWatch('viewMode', form)
  const viewMode = watchedViewMode || submittedFilters.viewMode || 'summary'
  const submittedViewMode = submittedFilters.viewMode || 'summary'
  const platformOptions = useMemo<PlatformOptionDto[]>(() => {
    const seen = new Set<string>()
    return [{ platform: 'baidu_translate', display_name: '百度翻译', enabled: true }, ...platforms].filter((item) => {
      const key = String(item.platform || '').trim()
      if (!key || seen.has(key)) return false
      seen.add(key)
      return true
    })
  }, [platforms])

  const params = useMemo<SyncApiLogQueryParams>(() => {
    const [start, end] = submittedFilters.dateRange || []
    return {
      platform: submittedFilters.platform || undefined,
      account_id: submittedFilters.account_id?.trim() || undefined,
      operation: submittedFilters.operation || undefined,
      status: submittedFilters.status || undefined,
      keyword: submittedFilters.keyword?.trim() || undefined,
      date_from: start?.startOf('day').format('YYYY-MM-DD HH:mm:ss'),
      date_to: end?.endOf('day').format('YYYY-MM-DD HH:mm:ss')
    }
  }, [submittedFilters])

  async function loadPlatforms() {
    try {
      setPlatforms(((await listPlatforms()) || []).filter((item) => item.enabled !== false))
    } catch {
      setPlatforms([])
    }
  }

  async function load() {
    setLoading(true)
    try {
      if (submittedViewMode === 'summary') {
        const data = await listSyncApiLogSummaries({ ...params, page, page_size: pageSize })
        setSummaryRows(
          (data.items || []).map((item, index) => ({
            ...item,
            row_key: `${item.platform || '-'}-${item.account_id || '-'}-${item.operation || '-'}-${item.url || '-'}-${item.log_date || '-'}-${index}`
          }))
        )
        setTotal(data.total || 0)
      } else {
        const data = await listSyncApiLogs({ ...params, page, page_size: pageSize })
        setRows(data.items || [])
        setTotal(data.total || 0)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    form.setFieldsValue(submittedFilters)
    loadPlatforms()
  }, [])

  useEffect(() => {
    load()
  }, [params, submittedViewMode, page, pageSize])

  async function openDetail(row: SyncApiLogDto) {
    const data = await getSyncApiLog(row.id)
    setDetail(data)
    setDetailOpen(true)
  }

  const summaryColumns: ColumnsType<SummaryRow> = [
    { title: '日期', dataIndex: 'log_date', width: 110 },
    { title: '最近调用', dataIndex: 'last_created_at', width: 170, render: (value) => formatTime(value, true) },
    { title: '平台', dataIndex: 'platform', width: 120 },
    { title: '账号', dataIndex: 'account_id', width: 160, ellipsis: true },
    { title: '操作', dataIndex: 'operation', width: 140, render: operationLabel },
    { title: '接口', dataIndex: 'url', width: 360, ellipsis: true },
    { title: '总次数', dataIndex: 'total', width: 90 },
    { title: '成功', dataIndex: 'success_count', width: 90 },
    { title: '失败', dataIndex: 'failed_count', width: 90 },
    { title: '平均耗时(ms)', dataIndex: 'avg_duration_ms', width: 120, render: (value) => value ?? '-' },
    { title: '最大耗时(ms)', dataIndex: 'max_duration_ms', width: 120, render: (value) => value ?? '-' }
  ]

  const detailColumns: ColumnsType<SyncApiLogDto> = [
    { title: '时间', dataIndex: 'created_at', width: 170, render: (value) => formatTime(value, true) },
    { title: '平台', dataIndex: 'platform', width: 120 },
    { title: '账号', dataIndex: 'account_id', width: 150, ellipsis: true },
    { title: '操作', dataIndex: 'operation', width: 130, render: operationLabel },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (value) => <Tag color={value === 'success' ? 'success' : 'error'}>{value || '-'}</Tag>
    },
    { title: 'HTTP', dataIndex: 'response_status', width: 80 },
    { title: '耗时(ms)', dataIndex: 'duration_ms', width: 100, render: (value) => value ?? '-' },
    { title: '方法', dataIndex: 'method', width: 90 },
    { title: '接口', dataIndex: 'url', width: 360, ellipsis: true },
    {
      title: '操作',
      key: 'actions',
      width: 90,
      fixed: 'right',
      render: (_, row) => (
        <Button size="small" onClick={() => openDetail(row)}>
          详情
        </Button>
      )
    }
  ]

  const pagination: TablePaginationConfig = {
    current: page,
    pageSize,
    total,
    pageSizeOptions: [50, 100, 200],
    showSizeChanger: true,
    showLessItems: true,
    showTotal: (value) => `共 ${value} 条`,
    onChange: (nextPage, nextPageSize) => {
      setPage(nextPage)
      setPageSize(nextPageSize)
    }
  }

  return (
    <div className="page-card">
      <div className="orders-header">
        <h2>平台接口日志</h2>
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
        <Form.Item label="视图" name="viewMode">
          <Select
            style={{ width: 120 }}
            onChange={() => setPage(1)}
            options={[
              { value: 'summary', label: '汇总' },
              { value: 'detail', label: '明细' }
            ]}
          />
        </Form.Item>
        <Form.Item label="平台" name="platform">
          <Select
            allowClear
            placeholder="全部"
            style={{ width: 150 }}
            options={platformOptions.map((item) => ({ value: item.platform, label: item.display_name }))}
          />
        </Form.Item>
        <Form.Item label="账号" name="account_id">
          <Input allowClear placeholder="账号" style={{ width: 150 }} />
        </Form.Item>
        <Form.Item label="操作" name="operation">
          <Select allowClear placeholder="全部" style={{ width: 140 }} options={operations} />
        </Form.Item>
        {viewMode === 'detail' ? (
          <Form.Item label="状态" name="status">
            <Select allowClear placeholder="全部" style={{ width: 110 }} options={statusOptions} />
          </Form.Item>
        ) : null}
        <Form.Item label="关键字" name="keyword">
          <Input allowClear placeholder="URL / 错误 / 内容" style={{ width: 210 }} />
        </Form.Item>
        <Form.Item label="日期" name="dateRange">
          <RangePicker style={{ width: 250 }} />
        </Form.Item>
        <Form.Item>
          <Space>
            <Button type="primary" htmlType="submit">
              查询
            </Button>
            <Button
              onClick={() => {
                const nextFilters = { viewMode: 'summary' as ViewMode, dateRange: defaultDateRange() }
                form.setFieldsValue(nextFilters)
                form.resetFields(['platform', 'account_id', 'operation', 'status', 'keyword'])
                setSubmittedFilters(nextFilters)
                setPage(1)
              }}
            >
              重置
            </Button>
          </Space>
        </Form.Item>
      </Form>

      {submittedViewMode === 'summary' ? (
        <DataTable<SummaryRow>
          rowKey="row_key"
          loading={loading}
          dataSource={summaryRows}
          columns={summaryColumns}
          pagination={pagination}
        />
      ) : (
        <DataTable<SyncApiLogDto>
          rowKey="id"
          loading={loading}
          dataSource={rows}
          columns={detailColumns}
          pagination={pagination}
        />
      )}

      <Modal
        open={detailOpen}
        width="min(900px, 96vw)"
        title="平台接口日志详情"
        centered
        footer={null}
        destroyOnClose
        styles={{ body: { maxHeight: '72vh', overflowY: 'auto' } }}
        onCancel={() => setDetailOpen(false)}
      >
        {detail ? (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="时间">{formatTime(detail.created_at, true)}</Descriptions.Item>
              <Descriptions.Item label="平台">{detail.platform || '-'}</Descriptions.Item>
              <Descriptions.Item label="账号">{detail.account_id || '-'}</Descriptions.Item>
              <Descriptions.Item label="操作">{operationLabel(detail.operation)}</Descriptions.Item>
              <Descriptions.Item label="状态">{detail.status || '-'}</Descriptions.Item>
              <Descriptions.Item label="HTTP">{detail.response_status || '-'}</Descriptions.Item>
              <Descriptions.Item label="耗时">{detail.duration_ms ?? '-'} ms</Descriptions.Item>
              <Descriptions.Item label="方法">{detail.method || '-'}</Descriptions.Item>
              <Descriptions.Item label="URL" span={2}>
                {detail.url || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="错误" span={2}>
                {detail.error_message || '-'}
              </Descriptions.Item>
            </Descriptions>
            <div>
              <h3>请求内容</h3>
              <pre className="json-preview">{pretty(detail.request_body)}</pre>
            </div>
            <div>
              <h3>响应内容</h3>
              <pre className="json-preview">{pretty(detail.response_body)}</pre>
            </div>
            <div>
              <h3>扩展信息</h3>
              <pre className="json-preview">{pretty(detail.extra)}</pre>
            </div>
          </Space>
        ) : null}
      </Modal>
    </div>
  )
}
