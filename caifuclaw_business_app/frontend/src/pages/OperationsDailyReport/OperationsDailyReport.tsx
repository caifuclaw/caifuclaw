import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption, SeriesOption } from 'echarts'
import dayjs from 'dayjs'
import { CalendarOutlined, ClockCircleOutlined, ReloadOutlined, WarningOutlined } from '@ant-design/icons'
import { Alert, Button, Card, DatePicker, Empty, Skeleton, Tag } from 'antd'
import { DataTable, type DataTableColumnsType } from '@/components/DataTable'
import {
  fetchOperationsDailyReport,
  type OperationsCustomerComplaint,
  type OperationsDailyReport,
  type OperationsDailyShop,
  type OperationsFulfillmentRisk
} from '@/api/dashboard'
import { sortShopTrendsByRevenue } from './shopTrendSort'
import './OperationsDailyReport.less'

const numberFormatter = new Intl.NumberFormat('zh-CN')
const moneyFormatter = new Intl.NumberFormat('zh-CN', {
  style: 'currency',
  currency: 'CNY',
  maximumFractionDigits: 0
})
const platformLabels: Record<string, string> = {
  ozon: 'Ozon',
  joom_logistics: 'Joom',
  mercadolibre: 'MercadoLibre',
  allegro: 'Allegro',
  wildberries: 'Wildberries'
}

function platformLabel(platform: string) {
  return platformLabels[platform] || platform || '未识别平台'
}

function PlatformTag({ platform }: { platform: string }) {
  return <Tag className="operations-daily-report__platform-tag">{platformLabel(platform)}</Tag>
}

function formatGeneratedAt(value?: string) {
  if (!value) return '--'
  const formatted = dayjs(value)
  return formatted.isValid() ? formatted.format('YYYY-MM-DD HH:mm:ss') : value
}

function formatIssueDate(value?: string | null) {
  if (!value) return '--'
  const formatted = dayjs(value)
  return formatted.isValid() ? formatted.format('YYYY-MM-DD') : value
}

function formatMoney(value: number) {
  return moneyFormatter.format(value || 0)
}

function formatCompactMoney(value: number) {
  const amount = value || 0
  if (Math.abs(amount) >= 10000) return `¥${(amount / 10000).toFixed(1)}万`
  return formatMoney(amount)
}

function formatRevenueAxisValue(value: number, maxRevenue: number) {
  const amount = value || 0
  if (amount === 0) return '¥0'
  if (maxRevenue < 10) return `¥${amount.toFixed(1).replace(/\.0$/, '')}`
  if (maxRevenue < 1000) return `¥${Math.round(amount)}`
  return formatCompactMoney(amount)
}

function revenueAxisInterval(maxRevenue: number) {
  if (maxRevenue <= 0) return 0
  if (maxRevenue < 10) return 1
  if (maxRevenue < 100) return 10
  if (maxRevenue < 1000) return 100
  if (maxRevenue < 10000) return 1000
  return 10000
}

function orderChartOption(shop: OperationsDailyShop): EChartsOption {
  const maxRevenue = shop.days.reduce((max, item) => Math.max(max, item.revenue_cny || 0), 0)
  const hasRevenue = maxRevenue > 0
  const revenueInterval = revenueAxisInterval(maxRevenue)
  const series: SeriesOption[] = [
    {
      name: '订单数',
      type: 'bar',
      barMaxWidth: 24,
      data: shop.days.map((item) => item.orders),
      itemStyle: { color: '#2563eb', borderRadius: [3, 3, 0, 0] },
      emphasis: { itemStyle: { color: '#1d4ed8' } }
    }
  ]

  if (hasRevenue) {
    series.push({
      name: '营业额',
      type: 'line',
      yAxisIndex: 1,
      data: shop.days.map((item) => item.revenue_cny),
      symbol: 'circle',
      symbolSize: 6,
      lineStyle: { width: 2 },
      itemStyle: { color: '#0f766e' }
    })
  }

  return {
    animation: false,
    color: ['#2563eb', '#0f766e'],
    grid: { top: hasRevenue ? 44 : 28, right: hasRevenue ? 52 : 16, bottom: 30, left: 42, containLabel: false },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: unknown) => {
        const values = Array.isArray(params) ? params : [params]
        const current = values[0] as { dataIndex?: number } | undefined
        const point = shop.days[current?.dataIndex || 0]
        if (!point) return ''
        return `${dayjs(point.date).format('MM-DD')}<br/>订单数：${numberFormatter.format(point.orders)} 单<br/>人民币营业额：${formatMoney(point.revenue_cny)}`
      }
    },
    legend: hasRevenue ? {
      top: 2,
      left: 0,
      itemWidth: 10,
      itemHeight: 10,
      itemGap: 14,
      textStyle: { color: '#64748b', fontSize: 11 }
    } : undefined,
    xAxis: {
      type: 'category',
      data: shop.days.map((item) => dayjs(item.date).format('MM-DD')),
      axisLine: { lineStyle: { color: '#cbd5e1' } },
      axisTick: { show: false },
      axisLabel: { color: '#64748b', fontSize: 11, interval: 0, hideOverlap: true }
    },
    yAxis: [
      {
        type: 'value',
        minInterval: 1,
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: '#e8eef6', type: 'dashed' } },
        axisLabel: { color: '#64748b', fontSize: 11, formatter: '{value}', hideOverlap: true }
      },
      hasRevenue
        ? {
            type: 'value',
            axisLine: { show: false },
            axisTick: { show: false },
            splitLine: { show: false },
            minInterval: revenueInterval,
            interval: revenueInterval,
            axisLabel: {
              color: '#64748b',
              fontSize: 10,
              margin: 8,
              hideOverlap: true,
              formatter: (value: number) => formatRevenueAxisValue(value, maxRevenue)
            }
          }
        : {
            type: 'value',
            axisLine: { show: false },
            axisTick: { show: false },
            splitLine: { show: false },
            axisLabel: { show: false }
          }
    ],
    series
  }
}

