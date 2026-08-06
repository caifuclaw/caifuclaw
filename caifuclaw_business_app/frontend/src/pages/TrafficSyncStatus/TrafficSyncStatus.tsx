import { useCallback, useEffect, useMemo, useState } from 'react'
import dayjs, { type Dayjs } from 'dayjs'
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  ReloadOutlined,
  SyncOutlined
} from '@ant-design/icons'
import { App, Button, DatePicker, Empty, Select, Space, Table, Tag, Tooltip } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  listTrafficAccounts,
  syncTrafficAnalytics,
  type TrafficAccount,
  type TrafficSyncRun
} from '@/api/trafficAnalytics'
import { formatTime } from '@/utils/format'
import '../TrafficAnalytics/TrafficAnalytics.less'

const { RangePicker } = DatePicker
const numberFormatter = new Intl.NumberFormat('zh-CN')
const tableScrollY = 'var(--traffic-table-scroll-y)'
const platformLabels: Record<string, string> = {
  ozon: 'Ozon',
  joom_logistics: 'Joom',
  mercadolibre: 'MercadoLibre',
  allegro: 'Allegro',
  wildberries: 'Wildberries'
}
const platformColors: Record<string, string> = {
  ozon: 'blue',
  joom_logistics: 'gold',
  mercadolibre: 'cyan',
  allegro: 'magenta',
  wildberries: 'purple'
}
const metricLabels: Record<string, string> = {
  impressions: '曝光量',
  clicks: '点击/访问',
  add_to_cart: '加购量',
  orders: '订单数',
  buyers: '买家数',
  units_sold: '售出件数',
  negative_reviews: '负面评价',
  revenue: '成交额'
}

function initialRange(): [Dayjs, Dayjs] {
  return [dayjs().subtract(7, 'day').startOf('day'), dayjs().subtract(1, 'day').startOf('day')]
}

function platformTag(platform: string) {
  return <Tag color={platformColors[platform]}>{platformLabels[platform] || platform}</Tag>
}

function formatInteger(value?: number | null) {
  return value == null ? '--' : numberFormatter.format(value)
}

function runStatus(run?: TrafficSyncRun | null) {
  if (!run) return <Tag>未同步</Tag>
  if (run.status === 'success') return <Tag icon={<CheckCircleOutlined />} color="success">成功</Tag>
  if (run.status === 'partial_success') {
    return <Tag icon={<ExclamationCircleOutlined />} color="warning">部分成功</Tag>
  }
  if (run.status === 'timed_out') return <Tag icon={<ClockCircleOutlined />} color="warning">超时</Tag>
  if (run.status === 'failed') return <Tag icon={<CloseCircleOutlined />} color="error">失败</Tag>
  if (run.status === 'running') return <Tag icon={<SyncOutlined spin />} color="processing">同步中</Tag>
  return <Tag icon={<ClockCircleOutlined />} color="default">等待中</Tag>
}

function dataFreshness(account: TrafficAccount) {
  if (account.data_freshness === 'fresh') {
    return <Tag icon={<CheckCircleOutlined />} color="success">最新</Tag>
  }
  if (account.data_freshness === 'stale') {
    return <Tag icon={<ExclamationCircleOutlined />} color="warning">已过期</Tag>
  }
  return <Tag>无数据</Tag>
}

