/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from '@/router/navigation'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import dayjs from 'dayjs'
import {
  AlertOutlined,
  ArrowDownOutlined,
  ArrowRightOutlined,
  ArrowUpOutlined,
  BarChartOutlined,
  CalendarOutlined,
  LineChartOutlined,
  PayCircleOutlined,
  ReloadOutlined,
  ShopOutlined,
  SettingOutlined,
  ShoppingCartOutlined,
  SwapOutlined
} from '@ant-design/icons'
import { Alert, App, Button, Card, Checkbox, Col, DatePicker, Empty, Form, InputNumber, Modal, Row, Segmented, Select, Skeleton, Space, Table, Tag, Tooltip } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  fetchDashboardOverview,
  fetchDashboardRisk,
  fetchDashboardSales,
  fetchDashboardSettings,
  fetchDashboardSkus,
  updateDashboardSettings,
  type DashboardOverview,
  type DashboardPlatformSetting,
  type DashboardRisk,
  type DashboardSales,
  type DashboardSkus
} from '@/api/dashboard'
import { listShops, type ShopDto } from '@/api/shops'
import { formatTime } from '@/utils/format'
import {
  currentDashboardRange,
  dashboardComparisonRange,
  initialDashboardComparison,
  initialDashboardShopIds,
  initialDashboardSelection,
  type DashboardCompareMode,
  type DashboardPeriod,
  type DashboardRange
} from '@/utils/dashboardPeriod'
import {
  dashboardTrendPoints,
  initialDashboardGroupBy,
  type DashboardGroupBy,
  type DashboardTrendMetric,
  type DashboardTrendPoint
} from '@/utils/dashboardTrend'
import './Dashboard.less'

const moneyFormatter = new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY', maximumFractionDigits: 0 })
const numberFormatter = new Intl.NumberFormat('zh-CN')
const { RangePicker } = DatePicker
const DASHBOARD_PERIOD_OPTIONS: Array<{ label: string; value: Exclude<DashboardPeriod, 'custom'> }> = [
  { label: '7天', value: '7d' },
  { label: '28天', value: '28d' },
  { label: '季度', value: 'quarter' },
  { label: '年度', value: 'year' }
]
const DASHBOARD_PERIOD_LABELS: Record<DashboardPeriod, string> = {
  '7d': '近7天',
  '28d': '近28天',
  quarter: '近3个月',
  year: '近12个月',
  custom: '自定义'
}
const DASHBOARD_COMPARE_LABELS: Record<DashboardCompareMode, string> = {
  previous: '上一周期',
  last_year: '去年同期',
  custom: '自定义周期',
  none: '不对比'
}
const DASHBOARD_COMPARE_OPTIONS: Array<{ label: string; value: DashboardCompareMode }> = [
  { label: '上一周期', value: 'previous' },
  { label: '去年同期', value: 'last_year' },
  { label: '自定义周期', value: 'custom' },
  { label: '不对比', value: 'none' }
]
const DASHBOARD_GROUP_OPTIONS: Array<{ label: string; value: DashboardGroupBy }> = [
  { label: '按日', value: 'day' },
  { label: '按周', value: 'week' },
  { label: '按月', value: 'month' }
]

function defaultFulfillmentDays(platform: string) {
  if (platform === 'ozon') return 5
  if (['wildberries', 'mercadolibre', 'dmsmatrix'].includes(platform)) return 2
  return 3
}

function resetPlatformSetting(row: DashboardPlatformSetting): DashboardPlatformSetting {
  return {
    ...row,
    receipt_rate_pct: row.platform === 'ozon' ? 69 : row.platform === 'wildberries' ? 75 : 100,
    fulfillment_days: defaultFulfillmentDays(row.platform)
  }
}

function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.matchMedia(query).matches
  })

  useEffect(() => {
    if (typeof window === 'undefined') return
    const media = window.matchMedia(query)
    const updateMatches = () => setMatches(media.matches)
    updateMatches()
    media.addEventListener('change', updateMatches)
    return () => media.removeEventListener('change', updateMatches)
  }, [query])

  return matches
}

function formatNumber(value?: number | null) {
  return numberFormatter.format(value || 0)
}

function formatMoney(value?: number | null) {
  return moneyFormatter.format(value || 0)
}

function formatCompactMoney(value?: number | null) {
  const safe = value || 0
  if (Math.abs(safe) >= 10000) {
    return `${numberFormatter.format(Math.round(safe / 10000))}万`
  }
  if (Math.abs(safe) >= 1000) {
    return `${numberFormatter.format(Math.round(safe / 1000))}k`
  }
  return numberFormatter.format(Math.round(safe))
}

function formatCompactCurrency(value?: number | null) {
  const safe = value || 0
  return `${safe < 0 ? '-' : ''}¥${formatCompactMoney(Math.abs(safe))}`
}

function formatTrendAxisCurrency(value?: number | null) {
  const safe = value || 0
  const absolute = Math.abs(safe)
  if (absolute >= 10000) {
    const scaled = absolute / 10000
    const precision = scaled < 10 && !Number.isInteger(scaled) ? 1 : 0
    return `${safe < 0 ? '-' : ''}¥${scaled.toFixed(precision)}万`
  }
  return formatCompactCurrency(safe)
}

function formatPct(value?: number | null) {
  const safe = value || 0
  return `${safe > 0 ? '+' : ''}${safe.toFixed(1)}%`
}

function skuDisplayName(sku: string, productName?: string | null) {
  return productName?.trim() || sku.trim() || '未记录 SKU'
}

function escapeTooltipText(value: string) {
  return value.replace(/[&<>"']/g, (character) => {
    const entities: Record<string, string> = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;'
    }
    return entities[character]
  })
}

function formatDateRangeLabel(value?: string | null) {
  return value ? value.replace('~', ' 至 ') : '-'
}

function formatTrendPointRange(startDate: string, endDate: string) {
  return startDate === endDate ? startDate : `${startDate} 至 ${endDate}`
}