function TrendSkeleton() {
  return (
    <div className="operations-daily-report__shop-grid" aria-label="订单趋势加载中">
      {[0, 1, 2, 3].map((index) => (
        <Card key={index} className="operations-daily-report__shop-card" bordered>
          <Skeleton active title={{ width: '45%' }} paragraph={{ rows: 4 }} />
        </Card>
      ))}
    </div>
  )
}

export function OperationsDailyReport() {
  const [selectedDate, setSelectedDate] = useState(() => dayjs().subtract(1, 'day').startOf('day'))
  const [report, setReport] = useState<OperationsDailyReport>()
  const [initialLoading, setInitialLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const reportRef = useRef<OperationsDailyReport>()
  const requestIdRef = useRef(0)
  const abortRef = useRef<AbortController>()
  const selectedDateValue = selectedDate.format('YYYY-MM-DD')

  const refresh = useCallback(async () => {
    const requestId = requestIdRef.current + 1
    requestIdRef.current = requestId
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setRefreshing(true)
    if (!reportRef.current) setInitialLoading(true)
    setError('')
    try {
      const nextReport = await fetchOperationsDailyReport(
        { report_date: selectedDateValue },
        { signal: controller.signal }
      )
      if (requestId !== requestIdRef.current) return
      reportRef.current = nextReport
      setReport(nextReport)
    } catch (requestError) {
      if ((requestError as { code?: string })?.code === 'ERR_CANCELED' || requestId !== requestIdRef.current) return
      setError('运营日报表加载失败，请重新刷新。')
    } finally {
      if (requestId === requestIdRef.current) {
        setInitialLoading(false)
        setRefreshing(false)
      }
    }
  }, [selectedDateValue])

  useEffect(() => {
    void refresh()
    return () => abortRef.current?.abort()
  }, [refresh])

  const handleDateChange = useCallback((value: dayjs.Dayjs | null) => {
    if (!value) return
    reportRef.current = undefined
    setReport(undefined)
    setInitialLoading(true)
    setSelectedDate(value.startOf('day'))
  }, [])

  const riskColumns = useMemo<DataTableColumnsType<OperationsFulfillmentRisk>>(
    () => [
      {
        title: '平台',
        dataIndex: 'platform',
        key: 'platform',
        flex: 1.2,
        render: (platform: string) => <PlatformTag platform={platform} />
      },
      {
        title: '超时订单',
        dataIndex: 'overdue_orders',
        key: 'overdue_orders',
        align: 'right',
        flex: 1,
        render: (count: number) => <span className="operations-daily-report__risk-number operations-daily-report__risk-number--overdue">{numberFormatter.format(count)}</span>
      },
      {
        title: '即将超时订单',
        dataIndex: 'due_soon_orders',
        key: 'due_soon_orders',
        align: 'right',
        flex: 1.1,
        render: (count: number) => <span className="operations-daily-report__risk-number operations-daily-report__risk-number--due-soon">{numberFormatter.format(count)}</span>
      }
    ],
    []
  )

  const complaintColumns = useMemo<DataTableColumnsType<OperationsCustomerComplaint>>(
    () => [
      {
        title: '平台',
        dataIndex: 'platform',
        key: 'platform',
        flex: 1,
        render: (platform: string) => platformLabel(platform)
      },
      { title: '店铺', dataIndex: 'shop', key: 'shop', flex: 1.4 },
      { title: '当日负面评价数', dataIndex: 'count', key: 'count', align: 'right', flex: 1 },
      {
        title: '统计日期',
        dataIndex: 'latest_issue_at',
        key: 'latest_issue_at',
        flex: 1,
        render: (value?: string | null) => formatIssueDate(value)
      }
    ],
    []
  )

  const rangeLabel = report ? `${report.date_from} 至 ${report.date_to}` : '最近 7 个自然日'
  const reportDateLabel = report?.date_to || selectedDateValue
  const fulfillmentRiskRows = useMemo(
    () => (report?.fulfillment_risk || []).filter((item) => item.overdue_orders > 0 || item.due_soon_orders > 0),
    [report?.fulfillment_risk]
  )
  const riskSummary = useMemo(
    () => fulfillmentRiskRows.reduce(
      (summary, item) => ({
        overdue: summary.overdue + item.overdue_orders,
        dueSoon: summary.dueSoon + item.due_soon_orders
      }),
      { overdue: 0, dueSoon: 0 }
    ),
    [fulfillmentRiskRows]
  )
  const shopSummary = useMemo(
    () => (report?.shop_daily_orders || []).reduce(
      (summary, shop) => ({
        totalOrders: summary.totalOrders + shop.total_orders,
        totalRevenue: summary.totalRevenue + shop.total_revenue_cny,
        shopCount: summary.shopCount + 1
      }),
      { totalOrders: 0, totalRevenue: 0, shopCount: 0 }
    ),
    [report?.shop_daily_orders]
  )
  const sortedShopDailyOrders = useMemo(
    () => sortShopTrendsByRevenue(report?.shop_daily_orders || []),
    [report?.shop_daily_orders]
  )
  const complaintRows = report?.customer_complaints || []
  const complaintSummary = useMemo(
    () => complaintRows.reduce(
      (summary, item) => ({
        total: summary.total + item.count,
        shopCount: summary.shopCount + 1
      }),
      { total: 0, shopCount: 0 }
    ),
    [complaintRows]
  )
  const complaintSourceReady = report?.customer_complaints_data_status === 'negative_reviews'

  return (
    <main className="operations-daily-report" aria-labelledby="operations-daily-report-title">
      <header className="operations-daily-report__header">
        <div>
          <h1 id="operations-daily-report-title">运营日报表</h1>
          <p>覆盖已启用店铺订单与各平台待处理履约风险，订单按付款时间计算。</p>
        </div>
        <div className="operations-daily-report__actions">
          <div className="operations-daily-report__date-filter">
            <label htmlFor="operations-daily-report-date">统计日期</label>
            <DatePicker
              id="operations-daily-report-date"
              value={selectedDate}
              allowClear={false}
              format="YYYY-MM-DD"
              disabledDate={(current) => Boolean(current && current.isAfter(dayjs().subtract(1, 'day'), 'day'))}
              onChange={handleDateChange}
            />
          </div>
          <div className="operations-daily-report__meta-item">
            <CalendarOutlined aria-hidden="true" />
            <span>
              <small>统计范围</small>
              <strong>{rangeLabel}</strong>
            </span>
          </div>
          <div className="operations-daily-report__meta-item">
            <ClockCircleOutlined aria-hidden="true" />
            <span>
              <small>数据更新时间</small>
              <strong>{formatGeneratedAt(report?.generated_at)}</strong>
            </span>
          </div>
          <Button icon={<ReloadOutlined />} onClick={() => void refresh()} loading={refreshing}>
            刷新
          </Button>
        </div>
      </header>

      <div className="operations-daily-report__body">
        {error ? (
          <Alert
            className="operations-daily-report__alert"
            type="error"
            showIcon
            message={error}
            action={<Button size="small" onClick={() => void refresh()}>重试</Button>}
          />
        ) : null}

        <section className="operations-daily-report__section operations-daily-report__section--risk" aria-labelledby="fulfillment-risk-title">
          <div className="operations-daily-report__section-heading">
            <div>
              <h2 id="fulfillment-risk-title">平台履约风险</h2>
              <p>只统计待处理和配货中的订单，超时与 24 小时内到期分别显示。</p>
            </div>
            <span className="operations-daily-report__section-status">按平台汇总</span>
          </div>

          <div className="operations-daily-report__risk-strip" aria-label="履约风险汇总">
            <div className="operations-daily-report__risk-metric operations-daily-report__risk-metric--overdue">
              <span className="operations-daily-report__risk-icon"><WarningOutlined aria-hidden="true" /></span>
              <div>
                <span>已超时订单</span>
                <strong>{initialLoading ? '--' : numberFormatter.format(riskSummary.overdue)}</strong>
              </div>
            </div>
            <div className="operations-daily-report__risk-metric operations-daily-report__risk-metric--due-soon">
              <span className="operations-daily-report__risk-icon"><ClockCircleOutlined aria-hidden="true" /></span>
              <div>
                <span>即将超时订单</span>
                <strong>{initialLoading ? '--' : numberFormatter.format(riskSummary.dueSoon)}</strong>
              </div>
            </div>
            <p className="operations-daily-report__risk-note">
              <strong>处理优先级</strong>
              已超时订单需优先处理，即将超时订单请在时限前完成操作。
            </p>
          </div>

          <Card className="operations-daily-report__table-card" bordered>
            <DataTable<OperationsFulfillmentRisk>
              rowKey="platform"
              columns={riskColumns}
              dataSource={fulfillmentRiskRows}
              loading={initialLoading}
              pagination={false}
              fitContentColumns={false}
              locale={{ emptyText: <Empty description={error ? '暂无法加载平台履约风险数据' : '暂无平台履约风险数据'} /> }}
            />
          </Card>
        </section>

        <section className="operations-daily-report__section" aria-labelledby="shop-order-trend-title">
          <div className="operations-daily-report__section-heading">
            <div>
              <h2 id="shop-order-trend-title">近七日店铺经营趋势</h2>
              <p>{rangeLabel}，订单按付款时间统计，营业额按付款日汇率折合人民币。</p>
            </div>
            <span className="operations-daily-report__trend-total">
              <strong>{initialLoading ? '--' : formatCompactMoney(shopSummary.totalRevenue)}</strong>
              <span>人民币营业额 / {initialLoading ? '--' : numberFormatter.format(shopSummary.totalOrders)} 单 / {initialLoading ? '--' : shopSummary.shopCount} 家店铺</span>
            </span>
          </div>

          {initialLoading ? <TrendSkeleton /> : sortedShopDailyOrders.length ? (
            <div className="operations-daily-report__shop-grid">
              {sortedShopDailyOrders.map((shop) => {
                const noOrders = shop.total_orders === 0
                const description = `${platformLabel(shop.platform)} ${shop.shop}，${rangeLabel} 共 ${numberFormatter.format(shop.total_orders)} 单，人民币营业额 ${formatMoney(shop.total_revenue_cny)}`
                return (
                  <Card key={`${shop.platform}-${shop.account_id}`} className="operations-daily-report__shop-card" bordered>
                    <div className="operations-daily-report__shop-card-head">
                      <div>
                        <PlatformTag platform={shop.platform} />
                        <h3 title={shop.shop}>{shop.shop}</h3>
                      </div>
                      <div className="operations-daily-report__shop-total">
                        <span>{noOrders ? '近 7 日无营业额' : '近 7 日营业额'}</span>
                        <strong>{formatCompactMoney(shop.total_revenue_cny)}</strong>
                        <small>{numberFormatter.format(shop.total_orders)} 单</small>
                      </div>
                    </div>
                    <div className="operations-daily-report__chart" role="img" aria-label={description}>
                      <span className="operations-daily-report__sr-only">{description}</span>
                      <ReactECharts option={orderChartOption(shop)} notMerge lazyUpdate style={{ height: 204 }} />
                    </div>
                  </Card>
                )
              })}
            </div>
          ) : (
            <Card className="operations-daily-report__empty-card" bordered>
              <Empty description={error ? '暂无法加载店铺订单趋势' : `当前统计范围内没有已启用店铺（${rangeLabel}）`} />
            </Card>
          )}
        </section>

        <section className="operations-daily-report__section" aria-labelledby="customer-complaints-title">
          <div className="operations-daily-report__section-heading">
            <div>
              <h2 id="customer-complaints-title">店铺客诉与售后</h2>
              <p>按店铺汇总所选日期的负面评价，仅统计已按日落库的数据。</p>
            </div>
          </div>
          <Alert
            className="operations-daily-report__alert"
            type="info"
            showIcon
            message={complaintSourceReady ? `${reportDateLabel} 负面评价已接入` : '客诉/售后数据源待接入'}
            description={complaintSourceReady
              ? complaintRows.length
                ? `${reportDateLabel} 共有 ${complaintSummary.shopCount} 家店铺出现负面评价，合计 ${numberFormatter.format(complaintSummary.total)} 条。`
                : `${reportDateLabel} 没有负面评价记录。`
              : '当前系统尚未配置可核验的数据源，接入后将在此按店铺展示真实统计。'}
          />
          <Card className="operations-daily-report__table-card" bordered>
            <DataTable<OperationsCustomerComplaint>
              rowKey={(row) => `${row.platform}-${row.shop}`}
              columns={complaintColumns}
              dataSource={complaintRows}
              loading={initialLoading}
              pagination={false}
              fitContentColumns={false}
              locale={{ emptyText: <Empty description={complaintSourceReady ? '所选日期没有负面评价' : '客诉/售后数据源待接入'} /> }}
            />
          </Card>
        </section>
      </div>
    </main>
  )
}