export function TrafficSyncStatus() {
  const { message } = App.useApp()
  const [range, setRange] = useState<[Dayjs, Dayjs]>(initialRange)
  const [platform, setPlatform] = useState('')
  const [accountId, setAccountId] = useState<number | undefined>()
  const [accounts, setAccounts] = useState<TrafficAccount[]>([])
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)

  const loadAccounts = useCallback(async (background = false) => {
    if (!background) setLoading(true)
    try {
      const response = await listTrafficAccounts({ background, silent: background })
      setAccounts(response.items)
      return response.items
    } finally {
      if (!background) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadAccounts()
  }, [loadAccounts])

  const activeSync = accounts.some((account) => ['pending', 'running'].includes(account.latest_run?.status || ''))
  useEffect(() => {
    if (!activeSync) return
    const timer = window.setInterval(() => {
      void loadAccounts(true).catch(() => undefined)
    }, 3000)
    return () => window.clearInterval(timer)
  }, [activeSync, loadAccounts])

  const platformAccounts = useMemo(
    () => accounts.filter((account) => !platform || account.platform === platform),
    [accounts, platform]
  )
  const visibleAccounts = useMemo(
    () => platformAccounts.filter((account) => !accountId || account.id === accountId),
    [accountId, platformAccounts]
  )

  const startSync = useCallback(
    async (ids?: number[]) => {
      setSyncing(true)
      try {
        const targetIds = ids || visibleAccounts.filter((item) => item.enabled).map((item) => item.id)
        if (!targetIds.length) {
          message.warning('当前筛选条件没有可同步店铺')
          return
        }
        const response = await syncTrafficAnalytics({
          platform_account_ids: targetIds,
          date_from: range[0].format('YYYY-MM-DD'),
          date_to: range[1].format('YYYY-MM-DD')
        })
        setAccounts((current) =>
          current.map((account) => {
            const run = response.items.find((item) => item.platform_account_id === account.id)
            return run ? { ...account, latest_run: run } : account
          })
        )
        message.success(`已提交 ${response.items.length} 个店铺的流量同步`)
      } finally {
        setSyncing(false)
      }
    },
    [message, range, visibleAccounts]
  )

  const columns = useMemo<ColumnsType<TrafficAccount>>(
    () => [
      { title: '平台', dataIndex: 'platform', key: 'platform', width: 132, fixed: 'left', render: platformTag },
      { title: '店铺', dataIndex: 'display_name', key: 'display_name', width: 190, fixed: 'left', ellipsis: true },
      { title: '流量范围', key: 'scope', width: 180, render: (_, row) => row.capability.scope },
      { title: '统计口径', key: 'grain', width: 190, render: (_, row) => row.capability.grain },
      {
        title: '可用指标',
        key: 'metrics',
        width: 330,
        render: (_, row) => (
          <Space size={[4, 4]} wrap>
            {row.capability.metrics.map((metric) => (
              <Tag key={metric}>
                {metricLabels[metric] || metric}
              </Tag>
            ))}
          </Space>
        )
      },
      { title: '同步状态', key: 'status', width: 112, render: (_, row) => runStatus(row.latest_run) },
      { title: '数据状态', key: 'freshness', width: 104, render: (_, row) => dataFreshness(row) },
      {
        title: '最新数据周期',
        key: 'period',
        width: 208,
        render: (_, row) => row.latest_period_start && row.latest_period_end
          ? `${row.latest_period_start} 至 ${row.latest_period_end}`
          : '--'
      },
      {
        title: '写入行数',
        key: 'rows',
        width: 108,
        align: 'right',
        render: (_, row) => formatInteger(row.latest_run?.rows_written)
      },
      {
        title: '最近完成',
        key: 'finished',
        width: 168,
        render: (_, row) => formatTime(row.latest_run?.finished_at || row.latest_metric_at)
      },
      {
        title: '结果',
        key: 'result',
        width: 260,
        ellipsis: true,
        render: (_, row) =>
          row.latest_run?.error_message ? (
            <Tooltip title={row.latest_run.error_message}>
              <span className={['partial_success', 'timed_out'].includes(row.latest_run.status) ? 'traffic-sync-warning' : 'traffic-sync-error'}>
                {row.latest_run.error_message}
              </span>
            </Tooltip>
          ) : (
            row.capability.note
          )
      },
      {
        title: '操作',
        key: 'actions',
        width: 76,
        fixed: 'right',
        align: 'center',
        render: (_, row) => (
          <Tooltip title="同步该店铺">
            <Button
              type="text"
              icon={<SyncOutlined />}
              loading={['pending', 'running'].includes(row.latest_run?.status || '')}
              disabled={!row.enabled}
              onClick={() => void startSync([row.id])}
              aria-label={`同步${row.display_name}`}
            />
          </Tooltip>
        )
      }
    ],
    [startSync]
  )

  return (
    <div className="traffic-analytics-page traffic-sync-status-page">
      <div className="traffic-page-header">
        <div className="traffic-page-title">
          <SyncOutlined />
          <h1>流量同步状态</h1>
          <span>{range[0].format('YYYY-MM-DD')} 至 {range[1].format('YYYY-MM-DD')}</span>
        </div>
        <div className="traffic-page-actions">
          <Tooltip title="刷新状态">
            <Button icon={<ReloadOutlined />} onClick={() => void loadAccounts()} aria-label="刷新流量同步状态" />
          </Tooltip>
          <Button type="primary" icon={<SyncOutlined />} loading={syncing || activeSync} onClick={() => void startSync()}>
            {accountId ? '同步当前店铺' : platform ? '同步当前平台' : '同步全部店铺'}
          </Button>
        </div>
      </div>

      <div className="traffic-filter-bar">
        <RangePicker
          value={range}
          allowClear={false}
          disabledDate={(current) => current && current >= dayjs().startOf('day')}
          onChange={(dates) => {
            if (dates?.[0] && dates?.[1]) setRange([dates[0], dates[1]])
          }}
        />
        <Select
          value={platform || undefined}
          allowClear
          placeholder="全部平台"
          className="traffic-filter-select"
          options={Object.entries(platformLabels).map(([value, label]) => ({ value, label }))}
          onChange={(value) => {
            setPlatform(value || '')
            setAccountId(undefined)
          }}
        />
        <Select
          value={accountId}
          allowClear
          showSearch
          optionFilterProp="label"
          placeholder="全部店铺"
          className="traffic-filter-select traffic-filter-select--shop"
          options={platformAccounts.map((account) => ({ value: account.id, label: account.display_name }))}
          onChange={setAccountId}
        />
      </div>

      <div className="traffic-table-surface traffic-table-surface--standalone">
        <Table<TrafficAccount>
          rowKey="id"
          columns={columns}
          dataSource={visibleAccounts}
          loading={loading}
          locale={{
            emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前筛选条件暂无店铺" />
          }}
          sticky
          scroll={{ x: 2100, y: tableScrollY }}
          pagination={false}
        />
      </div>
    </div>
  )
}