function trendOption({
  points,
  groupBy,
  currentLabel,
  comparisonLabel,
  comparisonName,
  comparisonEnabled,
  color,
  metric,
  isMobile
}: {
  points: DashboardTrendPoint[]
  groupBy: DashboardGroupBy
  currentLabel: string
  comparisonLabel: string
  comparisonName: string
  comparisonEnabled: boolean
  color: string
  metric: DashboardTrendMetric
  isMobile: boolean
}): EChartsOption {
  const formatValue = metric === 'orders' ? formatNumber : formatMoney
  const formatAxisValue = metric === 'orders' ? formatNumber : formatTrendAxisCurrency
  const currentSeriesName = isMobile ? '本期' : `本期 ${currentLabel}`
  const comparisonSeriesName = isMobile ? comparisonName : `${comparisonName} ${comparisonLabel}`
  const showSymbols = points.length <= (isMobile ? 28 : 62)
  const series: NonNullable<EChartsOption['series']> = [
    {
      name: currentSeriesName,
      type: 'line',
      data: points.map((point) => point.currentValue),
      showSymbol: showSymbols,
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { width: 2 },
      itemStyle: { color },
      emphasis: { focus: 'series' }
    }
  ]

  if (comparisonEnabled) {
    series.push({
      name: comparisonSeriesName,
      type: 'line',
      data: points.map((point) => point.comparisonValue),
      showSymbol: false,
      lineStyle: { width: 2, type: 'dashed', color: '#94a3b8' },
      itemStyle: { color: '#94a3b8' },
      emphasis: { focus: 'series' }
    })
  }

  return {
    animation: false,
    color: [color, '#94a3b8'],
    grid: isMobile
      ? { top: 20, right: 10, bottom: 58, left: metric === 'orders' ? 42 : 66 }
      : { top: 24, right: 22, bottom: 58, left: metric === 'orders' ? 56 : 86 },
    tooltip: {
      trigger: 'axis',
      confine: true,
      axisPointer: { type: 'line', lineStyle: { color: '#cbd5e1' } },
      formatter: (params) => {
        const items = Array.isArray(params) ? params : [params]
        const point = points[items[0]?.dataIndex]
        if (!point) return ''
        const lines = [
          `<strong>${formatTrendPointRange(point.currentStartDate, point.currentEndDate)}</strong>`,
          `<span style="color:${color}">●</span> 本期：${formatValue(point.currentValue)}`
        ]
        if (comparisonEnabled) {
          lines.push(
            `<strong>${formatTrendPointRange(point.comparisonStartDate, point.comparisonEndDate)}</strong>`,
            `<span style="color:#94a3b8">●</span> ${comparisonName}：${formatValue(point.comparisonValue)}`
          )
        }
        return lines.join('<br/>')
      }
    },
    legend: {
      bottom: 0,
      left: 0,
      type: 'scroll',
      itemWidth: 18,
      itemHeight: 8,
      textStyle: { color: '#475569', fontSize: isMobile ? 11 : 12 }
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: points.map((point) => point.currentStartDate),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#dbe3ed' } },
      axisLabel: {
        color: '#64748b',
        hideOverlap: true,
        formatter: (value: string) => {
          if (groupBy === 'month') return dayjs(value).format('YYYY年MM月')
          return dayjs(value).format(groupBy === 'week' || points.length > 180 ? 'MM-DD' : 'MM月DD日')
        }
      }
    },
    yAxis: {
      type: 'value',
      min: 0,
      ...(metric === 'orders' ? { minInterval: 1 } : {}),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: '#64748b',
        formatter: (value: number) => formatAxisValue(value)
      },
      splitLine: { lineStyle: { color: '#e8edf4', type: 'dashed' } }
    },
    series
  }
}

function GrowthBadge({ value }: { value: number }) {
  const positive = value >= 0
  return (
    <span className={positive ? 'growth-badge is-up' : 'growth-badge is-down'}>
      {positive ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
      {formatPct(value)}
    </span>
  )
}

function ChartSkeleton({ className }: { className: string }) {
  return (
    <div className={`dashboard-skeleton ${className}`}>
      <Skeleton active paragraph={{ rows: 5 }} title={false} loading />
    </div>
  )
}

function ChartCard({
  title,
  subtitle,
  action,
  children,
  className = ''
}: {
  title: string
  subtitle?: string
  action?: React.ReactNode
  children: React.ReactNode
  className?: string
}) {
  return (
    <Card className={`analytics-card ${className}`}>
      <div className="analytics-card__head">
        <div>
          <h3>{title}</h3>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        {action}
      </div>
      {children}
    </Card>
  )
}

export function Dashboard() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const isMobile = useMediaQuery('(max-width: 768px)')
  const [initialSelection] = useState(() => initialDashboardSelection(searchParams))
  const [initialComparison] = useState(() => initialDashboardComparison(searchParams, initialSelection.range))
  const [period, setPeriod] = useState<DashboardPeriod>(initialSelection.period)
  const [dateRange, setDateRange] = useState<DashboardRange>(initialSelection.range)
  const [shopIds, setShopIds] = useState<number[]>(() => initialDashboardShopIds(searchParams))
  const [shopOptions, setShopOptions] = useState<ShopDto[]>([])
  const [shopOptionsLoading, setShopOptionsLoading] = useState(true)
  const [shopOptionsError, setShopOptionsError] = useState(false)
  const [compareMode, setCompareMode] = useState<DashboardCompareMode>(initialComparison.mode)
  const [customComparisonRange, setCustomComparisonRange] = useState<DashboardRange>(initialComparison.range)
  const [groupBy, setGroupBy] = useState<DashboardGroupBy>(() => initialDashboardGroupBy(searchParams))
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [settingsLoading, setSettingsLoading] = useState(false)
  const [settingsSaving, setSettingsSaving] = useState(false)
  const [settingsCanManage, setSettingsCanManage] = useState(false)
  const [platformSettings, setPlatformSettings] = useState<DashboardPlatformSetting[]>([])
  const settingsButtonRef = useRef<HTMLButtonElement>(null)
  const refreshRequestRef = useRef(0)
  const refreshAbortRef = useRef<AbortController | null>(null)
  const initialRefreshRef = useRef(false)
  const [refreshing, setRefreshing] = useState(false)
  const [overviewLoading, setOverviewLoading] = useState(true)
  const [salesLoading, setSalesLoading] = useState(true)
  const [riskLoading, setRiskLoading] = useState(true)
  const [skusLoading, setSkusLoading] = useState(true)
  const [overview, setOverview] = useState<DashboardOverview | null>(null)
  const [sales, setSales] = useState<DashboardSales | null>(null)
  const [risk, setRisk] = useState<DashboardRisk | null>(null)
  const [skus, setSkus] = useState<DashboardSkus | null>(null)

  const comparisonRange = useMemo(
    () => dashboardComparisonRange(compareMode, dateRange, customComparisonRange),
    [compareMode, customComparisonRange, dateRange]
  )
  const comparisonEnabled = compareMode !== 'none'
  const comparisonName = DASHBOARD_COMPARE_LABELS[compareMode]

  const dateParams = useMemo(
    () => ({
      date_from: dateRange[0].format('YYYY-MM-DD'),
      date_to: dateRange[1].format('YYYY-MM-DD'),
      compare_from: comparisonRange[0].format('YYYY-MM-DD'),
      compare_to: comparisonRange[1].format('YYYY-MM-DD')
    }),
    [comparisonRange, dateRange]
  )

  const dashboardParams = useMemo(
    () => ({ ...dateParams, shop_ids: shopIds.length ? shopIds : undefined }),
    [dateParams, shopIds]
  )

  const shopScopeLabel = shopIds.length ? `已选 ${shopIds.length} 家店铺` : '全部店铺'
  const shopSelectOptions = useMemo(
    () => shopOptions
      .flatMap((shop) => typeof shop.id === 'number'
        ? [{ value: shop.id, label: shop.display_name || shop.account_id || shop.shop_id }]
        : [])
      .sort((left, right) => left.label.localeCompare(right.label, 'zh-CN')),
    [shopOptions]
  )

  useEffect(() => {
    const nextParams = new URLSearchParams(searchParams)
    nextParams.set('period', period)
    nextParams.set('date_from', dateParams.date_from)
    nextParams.set('date_to', dateParams.date_to)
    nextParams.set('compare', compareMode)
    nextParams.set('group_by', groupBy)
    if (shopIds.length) nextParams.set('shop_ids', shopIds.join(','))
    else nextParams.delete('shop_ids')
    if (compareMode === 'custom') {
      nextParams.set('compare_from', dateParams.compare_from)
      nextParams.set('compare_to', dateParams.compare_to)
    } else {
      nextParams.delete('compare_from')
      nextParams.delete('compare_to')
    }
    if (nextParams.toString() !== searchParams.toString()) {
      setSearchParams(nextParams, { replace: true })
    }
  }, [compareMode, dateParams, groupBy, period, searchParams, setSearchParams, shopIds])

  useEffect(() => {
    let active = true
    setShopOptionsLoading(true)
    setShopOptionsError(false)
    listShops({ sort_by: 'display_name', sort_order: 'asc' }, { background: true, silent: true })
      .then((shops) => {
        if (!active) return
        setShopOptions(shops)
        const availableIds = new Set(shops.flatMap((shop) => (typeof shop.id === 'number' ? [shop.id] : [])))
        const staleIds = shopIds.filter((shopId) => !availableIds.has(shopId))
        if (staleIds.length) {
          setShopIds((current) => current.filter((shopId) => availableIds.has(shopId)))
          message.warning('部分店铺已不可用，已从分析范围移除')
        }
      })
      .catch(() => {
        if (!active) return
        setShopOptionsError(true)
        message.error('店铺列表加载失败，工作台已保持全部店铺范围，请刷新页面重试')
      })
      .finally(() => {
        if (active) setShopOptionsLoading(false)
      })
    return () => {
      active = false
    }
  }, [message])

  const refresh = useCallback(async () => {
    const requestId = refreshRequestRef.current + 1
    refreshRequestRef.current = requestId
    refreshAbortRef.current?.abort()
    const controller = new AbortController()
    refreshAbortRef.current = controller
    setRefreshing(true)
    setOverviewLoading(true)
    setSalesLoading(true)
    setRiskLoading(true)
    setSkusLoading(true)

    const loadOverview = fetchDashboardOverview(dashboardParams, { signal: controller.signal })
      .then((result) => {
        if (refreshRequestRef.current === requestId) setOverview(result)
      })
      .finally(() => {
        if (refreshRequestRef.current === requestId) setOverviewLoading(false)
      })
    const loadSales = fetchDashboardSales(dashboardParams, { signal: controller.signal })
      .then((result) => {
        if (refreshRequestRef.current === requestId) setSales(result)
      })
      .finally(() => {
        if (refreshRequestRef.current === requestId) setSalesLoading(false)
      })
    const loadRisk = fetchDashboardRisk(dashboardParams, { signal: controller.signal })
      .then((result) => {
        if (refreshRequestRef.current === requestId) setRisk(result)
      })
      .finally(() => {
        if (refreshRequestRef.current === requestId) setRiskLoading(false)
      })
    const loadSkus = fetchDashboardSkus(dashboardParams, { signal: controller.signal })
      .then((result) => {
        if (refreshRequestRef.current === requestId) setSkus(result)
      })
      .finally(() => {
        if (refreshRequestRef.current === requestId) setSkusLoading(false)
      })

    await Promise.allSettled([loadOverview, loadSales, loadRisk, loadSkus])
    if (refreshRequestRef.current === requestId) setRefreshing(false)
  }, [dashboardParams])

  useLayoutEffect(() => {
    const delay = initialRefreshRef.current ? 260 : 0
    initialRefreshRef.current = true
    refreshRequestRef.current += 1
    refreshAbortRef.current?.abort()
    setRefreshing(true)
    setOverviewLoading(true)
    setSalesLoading(true)
    setRiskLoading(true)
    setSkusLoading(true)
    const timer = window.setTimeout(() => void refresh(), delay)
    return () => window.clearTimeout(timer)
  }, [refresh])

  useEffect(() => () => refreshAbortRef.current?.abort(), [])

  const comparison = overview?.mtd_comparison
  const overdueOrders = useMemo(
    () =>
      (risk?.risk_buckets || [])
        .filter((row) => row.key.startsWith('overdue'))
        .reduce((sum, row) => sum + row.orders, 0),
    [risk]
  )
  const due24Orders = risk?.risk_buckets.find((row) => row.key === 'due_24')?.orders || 0
  const actionOrders = overdueOrders + due24Orders
  const scopedEmpty = shopIds.length ? `${shopScopeLabel}在所选日期` : '所选日期'

  const applyDashboardSelection = useCallback(
    (nextPeriod: DashboardPeriod, nextRange: DashboardRange) => {
      const normalizedRange: DashboardRange = [nextRange[0].startOf('day'), nextRange[1].startOf('day')]
      const latestDate = dayjs().subtract(1, 'day').startOf('day')
      if (normalizedRange[0].isAfter(normalizedRange[1])) {
        message.warning('请选择有效的付款日期范围')
        return
      }
      if (normalizedRange[1].isAfter(latestDate, 'day')) {
        message.warning('统计日期不能包含今天或未来日期')
        return
      }
      if (normalizedRange[1].diff(normalizedRange[0], 'day') > 366) {
        message.warning('统计日期范围不能超过367天')
        return
      }
      setPeriod(nextPeriod)
      setDateRange(normalizedRange)
      if (compareMode === 'custom') {
        setCustomComparisonRange(dashboardComparisonRange('previous', normalizedRange))
      }
    },
    [compareMode, message]
  )

  const applyCustomComparison = useCallback(
    (nextRange: DashboardRange) => {
      const normalizedRange: DashboardRange = [nextRange[0].startOf('day'), nextRange[1].startOf('day')]
      const latestDate = dayjs().subtract(1, 'day').startOf('day')
      if (normalizedRange[1].isAfter(latestDate, 'day')) {
        message.warning('对比日期不能包含今天或未来日期')
        return
      }
      if (normalizedRange[1].diff(normalizedRange[0], 'day') !== dateRange[1].diff(dateRange[0], 'day')) {
        message.warning('对比周期天数需要与当前统计周期一致')
        return
      }
      setCustomComparisonRange(normalizedRange)
    },
    [dateRange, message]
  )

  const openSettings = useCallback(async () => {
    setSettingsOpen(true)
    setSettingsLoading(true)
    try {
      const result = await fetchDashboardSettings()
      setPlatformSettings(result.items)
      setSettingsCanManage(result.can_manage)
    } finally {
      setSettingsLoading(false)
    }
  }, [])

  const updatePlatformSetting = useCallback((platform: string, patch: Partial<DashboardPlatformSetting>) => {
    setPlatformSettings((rows) => rows.map((row) => (row.platform === platform ? { ...row, ...patch } : row)))
  }, [])

  const applySettings = useCallback(async () => {
    if (!settingsCanManage) {
      setSettingsOpen(false)
      return
    }
    setSettingsSaving(true)
    try {
      const result = await updateDashboardSettings(platformSettings)
      setPlatformSettings(result.items)
      setSettingsOpen(false)
      await refresh()
      message.success(`设置已保存，更新 ${result.backfilled} 个订单履约时间`)
    } finally {
      setSettingsSaving(false)
    }
  }, [message, platformSettings, refresh, settingsCanManage])

  const settingsColumns = useMemo<ColumnsType<DashboardPlatformSetting>>(
    () => [
      {
        title: '平台',
        dataIndex: 'platform_name',
        width: '40%',
        render: (value: string, row) => (
          <span className="dashboard-setting-platform">
            <strong>{value}</strong>
            <small>{row.platform}</small>
          </span>
        )
      },
      {
        title: '预计收款比例（%）',
        dataIndex: 'receipt_rate_pct',
        width: '30%',
        render: (value: number, row) => (
          <InputNumber
            aria-label={`${row.platform_name}预计收款比例`}
            value={value}
            min={0}
            max={100}
            precision={2}
            disabled={!settingsCanManage}
            onChange={(next) => updatePlatformSetting(row.platform, { receipt_rate_pct: Number(next ?? 0) })}
          />
        )
      },
      {
        title: '付款后履约时限（天）',
        dataIndex: 'fulfillment_days',
        width: '30%',
        render: (value: number, row) => (
          <InputNumber
            aria-label={`${row.platform_name}付款后履约天数`}
            value={value}
            min={0}
            max={365}
            precision={0}
            disabled={!settingsCanManage}
            onChange={(next) => updatePlatformSetting(row.platform, { fulfillment_days: Number(next ?? 0) })}
          />
        )
      }
    ],
    [settingsCanManage, updatePlatformSetting]
  )

  const orderTrendPoints = useMemo(
    () =>
      dashboardTrendPoints(
        sales?.daily_sales || [],
        sales?.comparison_daily_sales || [],
        dateRange,
        comparisonRange,
        groupBy,
        'orders'
      ),
    [comparisonRange, dateRange, groupBy, sales]
  )

  const receiptTrendPoints = useMemo(
    () =>
      dashboardTrendPoints(
        sales?.daily_sales || [],
        sales?.comparison_daily_sales || [],
        dateRange,
        comparisonRange,
        groupBy,
        'expected_receipt'
      ),
    [comparisonRange, dateRange, groupBy, sales]
  )

  const orderTrendOption = useMemo<EChartsOption>(
    () =>
      trendOption({
        points: orderTrendPoints,
        groupBy,
        currentLabel: formatDateRangeLabel(sales?.current_label || comparison?.current_label),
        comparisonLabel: formatDateRangeLabel(sales?.comparison_label || comparison?.previous_label),
        comparisonName,
        comparisonEnabled,
        color: '#2563eb',
        metric: 'orders',
        isMobile
      }),
    [comparison?.current_label, comparison?.previous_label, comparisonEnabled, comparisonName, groupBy, isMobile, orderTrendPoints, sales]
  )

  const receiptTrendOption = useMemo<EChartsOption>(
    () =>
      trendOption({
        points: receiptTrendPoints,
        groupBy,
        currentLabel: formatDateRangeLabel(sales?.current_label || comparison?.current_label),
        comparisonLabel: formatDateRangeLabel(sales?.comparison_label || comparison?.previous_label),
        comparisonName,
        comparisonEnabled,
        color: '#0f766e',
        metric: 'expected_receipt',
        isMobile
      }),
    [comparison?.current_label, comparison?.previous_label, comparisonEnabled, comparisonName, groupBy, isMobile, receiptTrendPoints, sales]
  )

  const salesOption = useMemo<EChartsOption>(() => {
    const rows = [...(sales?.shop_sales || [])].reverse()
    const axisLabelWidth = isMobile ? 84 : 158
    return {
      color: ['#2563eb', '#0f766e'],
      grid: isMobile ? { top: 50, right: 18, bottom: 24, left: 108 } : { top: 52, right: 64, bottom: 24, left: 184 },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params) => {
          const item = Array.isArray(params) ? params[0] : params
          const row = rows[item.dataIndex]
          if (!row) return ''
          const voidedLine = row.voided ? `<br/>作废：${formatNumber(row.voided)}` : ''
          return `${row.shop}<br/>平台：${row.platform}<br/>订单数：${formatNumber(row.orders)}<br/>人民币金额：${formatMoney(row.raw_amount)}<br/>预计收款：${formatMoney(row.expected_receipt)}（${row.receipt_rate_pct}%）<br/>客单价：${formatMoney(row.raw_aov)}${voidedLine}`
        }
      },
      legend: {
        top: 6,
        right: isMobile ? 0 : 8,
        itemWidth: 10,
        itemHeight: 10,
        textStyle: { color: '#64748b', fontSize: isMobile ? 11 : 12 }
      },
      xAxis: [
        {
          type: 'value',
          name: '订单',
          minInterval: 1,
          splitLine: { lineStyle: { color: '#edf2f7' } },
          axisLabel: { color: '#64748b' }
        },
        {
          type: 'value',
          name: '金额',
          position: 'top',
          splitLine: { show: false },
          axisLabel: {
            color: '#64748b',
            formatter: (value: number) => formatCompactMoney(value)
          }
        }
      ],
      yAxis: {
        type: 'category',
        data: rows.map((row) => row.shop),
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: {
          color: '#334155',
          width: axisLabelWidth,
          overflow: 'truncate',
          formatter: (value: string, index: number) => {
            const row = rows[index]
            if (!row) return value
            const orderText = isMobile ? `${formatNumber(row.orders)}单` : `订单数 ${formatNumber(row.orders)}`
            const receiptText = isMobile
              ? formatCompactCurrency(row.expected_receipt)
              : `收款 ${formatCompactCurrency(row.expected_receipt)}`
            return `{shop|${value}}\n{orders|${orderText}}  {amount|${receiptText}}`
          },
          rich: {
            shop: {
              color: '#334155',
              fontSize: isMobile ? 11 : 12,
              lineHeight: isMobile ? 16 : 18,
              width: axisLabelWidth,
              overflow: 'truncate',
              align: 'right'
            },
            orders: {
              color: '#2563eb',
              fontSize: isMobile ? 10 : 11,
              lineHeight: isMobile ? 14 : 15,
              fontWeight: 700
            },
            amount: {
              color: '#0f766e',
              fontSize: isMobile ? 10 : 11,
              lineHeight: isMobile ? 14 : 15,
              fontWeight: 700
            }
          }
        }
      },
      series: [
        {
          name: '订单数',
          type: 'bar',
          barWidth: 16,
          itemStyle: { borderRadius: 5 },
          data: rows.map((row) => row.orders)
        },
        {
          name: '预计收款',
          type: 'scatter',
          xAxisIndex: 1,
          symbolSize: 10,
          label: {
            show: false
          },
          data: rows.map((row) => row.expected_receipt)
        }
      ]
    }
  }, [isMobile, sales])

  const riskOption = useMemo<EChartsOption>(() => {
    const rows = risk?.risk_buckets || []
    const colors: Record<string, string> = {
      overdue_48: '#991b1b',
      overdue_24_48: '#dc2626',
      overdue_0_24: '#f97316',
      due_24: '#f59e0b',
      due_48: '#84cc16',
      due_later: '#22c55e',
      no_deadline: '#94a3b8'
    }
    return {
      grid: isMobile ? { top: 18, right: 32, bottom: 18, left: 68 } : { top: 22, right: 18, bottom: 20, left: 88 },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params) => {
          const item = Array.isArray(params) ? params[0] : params
          const row = rows[item.dataIndex]
          return `${row.label}<br/>订单：${row.orders}<br/>人民币金额：${formatMoney(row.raw_amount)}`
        }
      },
      xAxis: {
        type: 'value',
        minInterval: 1,
        splitLine: { lineStyle: { color: '#edf2f7' } },
        axisLabel: { color: '#64748b' }
      },
      yAxis: {
        type: 'category',
        inverse: true,
        data: rows.map((row) => row.label),
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: {
          color: '#334155',
          fontWeight: 600,
          width: isMobile ? 58 : 82,
          overflow: 'truncate'
        }
      },
      series: [
        {
          name: '订单数',
          type: 'bar',
          barWidth: isMobile ? 14 : 18,
          label: { show: true, position: 'right', color: '#334155', fontWeight: 700, fontSize: isMobile ? 10 : 12 },
          itemStyle: {
            borderRadius: 5,
            color: (params) => colors[rows[params.dataIndex]?.key] || '#64748b'
          },
          data: rows.map((row) => row.orders)
        }
      ]
    }
  }, [isMobile, risk])

  const hotSkuOption = useMemo<EChartsOption>(() => {
    const rows = [...(skus?.hot_skus || [])].slice(0, 10).reverse()
    const series: NonNullable<EChartsOption['series']> = [
      {
        name: '本期',
        type: 'bar',
        barWidth: isMobile ? 8 : 12,
        itemStyle: { borderRadius: 4 },
        data: rows.map((row) => row.units_7d)
      }
    ]
    if (comparisonEnabled) {
      series.push({
        name: comparisonName,
        type: 'bar',
        barWidth: isMobile ? 8 : 12,
        itemStyle: { borderRadius: 4 },
        data: rows.map((row) => row.units_prev_7d)
      })
    }
    return {
      color: ['#0f766e', '#cbd5e1'],
      grid: isMobile ? { top: 34, right: 12, bottom: 22, left: 98 } : { top: 28, right: 28, bottom: 24, left: 220 },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params) => {
          const items = Array.isArray(params) ? params : [params]
          const row = rows[items[0].dataIndex]
          const productName = escapeTooltipText(skuDisplayName(row.sku, row.product_name))
          const sku = escapeTooltipText(row.sku)
          const comparisonLine = comparisonEnabled
            ? `<br/>${comparisonName}（${skus?.previous_label || '-'}）：${row.units_prev_7d}`
            : ''
          return `${productName}<br/>SKU：${sku}<br/>本期（${skus?.current_label || '-'}）：${row.units_7d}${comparisonLine}<br/>待处理：${row.pending_orders}`
        }
      },
      legend: {
        top: 0,
        right: isMobile ? 0 : 8,
        itemWidth: 10,
        itemHeight: 10,
        textStyle: { color: '#64748b', fontSize: isMobile ? 11 : 12 }
      },
      xAxis: {
        type: 'value',
        minInterval: 1,
        splitLine: { lineStyle: { color: '#edf2f7' } },
        axisLabel: { color: '#64748b' }
      },
      yAxis: {
        type: 'category',
        data: rows.map((row) => skuDisplayName(row.sku, row.product_name)),
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: {
          color: '#334155',
          width: isMobile ? 88 : 204,
          overflow: 'truncate'
        }
      },
      series
    }
  }, [comparisonEnabled, comparisonName, isMobile, skus])

  return (
    <div className="dashboard-page dashboard-analytics-page" aria-busy={refreshing}>
      <div className="analytics-hero">
        <div>
          <div className="hero-kicker">运营首页</div>
          <h1>订单经营与履约风险</h1>
          <p>
            {DASHBOARD_PERIOD_LABELS[period]}统计：付款日期 {comparison?.current_label || `${dateParams.date_from}~${dateParams.date_to}`}，店铺范围：{shopScopeLabel}。统一折算人民币并按平台比例计算预计收款。
          </p>
          <div
            className="analytics-hero__scope"
            role="group"
            aria-labelledby="dashboard-shop-scope-label"
            aria-busy={shopOptionsLoading}
          >
            <span id="dashboard-shop-scope-label" className="analytics-hero__scope-label">
              <ShopOutlined aria-hidden="true" />
              店铺范围
            </span>
            <Select<number[]>
              mode="multiple"
              aria-label="选择工作台分析店铺"
              value={shopIds}
              options={shopSelectOptions}
              loading={shopOptionsLoading}
              disabled={shopOptionsError}
              allowClear
              showSearch
              optionFilterProp="label"
              maxTagCount={1}
              maxTagPlaceholder={() => `已选 ${shopIds.length} 家`}
              menuItemSelectedIcon={null}
              optionRender={(option) => (
                <Checkbox
                  className="analytics-shop-option-checkbox"
                  checked={shopIds.includes(Number(option.value))}
                  tabIndex={-1}
                  aria-hidden
                  onChange={() => undefined}
                >
                  {option.label}
                </Checkbox>
              )}
              placeholder="全部店铺"
              className="analytics-hero__shop-select"
              onChange={setShopIds}
            />
            <span className="analytics-hero__scope-status" aria-live="polite">
              {shopOptionsError ? '店铺列表加载失败，请刷新页面重试' : shopScopeLabel}
            </span>
          </div>
        </div>
        <Space className="analytics-hero__actions">
          <Tooltip title="Ozon 默认按69%、Wildberries按75%、其他平台按100%计算，比例可在设置中调整">
            <Tag color="green">预计收款口径</Tag>
          </Tooltip>
          <Button ref={settingsButtonRef} icon={<SettingOutlined />} onClick={() => void openSettings()}>
            设置
          </Button>
          <Button icon={<ReloadOutlined />} onClick={refresh} loading={refreshing}>
            刷新
          </Button>
        </Space>
      </div>

      <Row gutter={[14, 14]} className="metric-grid">
        <Col xs={24} md={6}>
          <Card className="metric-card">
              <span className="metric-card__icon blue">
                <ShoppingCartOutlined />
              </span>
              <p>本期订单</p>
              {overviewLoading ? (
                <Skeleton active paragraph={{ rows: 1 }} title={false} loading />
              ) : (
                <>
                  <strong>{formatNumber(comparison?.current_orders)}</strong>
                  <div>
                    {comparisonEnabled ? <GrowthBadge value={comparison?.order_growth_pct || 0} /> : null}
                    <span>{comparisonEnabled ? `较${comparisonName}` : '未开启对比'}</span>
                  </div>
                </>
              )}
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card className="metric-card">
              <span className="metric-card__icon teal">
                <LineChartOutlined />
              </span>
              <p>人民币订单金额</p>
              {overviewLoading ? (
                <Skeleton active paragraph={{ rows: 1 }} title={false} loading />
              ) : (
                <>
                  <strong>{formatMoney(comparison?.current_amount)}</strong>
                  <div>
                    {comparisonEnabled ? <GrowthBadge value={comparison?.amount_growth_pct || 0} /> : null}
                    <span>按付款日最近汇率折算</span>
                  </div>
                </>
              )}
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card className="metric-card">
              <span className="metric-card__icon teal">
                <PayCircleOutlined />
              </span>
              <p>预计收款</p>
              {overviewLoading ? (
                <Skeleton active paragraph={{ rows: 1 }} title={false} loading />
              ) : (
                <>
                  <strong>{formatMoney(comparison?.current_receipt)}</strong>
                  <div>
                    {comparisonEnabled ? <GrowthBadge value={comparison?.receipt_growth_pct || 0} /> : null}
                    <span>{comparisonEnabled ? `较${comparisonName}` : '未开启对比'}</span>
                  </div>
                </>
              )}
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card className="metric-card danger">
              <span className="metric-card__icon red">
                <AlertOutlined />
              </span>
              <p>今日需处理</p>
              {riskLoading ? (
                <Skeleton active paragraph={{ rows: 1 }} title={false} loading />
              ) : (
                <>
                  <strong>{formatNumber(actionOrders)}</strong>
                  <div>
                    <span className="danger-text">{formatNumber(overdueOrders)} 单已超时</span>
                    <span>{formatNumber(due24Orders)} 单24h内到期</span>
                  </div>
                </>
              )}
          </Card>
        </Col>
      </Row>

      <section className="trend-analysis" aria-labelledby="trend-analysis-title">
        <div className="trend-analysis__heading">
          <div>
            <h2 id="trend-analysis-title">订单与收款趋势</h2>
            <p>按付款日期汇总，两张图共用周期、分组和对比条件。</p>
          </div>
        </div>

        <div className="trend-filter-bar">
          <Segmented
            aria-label="趋势统计周期"
            options={DASHBOARD_PERIOD_OPTIONS}
            value={period === 'custom' ? '' : period}
            onChange={(value) => {
              const nextPeriod = value as Exclude<DashboardPeriod, 'custom'>
              applyDashboardSelection(nextPeriod, currentDashboardRange(nextPeriod))
            }}
          />
          <RangePicker
            aria-label="付款日期范围"
            value={dateRange}
            allowClear={false}
            format="YYYY-MM-DD"
            disabledDate={(current) => Boolean(current && !current.isBefore(dayjs(), 'day'))}
            onChange={(dates) => {
              if (dates?.[0] && dates?.[1]) {
                applyDashboardSelection('custom', [dates[0], dates[1]])
              }
            }}
          />
          <span className="trend-filter-bar__separator" aria-hidden="true" />
          <SwapOutlined className="trend-filter-bar__icon" aria-hidden="true" />
          <Select<DashboardCompareMode>
            aria-label="选择对比周期"
            value={compareMode}
            options={DASHBOARD_COMPARE_OPTIONS}
            onChange={(value) => {
              setCompareMode(value)
              if (value === 'custom') {
                setCustomComparisonRange(dashboardComparisonRange('previous', dateRange))
              }
            }}
          />
          {compareMode === 'custom' ? (
            <RangePicker
              aria-label="自定义对比日期范围"
              value={customComparisonRange}
              allowClear={false}
              format="YYYY-MM-DD"
              disabledDate={(current) => Boolean(current && !current.isBefore(dayjs(), 'day'))}
              onChange={(dates) => {
                if (dates?.[0] && dates?.[1]) applyCustomComparison([dates[0], dates[1]])
              }}
            />
          ) : null}
          <div className="trend-filter-bar__grouping">
            <CalendarOutlined />
            <span>分组</span>
            <Select<DashboardGroupBy>
              aria-label="选择图表分组维度"
              value={groupBy}
              options={DASHBOARD_GROUP_OPTIONS}
              popupMatchSelectWidth={false}
              onChange={setGroupBy}
            />
          </div>
        </div>

        <div className="trend-chart-stack">
          <ChartCard
            title="订单量"
            subtitle={`本期 ${formatDateRangeLabel(sales?.current_label || comparison?.current_label)}${comparisonEnabled ? `，${comparisonName} ${formatDateRangeLabel(sales?.comparison_label || comparison?.previous_label)}` : ''}`}
            className="trend-card"
            action={
              <div className="trend-card__summary">
                <strong>{formatNumber(comparison?.current_orders)} 单</strong>
                {comparisonEnabled ? <GrowthBadge value={comparison?.order_growth_pct || 0} /> : null}
              </div>
            }
          >
            {salesLoading ? (
              <ChartSkeleton className="chart--trend" />
            ) : (sales?.daily_sales.length || (comparisonEnabled && (sales?.comparison_daily_sales || []).length)) ? (
              <ReactECharts
                option={orderTrendOption}
                className="chart chart--trend"
                style={{ height: isMobile ? 278 : 330 }}
                notMerge
                lazyUpdate
              />
            ) : (
              <Empty description={`${scopedEmpty}暂无订单数据`} />
            )}
          </ChartCard>

          <ChartCard
            title="预计收款"
            subtitle={`本期 ${formatDateRangeLabel(sales?.current_label || comparison?.current_label)}${comparisonEnabled ? `，${comparisonName} ${formatDateRangeLabel(sales?.comparison_label || comparison?.previous_label)}` : ''}`}
            className="trend-card"
            action={
              <div className="trend-card__summary">
                <strong>{formatMoney(comparison?.current_receipt)}</strong>
                {comparisonEnabled ? <GrowthBadge value={comparison?.receipt_growth_pct || 0} /> : null}
              </div>
            }
          >
            {salesLoading ? (
              <ChartSkeleton className="chart--trend" />
            ) : (sales?.daily_sales.length || (comparisonEnabled && (sales?.comparison_daily_sales || []).length)) ? (
              <ReactECharts
                option={receiptTrendOption}
                className="chart chart--trend"
                style={{ height: isMobile ? 278 : 330 }}
                notMerge
                lazyUpdate
              />
            ) : (
              <Empty description={`${scopedEmpty}暂无预计收款数据`} />
            )}
          </ChartCard>
        </div>
      </section>

      <Row gutter={[14, 14]} className="main-grid">
        <Col xs={24} xl={15}>
          <ChartCard
              title="店铺订单与预计收款"
              subtitle={`${formatNumber(comparison?.current_orders)} 单，订单金额 ${formatMoney(comparison?.current_amount)}，预计收款 ${formatMoney(comparison?.current_receipt)}`}
              action={<BarChartOutlined className="card-head-icon" />}
            >
              {salesLoading ? (
                <ChartSkeleton className="chart--sales" />
              ) : (sales?.shop_sales || []).length ? (
                <ReactECharts
                  option={salesOption}
                  className="chart chart--sales"
                  style={{ height: isMobile ? 300 : 338 }}
                  notMerge
                  lazyUpdate
                />
              ) : (
                <Empty description={`${shopScopeLabel}暂无销售数据`} />
              )}
          </ChartCard>
        </Col>
        <Col xs={24} xl={9}>
          <ChartCard
              title="待发货超时风险"
              subtitle={`${shopScopeLabel} · 当前实时待处理，${formatNumber(actionOrders)} 单需要今天优先处理`}
              className="risk-panel"
              action={
                <Button
                  type="link"
                  size="small"
                  onClick={() => {
                    const params = new URLSearchParams({ risk: 'unhandled' })
                    if (shopIds.length) params.set('shop_ids', shopIds.join(','))
                    navigate(`/orders?${params.toString()}`)
                  }}
                >
                  查看订单 <ArrowRightOutlined />
                </Button>
              }
            >
              {riskLoading ? (
                <ChartSkeleton className="chart--risk" />
              ) : risk?.risk_buckets.length ? (
                <ReactECharts
                  option={riskOption}
                  className="chart chart--risk"
                  style={{ height: isMobile ? 220 : 240 }}
                  notMerge
                  lazyUpdate
                />
              ) : (
                <Empty description="暂无待发风险" />
              )}
              <div className="risk-shop-list">
                {riskLoading ? <Skeleton active paragraph={{ rows: 3 }} title={false} loading /> : null}
                {!riskLoading && (risk?.risk_shops || []).slice(0, 3).map((row) => (
                  <button
                    key={`${row.platform}-${row.shop}`}
                    type="button"
                    onClick={() => {
                      const params = new URLSearchParams({ risk: 'unhandled', platform: row.platform, shop: row.shop })
                      navigate(`/orders?${params.toString()}`)
                    }}
                  >
                    <span>
                      <strong>{row.shop}</strong>
                      <small>{row.platform}</small>
                    </span>
                    <em>{row.overdue_orders} 超时</em>
                  </button>
                ))}
              </div>
          </ChartCard>
        </Col>
      </Row>

      <Row gutter={[14, 14]}>
        <Col xs={24} xl={14}>
          <ChartCard
            title="热销 SKU 趋势"
            subtitle={`本期 ${skus?.current_label || '-'}${comparisonEnabled ? `，${comparisonName} ${skus?.previous_label || '-'}` : ''}`}
          >
              {skusLoading ? (
                <ChartSkeleton className="chart--sku" />
              ) : skus?.hot_skus.length ? (
                <ReactECharts
                  option={hotSkuOption}
                  className="chart chart--sku"
                  style={{ height: isMobile ? 320 : 370 }}
                  notMerge
                  lazyUpdate
                />
              ) : (
                <Empty description="暂无 SKU 数据" />
              )}
          </ChartCard>
        </Col>
        <Col xs={24} xl={10}>
          <ChartCard
              title="待发 SKU 提醒"
              subtitle="按超时单数、待发件数排序"
              action={
                <Button type="link" size="small" onClick={() => navigate('/order-summary')}>
                  明细表 <ArrowRightOutlined />
                </Button>
              }
            >
              <div className="sku-alert-list">
                {skusLoading ? <Skeleton active paragraph={{ rows: 6 }} title={false} loading /> : null}
                {!skusLoading && (skus?.risk_skus || []).map((row, index) => {
                  const productName = skuDisplayName(row.sku, row.product_name)
                  return (
                    <button
                      key={row.sku}
                      type="button"
                      aria-label={`查看 ${productName}，SKU ${row.sku} 的订单明细`}
                      onClick={() => navigate('/order-summary')}
                    >
                      <span className="sku-alert-list__rank">{index + 1}</span>
                      <span className="sku-alert-list__main">
                        <strong title={productName}>{productName}</strong>
                        <small title={row.sku}>{row.product_name ? `SKU：${row.sku}` : '未维护产品中文名称'}</small>
                      </span>
                      <span className="sku-alert-list__meta">
                        <em>{row.pending_units} 件</em>
                        {row.overdue_orders > 0 ? <Tag color="red">{row.overdue_orders} 超时</Tag> : <Tag>待发</Tag>}
                      </span>
                    </button>
                  )
                })}
                {!skusLoading && !skus?.risk_skus.length ? <Empty description="暂无待发 SKU" /> : null}
              </div>
          </ChartCard>
        </Col>
      </Row>

      <div className="dashboard-footnote">
          更新时间：{formatTime(overview?.generated_at || '') || '-'}。全部订单中有 {formatNumber(overview?.blank_currency_orders)} 单币种为空，金额为非作废订单按付款日期汇率折算人民币。
      </div>

      <Modal
        title="工作台设置"
        open={settingsOpen}
        width={820}
        wrapClassName="dashboard-settings-modal"
        onCancel={() => setSettingsOpen(false)}
        focusTriggerAfterClose={false}
        afterOpenChange={(open) => {
          if (open) {
            document.querySelector<HTMLButtonElement>('.dashboard-settings-modal .ant-modal-close')?.focus()
          } else {
            settingsButtonRef.current?.focus()
          }
        }}
        footer={[
          settingsCanManage ? (
            <Button key="reset" onClick={() => setPlatformSettings((rows) => rows.map(resetPlatformSetting))}>
              恢复默认参数
            </Button>
          ) : null,
          <Button key="cancel" onClick={() => setSettingsOpen(false)}>
            {settingsCanManage ? '取消' : '关闭'}
          </Button>,
          settingsCanManage ? (
            <Button key="apply" type="primary" loading={settingsSaving} onClick={() => void applySettings()}>
              保存并应用
            </Button>
          ) : null
        ]}
      >
        <Form layout="vertical" className="dashboard-settings-form">
          <div className="dashboard-settings-section-head">
            <div>
              <h3>平台参数</h3>
              <p>预计收款按人民币订单金额乘以平台比例；履约时间统一从付款时间起算。</p>
            </div>
            {!settingsCanManage && !settingsLoading ? <Tag>仅管理员可修改</Tag> : null}
          </div>
          {!settingsCanManage && !settingsLoading ? (
            <Alert type="info" showIcon message="当前账号只能查看平台参数，修改权限仅向管理员开放。" />
          ) : null}
          <Table<DashboardPlatformSetting>
            rowKey="platform"
            className="dashboard-settings-table"
            columns={settingsColumns}
            dataSource={platformSettings}
            loading={settingsLoading}
            pagination={false}
            size="small"
            scroll={{ y: 350 }}
          />
        </Form>
      </Modal>
    </div>
  )
}
