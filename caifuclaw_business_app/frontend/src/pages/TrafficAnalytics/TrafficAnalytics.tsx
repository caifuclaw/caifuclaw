import { type CSSProperties, type ReactNode, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import dayjs, { type Dayjs } from 'dayjs'
import {
  AreaChartOutlined,
  EyeOutlined,
  FilterOutlined,
  ReloadOutlined,
  SearchOutlined,
  SettingOutlined,
  SyncOutlined
} from '@ant-design/icons'
import {
  Alert,
  App,
  Button,
  Checkbox,
  DatePicker,
  Empty,
  Input,
  InputNumber,
  Modal,
  Segmented,
  Select,
  Tabs,
  Tag,
  Tooltip
} from 'antd'
import type { ColumnsType, TableProps } from 'antd/es/table'
import { DataTable, type DataTableColumnsType, type DataTableConfig } from '@/components/DataTable'
import {
  fetchTrafficCategories,
  fetchTrafficCategorySkuComparison,
  fetchTrafficCategorySkuFocusAnalysis,
  fetchTrafficComparison,
  fetchTrafficRankings,
  fetchTrafficSummary,
  listTrafficAccounts,
  syncTrafficAnalytics,
  type TrafficAccount,
  type TrafficCategoryResponse,
  type TrafficCategoryRow,
  type TrafficComparisonChangeDirection,
  type TrafficComparisonDimension,
  type TrafficComparisonRow,
  type TrafficComparisonSort,
  type TrafficCoverage,
  type TrafficFilters,
  type TrafficMetricKey,
  type TrafficMetricRow,
  type TrafficPeriodFallback,
  type TrafficRateMetricKey,
  type TrafficSkuFocusReason,
  type TrafficSkuFocusRow,
  type TrafficSortOrder
} from '@/api/trafficAnalytics'
import { formatTime } from '@/utils/format'
import {
  categorySkuComparisonContextError,
  resolveCategorySkuComparisonContext
} from './categorySkuComparisonContext'
import { categorySkuSortFromTable, comparisonSortFromTable } from './comparisonSort'
import { compareNullableTableMetric, rankingRateSortFromTable } from './rankingSort'
import { fitTableBodyHeightToRows } from './tableBodyHeight'
import './TrafficAnalytics.less'

const { RangePicker } = DatePicker
const numberFormatter = new Intl.NumberFormat('zh-CN')
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
const rankingMetricOptions = [
  { label: '按曝光', value: 'impressions' },
  { label: '按点击', value: 'clicks' },
  { label: '按加购', value: 'add_to_cart' },
  { label: '按下单', value: 'orders' }
] satisfies Array<{ label: string; value: TrafficMetricKey }>
const comparisonMetricOptions = [
  { label: '曝光环比', value: 'impressions' },
  { label: '点击环比', value: 'clicks' },
  { label: '加购环比', value: 'add_to_cart' },
  { label: '下单环比', value: 'orders' }
] satisfies Array<{ label: string; value: TrafficMetricKey }>
const comparisonDimensionOptions = [
  { label: '按 SKU', value: 'sku' },
  { label: '按品类', value: 'category' }
] satisfies Array<{ label: string; value: TrafficComparisonDimension }>
const comparisonMetricLabels: Record<TrafficMetricKey, string> = {
  impressions: '曝光',
  clicks: '点击',
  add_to_cart: '加购',
  orders: '下单'
}
type CategorySkuModalMode = 'comparison' | 'focus'
const categorySkuModalModeOptions = [
  { label: '环比明细', value: 'comparison' },
  { label: '重点 SKU', value: 'focus' }
] satisfies Array<{ label: string; value: CategorySkuModalMode }>
const focusMetricKeys: TrafficMetricKey[] = ['impressions', 'clicks', 'add_to_cart', 'orders']
const focusReasonMeta: Record<TrafficSkuFocusReason, { label: string; color: string }> = {
  high_impressions_no_orders: { label: '高曝光零下单', color: 'red' },
  high_clicks_missing_impressions_or_cart: { label: '点击榜错位', color: 'gold' },
  high_cart_missing_orders: { label: '加购未进下单榜', color: 'orange' },
  high_orders_missing_impressions: { label: '下单低曝光', color: 'blue' }
}

function focusReasonDescription(reason: TrafficSkuFocusReason, topN: number) {
  if (reason === 'high_impressions_no_orders') return `曝光 Top${topN}，本期下单为 0`
  if (reason === 'high_clicks_missing_impressions_or_cart') return `点击 Top${topN}，且曝光或加购至少一项未进 Top${topN}`
  if (reason === 'high_cart_missing_orders') return `加购 Top${topN}，但下单未进 Top${topN}`
  return `下单 Top${topN}，但曝光未进 Top${topN}`
}

const TRAFFIC_SUMMARY_TABLE_CONFIG: DataTableConfig = {
  tableKey: 'traffic-analytics.summary.v2',
  primaryColumnKey: 'platform',
  columns: [
    { key: 'platform', title: '平台', required: true, fixed: 'left' },
    { key: 'shop_name', title: '店铺', fixed: 'left' },
    { key: 'region', title: '地区' },
    { key: 'impressions', title: '曝光量' },
    { key: 'clicks', title: '点击/访问' },
    { key: 'add_to_cart', title: '加购量' },
    { key: 'orders', title: '订单数' },
    { key: 'buyers', title: '买家数' },
    { key: 'units_sold', title: '售出件数' },
    { key: 'ctr', title: 'CTR（点击率）' },
    { key: 'cart_rate', title: '加购率' },
    { key: 'cvr', title: 'CVR（转化率）' },
    { key: 'revenue', title: '成交额' },
    { key: 'negative_reviews', title: '负面评价' },
    { key: 'period', title: '数据周期' },
    { key: 'synced_at', title: '同步时间' },
    { key: 'source', title: '来源' }
  ]
}

const TRAFFIC_RANKING_TABLE_CONFIG: DataTableConfig = {
  tableKey: 'traffic-analytics.rankings',
  primaryColumnKey: 'rank',
  columns: [
    { key: 'rank', title: '综合排名', required: true, fixed: 'left' },
    { key: 'platform', title: '平台', fixed: 'left' },
    { key: 'shop_name', title: '店铺' },
    { key: 'region', title: '地区' },
    { key: 'sku', title: 'SKU' },
    { key: 'product_name', title: '商品名称' },
    { key: 'impressions', title: '曝光量' },
    { key: 'clicks', title: '点击/访问' },
    { key: 'add_to_cart', title: '加购量' },
    { key: 'orders', title: '订单数' },
    { key: 'buyers', title: '买家数' },
    { key: 'units_sold', title: '售出件数' },
    { key: 'ctr', title: 'CTR（点击率）' },
    { key: 'cvr', title: 'CVR（转化率）' },
    { key: 'revenue', title: '成交额' },
    { key: 'sales_share', title: '成交占比' },
    { key: 'negative_reviews', title: '负面评价' },
    { key: 'source', title: '来源' }
  ]
}

const TRAFFIC_CATEGORY_TABLE_CONFIG: DataTableConfig = {
  tableKey: 'traffic-analytics.categories.v2',
  primaryColumnKey: 'platform_category_name',
  columns: [
    { key: 'platform_category_name', title: '品类', required: true, fixed: 'left' },
    { key: 'platform_category_id', title: '品类 ID', visible: false },
    { key: 'platform', title: '平台' },
    { key: 'shop_name', title: '店铺' },
    { key: 'region', title: '地区' },
    { key: 'sku_count', title: 'SKU 数' },
    { key: 'impressions', title: '曝光量' },
    { key: 'clicks', title: '点击/访问' },
    { key: 'add_to_cart', title: '加购量' },
    { key: 'orders', title: '订单数' },
    { key: 'buyers', title: '买家数' },
    { key: 'units_sold', title: '售出件数' },
    { key: 'ctr', title: 'CTR（点击率）' },
    { key: 'cart_rate', title: '加购率' },
    { key: 'cvr', title: 'CVR（转化率）' },
    { key: 'revenue', title: '成交额' },
    { key: 'sales_share', title: '成交占比' },
    { key: 'negative_reviews', title: '负面评价' },
    { key: 'period', title: '数据周期' },
    { key: 'source', title: '来源' }
  ]
}

const TRAFFIC_COMPARISON_TABLE_CONFIG: DataTableConfig = {
  tableKey: 'traffic-analytics.comparison',
  primaryColumnKey: 'rank',
  columns: [
    { key: 'rank', title: '排名', required: true, fixed: 'left' },
    { key: 'platform', title: '平台', fixed: 'left' },
    { key: 'shop_name', title: '店铺', fixed: 'left' },
    { key: 'region', title: '地区' },
    { key: 'sku', title: 'SKU' },
    { key: 'product_name', title: '商品名称' },
    { key: 'current_metric', title: '本期' },
    { key: 'previous_metric', title: '上期' },
    { key: 'delta_metric', title: '环比增减' },
    { key: 'delta_rate_metric', title: '环比变化率' },
    { key: 'current_clicks', title: '本期点击' },
    { key: 'current_orders', title: '本期下单' },
    { key: 'source', title: '来源' }
  ]
}

const TRAFFIC_CATEGORY_COMPARISON_TABLE_CONFIG: DataTableConfig = {
  tableKey: 'traffic-analytics.comparison.category',
  primaryColumnKey: 'rank',
  columns: [
    { key: 'rank', title: '排名', required: true, fixed: 'left' },
    { key: 'platform', title: '平台', fixed: 'left' },
    { key: 'shop_name', title: '店铺', fixed: 'left' },
    { key: 'region', title: '地区' },
    { key: 'platform_category_name', title: '品类' },
    { key: 'current_metric', title: '本期' },
    { key: 'previous_metric', title: '上期' },
    { key: 'delta_metric', title: '环比增减' },
    { key: 'delta_rate_metric', title: '环比变化率' },
    { key: 'current_clicks', title: '本期点击' },
    { key: 'current_orders', title: '本期下单' },
    { key: 'source', title: '来源' },
    { key: 'sku_detail', title: 'SKU 明细', required: true, settingsHidden: true, fixed: 'right' }
  ]
}

type DateRangePreset = {
  label: string
  value: [Dayjs, Dayjs]
}

function lastCompleteDay() {
  return dayjs().subtract(1, 'day').startOf('day')
}

function initialRange(): [Dayjs, Dayjs] {
  const end = lastCompleteDay()
  return [end.subtract(6, 'day'), end]
}

function dateRangePresets(): DateRangePreset[] {
  const today = dayjs().startOf('day')
  const end = lastCompleteDay()
  const daysSinceMonday = (today.day() + 6) % 7
  const currentMonday = today.subtract(daysSinceMonday, 'day')
  const previousMonth = today.subtract(1, 'month')

  return [
    { label: '昨日', value: [end, end] },
    { label: '近7日', value: [end.subtract(6, 'day'), end] },
    { label: '近14日', value: [end.subtract(13, 'day'), end] },
    { label: '近30日', value: [end.subtract(29, 'day'), end] },
    { label: '上周', value: [currentMonday.subtract(7, 'day'), currentMonday.subtract(1, 'day')] },
    { label: '上月', value: [previousMonth.startOf('month'), previousMonth.endOf('month').startOf('day')] }
  ]
}

function isSameRange(left: [Dayjs, Dayjs], right: [Dayjs, Dayjs]) {
  return left[0].isSame(right[0], 'day') && left[1].isSame(right[1], 'day')
}

function platformTag(platform: string) {
  return <Tag color={platformColors[platform]}>{platformLabels[platform] || platform}</Tag>
}

function formatInteger(value?: number | null) {
  return value == null ? '--' : numberFormatter.format(value)
}

function formatPercent(value?: number | null) {
  return value == null ? '--' : `${(value * 100).toFixed(2)}%`
}

function formatMoney(value?: number | null, currency?: string) {
  if (value == null) return '--'
  return `${numberFormatter.format(Number(value.toFixed(2)))}${currency ? ` ${currency}` : ''}`
}

function metricCell(value: number | null, coverage?: TrafficCoverage) {
  if (value == null) {
    const missing = <span className="traffic-value--missing">--</span>
    return coverage === 'unavailable' ? <Tooltip title="平台未提供该指标">{missing}</Tooltip> : missing
  }
  const content = <span className="traffic-value">{numberFormatter.format(value)}</span>
  return coverage === 'partial' ? <Tooltip title="部分商品提供该指标">{content}</Tooltip> : content
}

function compareNullableMetric(left?: number | null, right?: number | null) {
  if (left == null && right == null) return 0
  if (left == null) return -1
  if (right == null) return 1
  return left - right
}

function sourceTag(source: string) {
  if (source === 'ads') return <Tag color="orange">广告</Tag>
  if (source === 'platform') return <Tag color="blue">平台全量</Tag>
  return <Tag color="green">自然</Tag>
}

function filterOption(label: ReactNode, checked: boolean) {
  return (
    <Checkbox
      className="traffic-filter-option-checkbox"
      checked={checked}
      tabIndex={-1}
      aria-hidden
      onChange={() => undefined}
    >
      {label}
    </Checkbox>
  )
}

type RegionsByPlatform = Record<string, string[]>

function mergeRegionsByPlatform(current: RegionsByPlatform, rows: TrafficMetricRow[]): RegionsByPlatform {
  const next = new Map(
    Object.entries(current).map(([platform, values]) => [platform, new Set(values)])
  )
  rows.forEach((row) => {
    if (!row.platform || !row.region) return
    const values = next.get(row.platform) || new Set<string>()
    values.add(row.region)
    next.set(row.platform, values)
  })
  return Object.fromEntries(
    Array.from(next, ([platform, values]) => [platform, Array.from(values).sort()])
  )
}

function regionsForPlatforms(regionsByPlatform: RegionsByPlatform, platforms: string[]): string[] {
  const targetPlatforms = platforms.length ? platforms : Object.keys(regionsByPlatform)
  return Array.from(
    new Set(targetPlatforms.flatMap((platform) => regionsByPlatform[platform] || []))
  ).sort()
}

function trafficCategoryKey(row: Pick<TrafficCategoryRow, 'platform' | 'region' | 'platform_category_id'>) {
  return [row.platform, row.region || '', row.platform_category_id].join('\u001f')
}

function trafficComparisonCategoryKey(row: Pick<TrafficComparisonRow, 'platform' | 'platform_account_id' | 'source' | 'grain' | 'region' | 'platform_category_id' | 'platform_category_name' | 'entity_id' | 'sku' | 'product_name' | 'rank'>) {
  const categoryKey = row.platform_category_id || row.entity_id || row.platform_category_name || row.product_name || row.sku || row.rank || ''
  return [
    row.platform,
    row.platform_account_id,
    row.source || '',
    row.grain || '',
    row.region || '',
    categoryKey
  ].join('\u001f')
}

function comparisonSortLabel(sort: TrafficComparisonSort) {
  if (sort === 'rate_desc') return '变化率降序'
  if (sort === 'rate_asc') return '变化率升序'
  if (sort === 'current_desc') return '本期降序'
  if (sort === 'current_asc') return '本期升序'
  if (sort === 'previous_desc') return '上期降序'
  if (sort === 'previous_asc') return '上期升序'
  if (sort === 'delta_desc') return '增减降序'
  if (sort === 'delta_asc') return '增减升序'
  return '环比增减'
}

const comparisonChangeDirectionOptions = [
  { label: '全部变化', value: 'all' },
  { label: '仅上升', value: 'up' },
  { label: '仅下降', value: 'down' },
  { label: '无变化', value: 'flat' }
] satisfies Array<{ label: string; value: TrafficComparisonChangeDirection }>

const emptyCategoryResponse: TrafficCategoryResponse = {
  items: [],
  date_from: '',
  date_to: '',
  total_sku_count: 0,
  categorized_sku_count: 0,
  uncategorized_sku_count: 0,
  classification_rate: 0
}

export function TrafficAnalytics() {
  const { message } = App.useApp()
  const [range, setRange] = useState<[Dayjs, Dayjs]>(initialRange)
  const [platforms, setPlatforms] = useState<string[]>([])
  const [accountIds, setAccountIds] = useState<number[]>([])
  const [source, setSource] = useState('')
  const [regions, setRegions] = useState<string[]>([])
  const [knownRegionsByPlatform, setKnownRegionsByPlatform] = useState<RegionsByPlatform>({})
  const [accounts, setAccounts] = useState<TrafficAccount[]>([])
  const [summary, setSummary] = useState<TrafficMetricRow[]>([])
  const [categoryResult, setCategoryResult] = useState<TrafficCategoryResponse>(emptyCategoryResponse)
  const [categoryKeys, setCategoryKeys] = useState<string[]>([])
  const [includeUncategorized, setIncludeUncategorized] = useState(true)
  const [rankings, setRankings] = useState<TrafficMetricRow[]>([])
  const [comparison, setComparison] = useState<TrafficComparisonRow[]>([])
  const [categorySkuComparisonModalRow, setCategorySkuComparisonModalRow] = useState<TrafficComparisonRow | null>(null)
  const [categorySkuModalMode, setCategorySkuModalMode] = useState<CategorySkuModalMode>('comparison')
  const [categorySkuComparisonRows, setCategorySkuComparisonRows] = useState<TrafficComparisonRow[]>([])
  const [categorySkuFocusRows, setCategorySkuFocusRows] = useState<TrafficSkuFocusRow[]>([])
  const [categorySkuFocusTopN, setCategorySkuFocusTopN] = useState(20)
  const [categorySkuFocusSupportedMetrics, setCategorySkuFocusSupportedMetrics] = useState<TrafficMetricKey[]>([])
  const [categorySkuComparisonLoading, setCategorySkuComparisonLoading] = useState(false)
  const [categorySkuComparisonError, setCategorySkuComparisonError] = useState('')
  const [categorySkuComparisonMetric, setCategorySkuComparisonMetric] = useState<TrafficMetricKey>('impressions')
  const [categorySkuComparisonSort, setCategorySkuComparisonSort] = useState<TrafficComparisonSort>('delta_abs')
  const [categorySkuComparisonKeyword, setCategorySkuComparisonKeyword] = useState('')
  const [categorySkuComparisonChangeDirection, setCategorySkuComparisonChangeDirection] = useState<TrafficComparisonChangeDirection>('all')
  const [comparisonPeriod, setComparisonPeriod] = useState('')
  const [rankMetric, setRankMetric] = useState<TrafficMetricKey>('clicks')
  const [rankRateSort, setRankRateSort] = useState<{ metric: TrafficRateMetricKey; order: TrafficSortOrder } | null>(null)
  const [comparisonMetric, setComparisonMetric] = useState<TrafficMetricKey>('impressions')
  const [comparisonDimension, setComparisonDimension] = useState<TrafficComparisonDimension>('sku')
  const [comparisonSort, setComparisonSort] = useState<TrafficComparisonSort>('delta_abs')
  const [activeTab, setActiveTab] = useState('summary')
  const [settingsTab, setSettingsTab] = useState<string | null>(null)
  const [tableBodyHeight, setTableBodyHeight] = useState(240)
  const [dataLoading, setDataLoading] = useState(true)
  const [dataError, setDataError] = useState('')
  const [periodFallbacks, setPeriodFallbacks] = useState<TrafficPeriodFallback[]>([])
  const [syncing, setSyncing] = useState(false)
  const dataRequestAbortRef = useRef<AbortController | null>(null)
  const categorySkuRequestAbortRef = useRef<AbortController | null>(null)
  const loadedRequestKeysRef = useRef<Record<string, string>>({})
  const accountsRef = useRef<TrafficAccount[]>([])
  const tableSurfaceRef = useRef<HTMLDivElement | null>(null)

  const datePresets = useMemo(
    () => dateRangePresets().map((preset) => {
      const selected = isSameRange(range, preset.value)
      return {
        label: (
          <span
            className={`traffic-date-preset-label${selected ? ' is-selected' : ''}`}
            aria-current={selected ? 'date' : undefined}
          >
            {preset.label}
          </span>
        ),
        value: preset.value
      }
    }),
    [range]
  )

  const filters = useMemo<TrafficFilters>(
    () => ({
      date_from: range[0].format('YYYY-MM-DD'),
      date_to: range[1].format('YYYY-MM-DD'),
      platform: platforms.length ? platforms : undefined,
      platform_account_id: accountIds.length ? accountIds : undefined,
      source: source || undefined,
      region: regions.length ? regions : undefined
    }),
    [accountIds, platforms, range, regions, source]
  )
  const filterRequestKey = useMemo(() => JSON.stringify(filters), [filters])
  const metricAccounts = useMemo(
    () => accounts.filter((account) =>
      (!platforms.length || platforms.includes(account.platform)) &&
      (!accountIds.length || accountIds.includes(account.id))
    ),
    [accountIds, accounts, platforms]
  )
  const supportedMetricKeys = useMemo(
    () => new Set(metricAccounts.flatMap((account) => account.capability.metrics)),
    [metricAccounts]
  )
  const availableRankingMetricOptions = useMemo(
    () => rankingMetricOptions.map((option) => ({
      ...option,
      disabled: supportedMetricKeys.size > 0 && !supportedMetricKeys.has(option.value)
    })),
    [supportedMetricKeys]
  )
  const availableComparisonMetricOptions = useMemo(
    () => comparisonMetricOptions.map((option) => ({
      ...option,
      disabled: supportedMetricKeys.size > 0 && !supportedMetricKeys.has(option.value)
    })),
    [supportedMetricKeys]
  )
  const activeRequestKey = useMemo(() => {
    if (activeTab === 'rankings') {
      const rankingMetric = rankRateSort?.metric || rankMetric
      const rankingOrder = rankRateSort?.order || 'desc'
      return `${activeTab}:${filterRequestKey}:${rankingMetric}:${rankingOrder}`
    }
    if (activeTab === 'comparison') return `${activeTab}:${filterRequestKey}:${comparisonMetric}:${comparisonDimension}:${comparisonSort}`
    return `${activeTab}:${filterRequestKey}`
  }, [activeTab, comparisonDimension, comparisonMetric, comparisonSort, filterRequestKey, rankMetric, rankRateSort])

  const loadAccounts = useCallback(async (background = false) => {
    const response = await listTrafficAccounts({ background, silent: background })
    setAccounts(response.items)
    return response.items
  }, [])

  const loadActiveData = useCallback(async (force = false) => {
    if (!force && loadedRequestKeysRef.current[activeTab] === activeRequestKey) {
      setDataLoading(false)
      return
    }
    dataRequestAbortRef.current?.abort()
    const controller = new AbortController()
    dataRequestAbortRef.current = controller
    setDataLoading(true)
    setDataError('')
    setPeriodFallbacks([])
    try {
      let fallbackPeriods: TrafficPeriodFallback[] = []
      if (activeTab === 'summary') {
        const response = await fetchTrafficSummary(filters, { signal: controller.signal })
        if (controller.signal.aborted) return
        setSummary(response.items)
        fallbackPeriods = response.fallback_periods || []
        setKnownRegionsByPlatform((current) =>
          mergeRegionsByPlatform(current, response.items)
        )
      } else if (activeTab === 'categories') {
        const response = await fetchTrafficCategories(filters, { signal: controller.signal })
        if (controller.signal.aborted) return
        setCategoryResult(response)
        fallbackPeriods = response.fallback_periods || []
        setKnownRegionsByPlatform((current) =>
          mergeRegionsByPlatform(current, response.items)
        )
      } else if (activeTab === 'rankings') {
        const response = await fetchTrafficRankings(
          {
            ...filters,
            metric: rankRateSort?.metric || rankMetric,
            sort_order: rankRateSort?.order || 'desc',
            limit: 20
          },
          { signal: controller.signal }
        )
        if (controller.signal.aborted) return
        setRankings(response.items)
        fallbackPeriods = response.fallback_periods || []
      } else {
        setComparison([])
        setComparisonPeriod('')
        const response = await fetchTrafficComparison(
          { ...filters, metric: comparisonMetric, dimension: comparisonDimension, sort_by: comparisonSort, limit: 20 },
          { signal: controller.signal }
        )
        if (controller.signal.aborted) return
        setComparison(response.items)
        fallbackPeriods = response.fallback_periods || []
        setComparisonPeriod(
          `${response.previous_date_from} 至 ${response.previous_date_to}`
        )
      }
      setPeriodFallbacks(fallbackPeriods)
      loadedRequestKeysRef.current[activeTab] = activeRequestKey
    } catch (error) {
      if (!controller.signal.aborted) {
        setDataError('流量数据加载失败，请点击刷新按钮重试')
        throw error
      }
    } finally {
      if (dataRequestAbortRef.current === controller) {
        setDataLoading(false)
      }
    }
  }, [activeRequestKey, activeTab, comparisonDimension, comparisonMetric, comparisonSort, filters, rankMetric, rankRateSort])

  const reloadTrafficData = useCallback(async () => {
    loadedRequestKeysRef.current = {}
    await loadActiveData(true)
  }, [loadActiveData])

  const loadCategorySkuDetails = useCallback(async (row: TrafficComparisonRow) => {
    const context = resolveCategorySkuComparisonContext(row)
    if (!context) {
      setCategorySkuComparisonError(categorySkuComparisonContextError(row))
      return
    }
    categorySkuRequestAbortRef.current?.abort()
    const controller = new AbortController()
    categorySkuRequestAbortRef.current = controller
    setCategorySkuComparisonLoading(true)
    setCategorySkuComparisonError('')
    try {
      if (categorySkuModalMode === 'focus') {
        const response = await fetchTrafficCategorySkuFocusAnalysis(
          {
            date_from: filters.date_from,
            date_to: filters.date_to,
            top_n: categorySkuFocusTopN,
            keyword: categorySkuComparisonKeyword,
            ...context
          },
          { signal: controller.signal }
        )
        if (controller.signal.aborted) return
        setCategorySkuFocusRows(response.items)
        setCategorySkuFocusSupportedMetrics(response.supported_metrics)
        return
      }
      const response = await fetchTrafficCategorySkuComparison(
        {
          date_from: filters.date_from,
          date_to: filters.date_to,
          metric: categorySkuComparisonMetric,
          sort_by: categorySkuComparisonSort,
          keyword: categorySkuComparisonKeyword,
          change_direction: categorySkuComparisonChangeDirection,
          limit: 20,
          ...context
        },
        { signal: controller.signal }
      )
      if (controller.signal.aborted) return
      setCategorySkuComparisonRows(response.items)
    } catch {
      if (!controller.signal.aborted) {
        setCategorySkuComparisonError('品类 SKU 明细加载失败，请重试')
      }
    } finally {
      if (categorySkuRequestAbortRef.current === controller) {
        categorySkuRequestAbortRef.current = null
        setCategorySkuComparisonLoading(false)
      }
    }
  }, [categorySkuComparisonChangeDirection, categorySkuComparisonKeyword, categorySkuComparisonMetric, categorySkuComparisonSort, categorySkuFocusTopN, categorySkuModalMode, filters.date_from, filters.date_to])

  const openCategorySkuComparison = useCallback((row: TrafficComparisonRow) => {
    if (!resolveCategorySkuComparisonContext(row)) {
      setCategorySkuComparisonError(categorySkuComparisonContextError(row))
      setCategorySkuComparisonModalRow(row)
      return
    }
    setCategorySkuComparisonModalRow(row)
    setCategorySkuModalMode('comparison')
    setCategorySkuComparisonMetric(comparisonMetric)
    setCategorySkuComparisonSort('delta_abs')
    setCategorySkuComparisonKeyword('')
    setCategorySkuComparisonChangeDirection('all')
    setCategorySkuComparisonRows([])
    setCategorySkuFocusRows([])
    setCategorySkuFocusSupportedMetrics([])
    setCategorySkuComparisonError('')
  }, [comparisonMetric])

  const closeCategorySkuComparison = useCallback(() => {
    categorySkuRequestAbortRef.current?.abort()
    categorySkuRequestAbortRef.current = null
    setCategorySkuComparisonModalRow(null)
    setCategorySkuComparisonLoading(false)
  }, [])

  useEffect(() => {
    void loadAccounts()
  }, [loadAccounts])

  useEffect(() => {
    categorySkuRequestAbortRef.current?.abort()
    categorySkuRequestAbortRef.current = null
    setCategorySkuComparisonModalRow(null)
    setCategorySkuComparisonRows([])
    setCategorySkuFocusRows([])
    setCategorySkuFocusSupportedMetrics([])
    setCategorySkuComparisonLoading(false)
    setCategorySkuComparisonError('')
  }, [comparisonDimension, filterRequestKey])

  useEffect(() => () => {
    categorySkuRequestAbortRef.current?.abort()
    categorySkuRequestAbortRef.current = null
  }, [])

  useEffect(() => {
    const row = categorySkuComparisonModalRow
    if (!row) return
    const timer = window.setTimeout(() => {
      void loadCategorySkuDetails(row).catch(() => undefined)
    }, categorySkuComparisonKeyword ? 280 : 0)
    return () => window.clearTimeout(timer)
  }, [categorySkuComparisonChangeDirection, categorySkuComparisonKeyword, categorySkuComparisonMetric, categorySkuComparisonModalRow, categorySkuComparisonSort, categorySkuFocusTopN, categorySkuModalMode, loadCategorySkuDetails])

  useEffect(() => {
    accountsRef.current = accounts
  }, [accounts])

  useEffect(() => {
    if (!supportedMetricKeys.size) return
    if (!supportedMetricKeys.has(rankMetric)) {
      const fallback = supportedMetricKeys.has('clicks') ? 'clicks' : availableRankingMetricOptions.find((option) => !option.disabled)?.value
      if (fallback) setRankMetric(fallback)
    }
    if (!supportedMetricKeys.has(comparisonMetric)) {
      const fallback = supportedMetricKeys.has('orders') ? 'orders' : availableComparisonMetricOptions.find((option) => !option.disabled)?.value
      if (fallback) setComparisonMetric(fallback)
    }
  }, [availableComparisonMetricOptions, availableRankingMetricOptions, comparisonMetric, rankMetric, supportedMetricKeys])

  useEffect(() => {
    if (loadedRequestKeysRef.current[activeTab] === activeRequestKey) {
      setDataLoading(false)
      return
    }
    setDataLoading(true)
    const timer = window.setTimeout(() => {
      void loadActiveData().catch(() => undefined)
    }, 50)
    return () => {
      window.clearTimeout(timer)
      dataRequestAbortRef.current?.abort()
    }
  }, [activeRequestKey, activeTab, loadActiveData])

  const activeSync = accounts.some((account) => ['pending', 'running'].includes(account.latest_run?.status || ''))
  useEffect(() => {
    if (!activeSync) return
    const timer = window.setInterval(async () => {
      const previous = accountsRef.current
      const next = await loadAccounts(true).catch(() => [])
      const previousById = new Map(previous.map((account) => [account.id, account]))
      const dataChanged = next.some((account) => {
        const prior = previousById.get(account.id)
        return Boolean(prior && prior.latest_metric_at !== account.latest_metric_at)
      })
      accountsRef.current = next
      const stillRunning = next.some((account) => ['pending', 'running'].includes(account.latest_run?.status || ''))
      if (dataChanged) {
        await reloadTrafficData().catch(() => undefined)
      }
      if (!stillRunning) {
        window.clearInterval(timer)
        if (!dataChanged) await reloadTrafficData().catch(() => undefined)
      }
    }, 3000)
    return () => window.clearInterval(timer)
  }, [activeSync, loadAccounts, reloadTrafficData])

  const visibleAccounts = useMemo(
    () => accounts.filter((account) => !platforms.length || platforms.includes(account.platform)),
    [accounts, platforms]
  )
  const targetAccounts = useMemo(
    () => accountIds.length
      ? visibleAccounts.filter((account) => accountIds.includes(account.id))
      : visibleAccounts,
    [accountIds, visibleAccounts]
  )
  const latestDataUpdateAt = useMemo(() => {
    return targetAccounts.reduce<string | null>((latest, account) => {
      const value = account.latest_metric_at
      if (!value) return latest
      if (!latest || dayjs(value).isAfter(dayjs(latest))) return value
      return latest
    }, null)
  }, [targetAccounts])
  const activeItemCount = activeTab === 'summary'
    ? summary.length
    : activeTab === 'categories'
      ? categoryResult.items.length
      : activeTab === 'rankings'
        ? rankings.length
        : comparison.length
  const statusAlert = useMemo(() => {
    if (dataError) {
      return { type: 'error' as const, message: '数据加载失败', description: dataError }
    }
    const matchingRun = (account: TrafficAccount) => {
      const run = account.latest_run
      return run && run.date_from === filters.date_from && run.date_to === filters.date_to ? run : null
    }
    const failedAccounts = targetAccounts.filter((account) => matchingRun(account)?.status === 'failed')
    const timedOutAccounts = targetAccounts.filter((account) => matchingRun(account)?.status === 'timed_out')
    const runningAccounts = targetAccounts.filter((account) => ['pending', 'running'].includes(matchingRun(account)?.status || ''))
    const partialAccounts = targetAccounts.filter((account) => matchingRun(account)?.status === 'partial_success')
    const fallbackEntries = new Map(
      periodFallbacks.map((fallback) => {
        const account = accounts.find((item) => item.id === fallback.platform_account_id)
        const platform = platformLabels[fallback.platform] || fallback.platform
        const scope = fallback.scope === 'previous' ? '上期' : '本期'
        const label = `${platform}${account ? ` / ${account.display_name}` : ''} ${scope} ${fallback.actual_date_from} 至 ${fallback.actual_date_to}`
        return [`${fallback.platform_account_id}-${fallback.scope}-${fallback.actual_date_from}-${fallback.actual_date_to}`, label]
      })
    )
    const fallbackText = Array.from(fallbackEntries.values()).join('；')
    if (failedAccounts.length || timedOutAccounts.length) {
      const problemAccounts = [...failedAccounts, ...timedOutAccounts]
      const names = problemAccounts.map((account) => `${platformLabels[account.platform] || account.platform} / ${account.display_name}`).join('、')
      const reasons = problemAccounts
        .map((account) => matchingRun(account)?.error_message)
        .filter(Boolean)
        .join('；')
      return {
        type: failedAccounts.length ? 'error' as const : 'warning' as const,
        message: failedAccounts.length && timedOutAccounts.length
          ? `${names} 同步失败或超时`
          : `${names} ${failedAccounts.length ? '同步失败' : '同步超时'}`,
        description: [
          reasons,
          fallbackText ? `当前继续显示最新可用数据：${fallbackText}` : '',
          timedOutAccounts.length ? '已结束超时店铺任务，其他店铺继续同步' : '其他店铺继续同步'
        ]
          .filter(Boolean)
          .join('。')
      }
    }
    if (runningAccounts.length) {
      return {
        type: 'info' as const,
        message: '流量数据正在同步',
        description: fallbackText ? `已完成的平台会自动刷新，当前暂显示：${fallbackText}` : '已完成的平台会自动刷新'
      }
    }
    if (partialAccounts.length) {
      const details = partialAccounts
        .map((account) => matchingRun(account)?.error_message)
        .filter(Boolean)
        .join('；')
      return {
        type: 'warning' as const,
        message: '部分站点数据未完整同步',
        description: `${details || '已保留成功站点的数据'}。系统将按计划自动重试缺失数据`
      }
    }
    if (!dataLoading && activeTab === 'summary' && activeItemCount === 0 && targetAccounts.length) {
      const completed = targetAccounts.some((account) => matchingRun(account)?.status === 'success')
      return completed
        ? {
            type: 'info' as const,
            message: '当前周期无平台流量数据',
            description: '同步已完成，但平台没有返回符合当前筛选条件的数据'
          }
        : {
            type: 'info' as const,
            message: '当前周期尚未同步',
            description: '点击右上角同步按钮获取所选周期的数据'
          }
    }
    return null
  }, [accounts, activeItemCount, activeTab, dataError, dataLoading, filters.date_from, filters.date_to, periodFallbacks, targetAccounts])
  const availableRegions = useMemo(
    () => regionsForPlatforms(knownRegionsByPlatform, platforms),
    [knownRegionsByPlatform, platforms]
  )
  const regionOptions = useMemo(
    () => availableRegions.map((value) => ({ label: value, value })),
    [availableRegions]
  )
  const categoryOptions = useMemo(() => {
    const options = new Map<string, { value: string; label: string }>()
    categoryResult.items.forEach((row) => {
      if (!row.categorized || !row.platform_category_id) return
      const value = trafficCategoryKey(row)
      const context = [platformLabels[row.platform] || row.platform, row.region || '全部地区']
      const name = row.platform_category_name || row.platform_category_id
      options.set(value, { value, label: `${context.join(' / ')} / ${name}` })
    })
    return Array.from(options.values()).sort((left, right) => left.label.localeCompare(right.label, 'zh-CN'))
  }, [categoryResult.items])
  const visibleCategoryRows = useMemo(() => {
    const rows = categoryResult.items.filter((row) => {
      if (!includeUncategorized && !row.categorized) return false
      return !categoryKeys.length || categoryKeys.includes(trafficCategoryKey(row))
    })
    if (platforms.length) return rows
    return [...rows].sort((left, right) => (
      compareNullableMetric(right.impressions, left.impressions)
      || compareNullableMetric(right.clicks, left.clicks)
      || left.platform.localeCompare(right.platform)
      || left.platform_category_name.localeCompare(right.platform_category_name, 'zh-CN')
    ))
  }, [categoryKeys, categoryResult.items, includeUncategorized, platforms.length])
  const orderedRankings = useMemo(
    () => [...rankings].sort((left, right) => (left.rank || 0) - (right.rank || 0)),
    [rankings]
  )

  useEffect(() => {
    const availableKeys = new Set(categoryOptions.map((option) => option.value))
    setCategoryKeys((current) => current.filter((key) => availableKeys.has(key)))
  }, [categoryOptions])

  useLayoutEffect(() => {
    const updateTableHeight = () => {
      const surface = tableSurfaceRef.current
      const pane = surface?.querySelector<HTMLElement>('.ant-tabs-tabpane-active')
      const body = pane?.querySelector<HTMLElement>('.ant-table-body')
      if (!surface || !pane || !body) return

      const dataRow = body.querySelector<HTMLElement>(
        '.ant-table-tbody > tr:not(.ant-table-measure-row)'
      )
      const rowHeight = dataRow?.getBoundingClientRect().height || 0
      const table = body.closest<HTMLElement>('.ant-table')
      const tableStyle = table ? window.getComputedStyle(table) : null
      const customScrollbarReserve = Number.parseFloat(
        tableStyle?.paddingBottom || '0'
      )
      const bodyStyle = window.getComputedStyle(body)
      const nativeScrollbarReserve = Math.max(
        0,
        body.offsetHeight -
          body.clientHeight -
          Number.parseFloat(bodyStyle.borderTopWidth || '0') -
          Number.parseFloat(bodyStyle.borderBottomWidth || '0')
      )
      const pagination = pane.querySelector<HTMLElement>('.ant-pagination')
      const paginationStyle = pagination ? window.getComputedStyle(pagination) : null
      const paginationReserve = pagination
        ? pagination.getBoundingClientRect().height +
          Number.parseFloat(paginationStyle?.marginTop || '0') +
          Number.parseFloat(paginationStyle?.marginBottom || '0')
        : 0
      const surfaceStyle = window.getComputedStyle(surface)
      const surfaceBottomInset =
        Number.parseFloat(surfaceStyle.paddingBottom || '0') +
        Number.parseFloat(surfaceStyle.borderBottomWidth || '0')
      const available = Math.floor(
        window.innerHeight - 8 - body.getBoundingClientRect().top - paginationReserve - surfaceBottomInset
      )
      const nextHeight = fitTableBodyHeightToRows(
        available,
        rowHeight,
        customScrollbarReserve + nativeScrollbarReserve
      )
      setTableBodyHeight((current) => (Math.abs(current - nextHeight) > 2 ? nextHeight : current))
    }

    const frame = window.requestAnimationFrame(updateTableHeight)
    window.addEventListener('resize', updateTableHeight)
    const observer = new ResizeObserver(updateTableHeight)
    if (tableSurfaceRef.current) observer.observe(tableSurfaceRef.current)
    return () => {
      window.cancelAnimationFrame(frame)
      window.removeEventListener('resize', updateTableHeight)
      observer.disconnect()
    }
  }, [activeTab, comparison.length, dataLoading, rankings.length, summary.length, visibleCategoryRows.length])

  const startSync = useCallback(
    async (ids?: number[]) => {
      setSyncing(true)
      try {
        if (range[1].diff(range[0], 'day') + 1 > 31) {
          message.warning('单次同步最多支持31天，请缩小日期范围后再同步')
          return
        }
        const targetIds = ids || (accountIds.length ? accountIds : visibleAccounts.filter((item) => item.enabled).map((item) => item.id))
        if (!targetIds.length) {
          message.warning('当前筛选条件没有可同步店铺')
          return
        }
        const response = await syncTrafficAnalytics({
          platform_account_ids: targetIds,
          date_from: filters.date_from,
          date_to: filters.date_to
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
    [accountIds, filters.date_from, filters.date_to, message, range, visibleAccounts]
  )

  const summaryColumns = useMemo<ColumnsType<TrafficMetricRow>>(
    () => [
      { title: '平台', dataIndex: 'platform', key: 'platform', width: 132, fixed: 'left', render: platformTag },
      { title: '店铺', dataIndex: 'shop_name', key: 'shop_name', width: 170, fixed: 'left', ellipsis: true },
      { title: '地区', dataIndex: 'region', key: 'region', width: 92, render: (value) => value || '全部' },
      {
        title: '曝光量', dataIndex: 'impressions', key: 'impressions', width: 116, align: 'right',
        sorter: { compare: (a, b) => compareNullableMetric(a.impressions, b.impressions), multiple: 3 },
        defaultSortOrder: 'descend',
        render: (value, row) => metricCell(value, row.coverage?.impressions)
      },
      {
        title: '点击/访问', dataIndex: 'clicks', key: 'clicks', width: 116, align: 'right',
        sorter: { compare: (a, b) => compareNullableMetric(a.clicks, b.clicks), multiple: 2 },
        defaultSortOrder: 'descend',
        render: (value, row) => metricCell(value, row.coverage?.clicks)
      },
      {
        title: '加购量', dataIndex: 'add_to_cart', key: 'add_to_cart', width: 108, align: 'right', sorter: (a, b) => (a.add_to_cart || 0) - (b.add_to_cart || 0),
        render: (value, row) => metricCell(value, row.coverage?.add_to_cart)
      },
      {
        title: '订单数', dataIndex: 'orders', key: 'orders', width: 108, align: 'right',
        sorter: { compare: (a, b) => compareNullableMetric(a.orders, b.orders), multiple: 1 },
        defaultSortOrder: 'descend',
        render: (value, row) => metricCell(value, row.coverage?.orders)
      },
      { title: '买家数', dataIndex: 'buyers', key: 'buyers', width: 104, align: 'right', render: (value, row) => metricCell(value, row.coverage?.buyers) },
      { title: '售出件数', dataIndex: 'units_sold', key: 'units_sold', width: 112, align: 'right', render: (value, row) => metricCell(value, row.coverage?.units_sold) },
      {
        title: 'CTR（点击率）', dataIndex: 'ctr', key: 'ctr', width: 132, align: 'right',
        sorter: (a, b, order) => compareNullableTableMetric(a.ctr, b.ctr, order),
        render: formatPercent
      },
      { title: '加购率', dataIndex: 'cart_rate', key: 'cart_rate', width: 92, align: 'right', render: formatPercent },
      {
        title: 'CVR（转化率）', dataIndex: 'cvr', key: 'cvr', width: 132, align: 'right',
        sorter: (a, b, order) => compareNullableTableMetric(a.cvr, b.cvr, order),
        render: formatPercent
      },
      { title: '成交额', dataIndex: 'revenue', key: 'revenue', width: 142, align: 'right', render: (value, row) => formatMoney(value, row.currency) },
      { title: '负面评价', dataIndex: 'negative_reviews', key: 'negative_reviews', width: 112, align: 'right', render: (value, row) => metricCell(value, row.coverage?.negative_reviews) },
      { title: '数据周期', key: 'period', width: 196, render: (_, row) => `${row.period_start} 至 ${row.period_end}` },
      { title: '同步时间', dataIndex: 'synced_at', key: 'synced_at', width: 166, render: (value) => formatTime(value) },
      { title: '来源', dataIndex: 'source', key: 'source', width: 88, render: sourceTag }
    ],
    []
  )

  const categoryColumns = useMemo<DataTableColumnsType<TrafficCategoryRow>>(
    () => [
      {
        title: '品类', dataIndex: 'platform_category_name', key: 'platform_category_name',
        minWidth: 168, maxWidth: 300, flex: 2, fixed: 'left',
        sorter: (a, b) => a.platform_category_name.localeCompare(b.platform_category_name, 'zh-CN'),
        render: (value, row) => row.categorized
          ? <span className="traffic-category-name">{value || row.platform_category_id}</span>
          : <Tag>未归类</Tag>
      },
      {
        title: '品类 ID', dataIndex: 'platform_category_id', key: 'platform_category_id',
        minWidth: 150, maxWidth: 240,
        render: (value) => value ? <span className="traffic-category-id">{value}</span> : '--'
      },
      { title: '平台', dataIndex: 'platform', key: 'platform', minWidth: 120, maxWidth: 150, render: platformTag },
      { title: '店铺', dataIndex: 'shop_name', key: 'shop_name', minWidth: 150, maxWidth: 240, flex: 1, ellipsis: true },
      { title: '地区', dataIndex: 'region', key: 'region', minWidth: 92, maxWidth: 160, render: (value) => value || '全部' },
      { title: 'SKU 数', dataIndex: 'sku_count', key: 'sku_count', minWidth: 92, maxWidth: 112, align: 'right', sorter: (a, b) => a.sku_count - b.sku_count, render: formatInteger },
      {
        title: '曝光量', dataIndex: 'impressions', key: 'impressions', minWidth: 108, maxWidth: 132, align: 'right',
        sorter: platforms.length
          ? (a, b) => compareNullableMetric(a.impressions, b.impressions)
          : { compare: (a, b) => compareNullableMetric(a.impressions, b.impressions), multiple: 2 },
        defaultSortOrder: platforms.length ? undefined : 'descend',
        render: (value, row) => metricCell(value, row.coverage?.impressions)
      },
      {
        title: '点击/访问', dataIndex: 'clicks', key: 'clicks', minWidth: 108, maxWidth: 132, align: 'right',
        sorter: platforms.length
          ? (a, b) => compareNullableMetric(a.clicks, b.clicks)
          : { compare: (a, b) => compareNullableMetric(a.clicks, b.clicks), multiple: 1 },
        defaultSortOrder: 'descend',
        render: (value, row) => metricCell(value, row.coverage?.clicks)
      },
      {
        title: '加购量', dataIndex: 'add_to_cart', key: 'add_to_cart', minWidth: 96, maxWidth: 116, align: 'right',
        sorter: (a, b) => compareNullableMetric(a.add_to_cart, b.add_to_cart),
        render: (value, row) => metricCell(value, row.coverage?.add_to_cart)
      },
      {
        title: '订单数', dataIndex: 'orders', key: 'orders', minWidth: 96, maxWidth: 116, align: 'right',
        sorter: (a, b) => compareNullableMetric(a.orders, b.orders),
        render: (value, row) => metricCell(value, row.coverage?.orders)
      },
      { title: '买家数', dataIndex: 'buyers', key: 'buyers', minWidth: 96, maxWidth: 116, align: 'right', render: (value, row) => metricCell(value, row.coverage?.buyers) },
      { title: '售出件数', dataIndex: 'units_sold', key: 'units_sold', minWidth: 104, maxWidth: 124, align: 'right', render: (value, row) => metricCell(value, row.coverage?.units_sold) },
      {
        title: 'CTR（点击率）', dataIndex: 'ctr', key: 'ctr', minWidth: 124, maxWidth: 144, align: 'right',
        sorter: (a, b, order) => compareNullableTableMetric(a.ctr, b.ctr, order),
        render: formatPercent
      },
      { title: '加购率', dataIndex: 'cart_rate', key: 'cart_rate', minWidth: 92, maxWidth: 112, align: 'right', render: formatPercent },
      {
        title: 'CVR（转化率）', dataIndex: 'cvr', key: 'cvr', minWidth: 124, maxWidth: 144, align: 'right',
        sorter: (a, b, order) => compareNullableTableMetric(a.cvr, b.cvr, order),
        render: formatPercent
      },
      {
        title: '成交额', dataIndex: 'revenue', key: 'revenue', minWidth: 132, maxWidth: 176, align: 'right',
        sorter: (a, b) => compareNullableMetric(a.revenue, b.revenue),
        render: (value, row) => row.currency === 'MIXED' ? <Tooltip title="包含多个币种，无法合计">--</Tooltip> : formatMoney(value, row.currency)
      },
      { title: '成交占比', dataIndex: 'sales_share', key: 'sales_share', minWidth: 104, maxWidth: 124, align: 'right', render: formatPercent },
      { title: '负面评价', dataIndex: 'negative_reviews', key: 'negative_reviews', minWidth: 104, maxWidth: 124, align: 'right', render: (value, row) => metricCell(value, row.coverage?.negative_reviews) },
      { title: '数据周期', key: 'period', minWidth: 188, maxWidth: 220, render: (_, row) => `${row.period_start} 至 ${row.period_end}` },
      { title: '来源', dataIndex: 'source', key: 'source', minWidth: 88, maxWidth: 112, render: sourceTag }
    ],
    [platforms.length]
  )

  const rankingColumns = useMemo<ColumnsType<TrafficMetricRow>>(
    () => [
      { title: '综合排名', dataIndex: 'rank', key: 'rank', width: 88, fixed: 'left', align: 'center' },
      { title: '平台', dataIndex: 'platform', key: 'platform', width: 128, fixed: 'left', render: platformTag },
      { title: '店铺', dataIndex: 'shop_name', key: 'shop_name', width: 160, ellipsis: true },
      { title: '地区', dataIndex: 'region', key: 'region', width: 90, render: (value) => value || '全部' },
      { title: 'SKU', dataIndex: 'sku', key: 'sku', width: 190, ellipsis: true, render: (value) => value || '--' },
      { title: '商品名称', dataIndex: 'product_name', key: 'product_name', width: 280, ellipsis: true },
      { title: '曝光量', dataIndex: 'impressions', key: 'impressions', width: 112, align: 'right', render: formatInteger },
      { title: '点击/访问', dataIndex: 'clicks', key: 'clicks', width: 112, align: 'right', render: formatInteger },
      { title: '加购量', dataIndex: 'add_to_cart', key: 'add_to_cart', width: 104, align: 'right', render: formatInteger },
      { title: '订单数', dataIndex: 'orders', key: 'orders', width: 104, align: 'right', render: formatInteger },
      { title: '买家数', dataIndex: 'buyers', key: 'buyers', width: 104, align: 'right', render: formatInteger },
      { title: '售出件数', dataIndex: 'units_sold', key: 'units_sold', width: 112, align: 'right', render: formatInteger },
      {
        title: 'CTR（点击率）', dataIndex: 'ctr', key: 'ctr', width: 132, align: 'right',
        sorter: true,
        sortOrder: rankRateSort?.metric === 'ctr' ? (rankRateSort.order === 'desc' ? 'descend' : 'ascend') : null,
        sortDirections: ['descend', 'ascend'],
        render: formatPercent
      },
      {
        title: 'CVR（转化率）', dataIndex: 'cvr', key: 'cvr', width: 132, align: 'right',
        sorter: true,
        sortOrder: rankRateSort?.metric === 'cvr' ? (rankRateSort.order === 'desc' ? 'descend' : 'ascend') : null,
        sortDirections: ['descend', 'ascend'],
        render: formatPercent
      },
      { title: '成交额', dataIndex: 'revenue', key: 'revenue', width: 142, align: 'right', render: (value, row) => formatMoney(value, row.currency) },
      { title: '成交占比', dataIndex: 'sales_share', key: 'sales_share', width: 112, align: 'right', render: formatPercent },
      { title: '负面评价', dataIndex: 'negative_reviews', key: 'negative_reviews', width: 112, align: 'right', render: formatInteger },
      { title: '来源', dataIndex: 'source', key: 'source', width: 88, render: sourceTag }
    ],
    [rankRateSort]
  )

  const handleRankingTableChange: NonNullable<TableProps<TrafficMetricRow>['onChange']> = useCallback(
    (_pagination, _filters, sorter, extra) => {
      if (extra.action !== 'sort') return
      const activeSorter = Array.isArray(sorter)
        ? sorter.find((item) => item.order) || sorter[0]
        : sorter
      const nextSort = rankingRateSortFromTable(activeSorter)
      if (nextSort !== undefined) setRankRateSort(nextSort)
    },
    []
  )

  const handleComparisonTableChange: NonNullable<TableProps<TrafficComparisonRow>['onChange']> = useCallback(
    (_pagination, _filters, sorter, extra) => {
      if (extra.action !== 'sort') return
      const activeSorter = Array.isArray(sorter)
        ? sorter.find((item) => item.order) || sorter[0]
        : sorter
      const nextSort = comparisonSortFromTable(activeSorter)
      if (nextSort) setComparisonSort(nextSort)
    },
    []
  )

  const handleCategorySkuComparisonTableChange: NonNullable<TableProps<TrafficComparisonRow>['onChange']> = useCallback(
    (_pagination, _filters, sorter, extra) => {
      if (extra.action !== 'sort') return
      const activeSorter = Array.isArray(sorter)
        ? sorter.find((item) => item.order) || sorter[0]
        : sorter
      const nextSort = categorySkuSortFromTable(activeSorter)
      if (nextSort) setCategorySkuComparisonSort(nextSort)
    },
    []
  )

  const categorySkuComparisonColumns = useMemo<ColumnsType<TrafficComparisonRow>>(() => {
    const metricLabel = comparisonMetricLabels[categorySkuComparisonMetric]
    const currentKey = `current_${categorySkuComparisonMetric}` as keyof TrafficComparisonRow
    const previousKey = `previous_${categorySkuComparisonMetric}` as keyof TrafficComparisonRow
    const deltaKey = `delta_${categorySkuComparisonMetric}` as keyof TrafficComparisonRow
    const rateKey = `delta_rate_${categorySkuComparisonMetric}` as keyof TrafficComparisonRow
    const contextColumns: ColumnsType<TrafficComparisonRow> = []
    if (categorySkuComparisonMetric !== 'clicks') {
      contextColumns.push({ title: '本期点击', dataIndex: 'current_clicks', key: 'current_clicks', width: 100, align: 'right', render: formatInteger })
    }
    if (categorySkuComparisonMetric !== 'orders') {
      contextColumns.push({ title: '本期下单', dataIndex: 'current_orders', key: 'current_orders', width: 100, align: 'right', render: formatInteger })
    }
    return [
      { title: '排名', dataIndex: 'rank', key: 'rank', width: 64, fixed: 'left', align: 'center' },
      { title: 'SKU', dataIndex: 'sku', key: 'sku', width: 200, fixed: 'left', ellipsis: true, render: (value) => value || '--' },
      { title: '商品名称', dataIndex: 'product_name', key: 'product_name', width: 300, ellipsis: true },
      {
        title: `本期${metricLabel}`, key: 'current_metric', width: 112, align: 'right', sorter: true,
        sortOrder: categorySkuComparisonSort === 'current_desc' ? 'descend' : categorySkuComparisonSort === 'current_asc' ? 'ascend' : null,
        sortDirections: ['descend', 'ascend'],
        render: (_, row) => formatInteger(row[currentKey] as number | null)
      },
      {
        title: `上期${metricLabel}`, key: 'previous_metric', width: 112, align: 'right', sorter: true,
        sortOrder: categorySkuComparisonSort === 'previous_desc' ? 'descend' : categorySkuComparisonSort === 'previous_asc' ? 'ascend' : null,
        sortDirections: ['descend', 'ascend'],
        render: (_, row) => formatInteger(row[previousKey] as number | null)
      },
      {
        title: `${metricLabel}增减`, key: 'delta_metric', width: 112, align: 'right',
        sorter: true,
        sortOrder: categorySkuComparisonSort === 'delta_desc' ? 'descend' : categorySkuComparisonSort === 'delta_asc' ? 'ascend' : null,
        sortDirections: ['descend', 'ascend'],
        render: (_, row) => {
          const value = row[deltaKey] as number | null
          if (value == null) return '--'
          return <span className={value > 0 ? 'traffic-delta is-up' : value < 0 ? 'traffic-delta is-down' : 'traffic-delta'}>{value > 0 ? '+' : ''}{formatInteger(value)}</span>
        }
      },
      {
        title: `${metricLabel}变化率`, key: 'delta_rate_metric', width: 112, align: 'right',
        sorter: true,
        sortOrder: categorySkuComparisonSort === 'rate_desc' ? 'descend' : categorySkuComparisonSort === 'rate_asc' ? 'ascend' : null,
        sortDirections: ['descend', 'ascend'],
        render: (_, row) => {
          const value = row[rateKey] as number | null
          if (value == null) return '--'
          return <span className={value > 0 ? 'traffic-delta is-up' : value < 0 ? 'traffic-delta is-down' : 'traffic-delta'}>{value > 0 ? '+' : ''}{formatPercent(value)}</span>
        }
      },
      ...contextColumns
    ]
  }, [categorySkuComparisonMetric, categorySkuComparisonSort])

  const categorySkuFocusColumns = useMemo<ColumnsType<TrafficSkuFocusRow>>(() => [
    { title: '优先级', dataIndex: 'rank', key: 'rank', width: 70, fixed: 'left', align: 'center' },
    {
      title: '命中规则',
      dataIndex: 'focus_reasons',
      key: 'focus_reasons',
      width: 250,
      fixed: 'left',
      render: (reasons: TrafficSkuFocusReason[]) => (
        <div className="traffic-category-sku-focus-reasons">
          {reasons.map((reason) => (
            <Tooltip key={reason} title={focusReasonDescription(reason, categorySkuFocusTopN)}>
              <Tag color={focusReasonMeta[reason].color}>{focusReasonMeta[reason].label}</Tag>
            </Tooltip>
          ))}
        </div>
      )
    },
    { title: 'SKU', dataIndex: 'sku', key: 'sku', width: 190, fixed: 'left', ellipsis: true, render: (value) => value || '--' },
    { title: '商品名称', dataIndex: 'product_name', key: 'product_name', width: 260, ellipsis: true, render: (value) => value || '--' },
    { title: '曝光', dataIndex: 'impressions', key: 'impressions', width: 90, align: 'right', render: formatInteger },
    { title: '点击', dataIndex: 'clicks', key: 'clicks', width: 90, align: 'right', render: formatInteger },
    { title: '加购', dataIndex: 'add_to_cart', key: 'add_to_cart', width: 90, align: 'right', render: formatInteger },
    { title: '下单', dataIndex: 'orders', key: 'orders', width: 90, align: 'right', render: formatInteger },
    { title: '曝光排名', dataIndex: 'impressions_rank', key: 'impressions_rank', width: 90, align: 'center', render: (value) => value == null ? '--' : `#${value}` },
    { title: '点击排名', dataIndex: 'clicks_rank', key: 'clicks_rank', width: 90, align: 'center', render: (value) => value == null ? '--' : `#${value}` },
    { title: '加购排名', dataIndex: 'add_to_cart_rank', key: 'add_to_cart_rank', width: 90, align: 'center', render: (value) => value == null ? '--' : `#${value}` },
    { title: '下单排名', dataIndex: 'orders_rank', key: 'orders_rank', width: 90, align: 'center', render: (value) => value == null ? '--' : `#${value}` }
  ], [categorySkuFocusTopN])

  const categorySkuFocusUnavailableMetrics = useMemo(
    () => focusMetricKeys.filter((metric) => !categorySkuFocusSupportedMetrics.includes(metric)),
    [categorySkuFocusSupportedMetrics]
  )

  const comparisonColumns = useMemo<ColumnsType<TrafficComparisonRow>>(() => {
    const currentKey = `current_${comparisonMetric}` as keyof TrafficComparisonRow
    const previousKey = `previous_${comparisonMetric}` as keyof TrafficComparisonRow
    const deltaKey = `delta_${comparisonMetric}` as keyof TrafficComparisonRow
    const rateKey = `delta_rate_${comparisonMetric}` as keyof TrafficComparisonRow
    const identityColumns: ColumnsType<TrafficComparisonRow> = [
      { title: '排名', dataIndex: 'rank', key: 'rank', width: 72, fixed: 'left', align: 'center' },
      { title: '平台', dataIndex: 'platform', key: 'platform', width: 128, fixed: 'left', render: platformTag },
      { title: '店铺', dataIndex: 'shop_name', key: 'shop_name', width: 160, fixed: 'left', ellipsis: true },
      { title: '地区', dataIndex: 'region', key: 'region', width: 90, render: (value) => value || '全部' }
    ]
    if (comparisonDimension === 'category') {
      identityColumns.push({
        title: '品类',
        dataIndex: 'platform_category_name',
        key: 'platform_category_name',
        width: 470,
        ellipsis: true,
        render: (value, row) => value || row.platform_category_id || '未归类'
      })
    } else {
      identityColumns.push(
        { title: 'SKU', dataIndex: 'sku', key: 'sku', width: 190, ellipsis: true },
        { title: '商品名称', dataIndex: 'product_name', key: 'product_name', width: 280, ellipsis: true }
      )
    }
    return [
      ...identityColumns,
      {
        title: '本期', key: 'current_metric', width: 116, align: 'right', sorter: true,
        sortOrder: comparisonSort === 'current_desc' ? 'descend' : comparisonSort === 'current_asc' ? 'ascend' : null,
        sortDirections: ['descend', 'ascend'],
        render: (_, row) => formatInteger(row[currentKey] as number | null)
      },
      {
        title: '上期', key: 'previous_metric', width: 116, align: 'right', sorter: true,
        sortOrder: comparisonSort === 'previous_desc' ? 'descend' : comparisonSort === 'previous_asc' ? 'ascend' : null,
        sortDirections: ['descend', 'ascend'],
        render: (_, row) => formatInteger(row[previousKey] as number | null)
      },
      {
        title: '环比增减', key: 'delta_metric', width: 116, align: 'right',
        sorter: true,
        sortOrder: comparisonSort === 'delta_desc' ? 'descend' : comparisonSort === 'delta_asc' ? 'ascend' : null,
        sortDirections: ['descend', 'ascend'],
        render: (_, row) => {
          const value = row[deltaKey] as number | null
          if (value == null) return '--'
          return <span className={value > 0 ? 'traffic-delta is-up' : value < 0 ? 'traffic-delta is-down' : 'traffic-delta'}>{value > 0 ? '+' : ''}{formatInteger(value)}</span>
        }
      },
      {
        title: '环比变化率', key: 'delta_rate_metric', width: 104, align: 'right',
        sorter: true,
        sortOrder: comparisonSort === 'rate_desc' ? 'descend' : comparisonSort === 'rate_asc' ? 'ascend' : null,
        sortDirections: ['descend', 'ascend'],
        render: (_, row) => {
          const value = row[rateKey] as number | null
          if (value == null) return '--'
          return <span className={value > 0 ? 'traffic-delta is-up' : value < 0 ? 'traffic-delta is-down' : 'traffic-delta'}>{value > 0 ? '+' : ''}{formatPercent(value)}</span>
        }
      },
      { title: '本期点击', dataIndex: 'current_clicks', key: 'current_clicks', width: 110, align: 'right', render: formatInteger },
      { title: '本期下单', dataIndex: 'current_orders', key: 'current_orders', width: 110, align: 'right', render: formatInteger },
      { title: '来源', dataIndex: 'source', key: 'source', width: 88, render: sourceTag },
      ...(comparisonDimension === 'category' ? [{
        title: '明细',
        key: 'sku_detail',
        width: 64,
        fixed: 'right' as const,
        align: 'center' as const,
        render: (_value: unknown, row: TrafficComparisonRow) => (
          <Tooltip title="查看品类 SKU 明细">
            <Button
              type="text"
              size="small"
              icon={<EyeOutlined />}
              aria-label={`查看${row.platform_category_name || row.platform_category_id || '未归类'} SKU 明细`}
              aria-haspopup="dialog"
              onClick={(event) => {
                event.stopPropagation()
                openCategorySkuComparison(row)
              }}
            />
          </Tooltip>
        )
      }] : [])
    ]
  }, [comparisonDimension, comparisonMetric, comparisonSort, openCategorySkuComparison])

  const categorySkuComparisonModal = categorySkuComparisonModalRow ? (
    <Modal
      open
      title={`${categorySkuComparisonModalRow.platform_category_name || categorySkuComparisonModalRow.platform_category_id || '品类'} · SKU 分析`}
      width={1360}
      centered
      destroyOnHidden
      className="traffic-category-sku-modal"
      onCancel={closeCategorySkuComparison}
      footer={null}
    >
      <div className="traffic-category-sku-modal__context" aria-label="品类明细上下文">
        <Tag color={platformColors[categorySkuComparisonModalRow.platform]}>{platformLabels[categorySkuComparisonModalRow.platform] || categorySkuComparisonModalRow.platform}</Tag>
        <Tag>{categorySkuComparisonModalRow.shop_name || '全部店铺'}</Tag>
        <Tag>{categorySkuComparisonModalRow.region || '全部地区'}</Tag>
        <Tag>{categorySkuComparisonModalRow.source === 'ads' ? '广告流量' : categorySkuComparisonModalRow.source === 'platform' ? '平台全量' : '自然流量'}</Tag>
        <span>当前期：{filters.date_from} 至 {filters.date_to}</span>
        <span>对比期：{comparisonPeriod || '--'}</span>
      </div>
      <div className="traffic-category-sku-modal__filters" role="group" aria-label="SKU 明细筛选条件">
        <div className="traffic-category-sku-modal__filter">
          <span className="traffic-filter-label">分析</span>
          <Segmented<CategorySkuModalMode>
            value={categorySkuModalMode}
            options={categorySkuModalModeOptions}
            onChange={setCategorySkuModalMode}
          />
        </div>
        {categorySkuModalMode === 'comparison' ? (
          <div className="traffic-category-sku-modal__filter">
            <span className="traffic-filter-label">指标</span>
            <Segmented<TrafficMetricKey>
              value={categorySkuComparisonMetric}
              options={availableComparisonMetricOptions}
              onChange={setCategorySkuComparisonMetric}
            />
          </div>
        ) : (
          <div className="traffic-category-sku-modal__filter traffic-category-sku-modal__filter--top-n">
            <span className="traffic-filter-label">Top N</span>
            <InputNumber
              min={1}
              max={100}
              step={5}
              precision={0}
              value={categorySkuFocusTopN}
              onChange={(value) => {
                if (value != null) setCategorySkuFocusTopN(value)
              }}
            />
          </div>
        )}
        <div className="traffic-category-sku-modal__filter traffic-category-sku-modal__filter--keyword">
          <span className="traffic-filter-label">关键词</span>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="输入 SKU 或商品名称"
            value={categorySkuComparisonKeyword}
            onChange={(event) => setCategorySkuComparisonKeyword(event.target.value)}
            onPressEnter={() => {
              if (categorySkuComparisonModalRow) void loadCategorySkuDetails(categorySkuComparisonModalRow)
            }}
          />
        </div>
        {categorySkuModalMode === 'comparison' ? (
          <div className="traffic-category-sku-modal__filter">
            <span className="traffic-filter-label">变化</span>
            <Select<TrafficComparisonChangeDirection>
              value={categorySkuComparisonChangeDirection}
              options={comparisonChangeDirectionOptions}
              onChange={setCategorySkuComparisonChangeDirection}
              suffixIcon={<FilterOutlined />}
            />
          </div>
        ) : null}
      </div>
      {categorySkuComparisonError ? (
        <Alert
          type="warning"
          showIcon
          message={categorySkuComparisonError}
          action={<Button size="small" onClick={() => { void loadCategorySkuDetails(categorySkuComparisonModalRow) }}>重试</Button>}
        />
      ) : null}
      {categorySkuModalMode === 'focus' && categorySkuFocusSupportedMetrics.length > 0 && categorySkuFocusUnavailableMetrics.length > 0 ? (
        <Alert
          type="info"
          showIcon
          message={`部分指标暂无数据：${categorySkuFocusUnavailableMetrics.map((metric) => comparisonMetricLabels[metric]).join('、')}，相关规则未参与判断`}
        />
      ) : null}
      <div className="traffic-category-sku-modal__table-meta" aria-live="polite">
        {categorySkuModalMode === 'comparison' ? (
          <>
            <strong>{comparisonMetricLabels[categorySkuComparisonMetric]}环比 SKU Top20</strong>
            <span>按{comparisonSortLabel(categorySkuComparisonSort)}排序 · 条件变化后重新查询后端</span>
          </>
        ) : (
          <>
            <strong>重点 SKU {categorySkuFocusRows.length} 个</strong>
            <span>当前期 Top{categorySkuFocusTopN} 口径 · 多规则命中优先</span>
          </>
        )}
      </div>
      {categorySkuModalMode === 'comparison' ? (
        <DataTable<TrafficComparisonRow>
          rowKey={(item) => `${item.rank}-${item.platform_account_id}-${item.region}-${item.entity_id || item.sku}`}
          size="small"
          className="traffic-category-sku-table"
          dataSource={categorySkuComparisonRows}
          columns={categorySkuComparisonColumns}
          loading={categorySkuComparisonLoading}
          onChange={handleCategorySkuComparisonTableChange}
          pagination={false}
          sticky={false}
          scroll={{ x: 1110, y: 'min(470px, max(240px, calc(100vh - 330px)))' }}
          locale={{
            emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={`该品类暂无符合条件的${comparisonMetricLabels[categorySkuComparisonMetric]}环比 SKU`} />
          }}
        />
      ) : (
        <DataTable<TrafficSkuFocusRow>
          rowKey={(item) => `${item.platform_account_id}-${item.region}-${item.entity_id || item.sku}`}
          size="small"
          className="traffic-category-sku-table"
          dataSource={categorySkuFocusRows}
          columns={categorySkuFocusColumns}
          loading={categorySkuComparisonLoading}
          pagination={false}
          sticky={false}
          scroll={{ x: 1430, y: 'min(470px, max(240px, calc(100vh - 330px)))' }}
          locale={{
            emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={`当前 Top${categorySkuFocusTopN} 规则下暂无重点 SKU`} />
          }}
        />
      )}
    </Modal>
  ) : null

  const tableLocale = {
    emptyText: (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={dataError ? '数据加载失败' : statusAlert?.message || '当前筛选条件暂无数据'}
      />
    )
  }

  return (
    <div className="traffic-analytics-page">
      <div className="traffic-page-header">
        <div className="traffic-page-title">
          <AreaChartOutlined />
          <h1>流量分析</h1>
          <span>{filters.date_from} 至 {filters.date_to}</span>
        </div>
        <div className="traffic-page-actions">
          <div className="traffic-update-time" aria-live="polite">
            <span>数据更新</span>
            <strong>{formatTime(latestDataUpdateAt)}</strong>
          </div>
          <Tooltip title="刷新数据"><Button icon={<ReloadOutlined />} onClick={() => { void loadAccounts().catch(() => undefined); void reloadTrafficData().catch(() => undefined) }} aria-label="刷新流量分析" /></Tooltip>
          <Button type="primary" icon={<SyncOutlined />} loading={syncing || activeSync} onClick={() => void startSync()}>
            {accountIds.length ? '同步选中店铺' : platforms.length ? '同步选中平台' : '同步全部店铺'}
          </Button>
        </div>
      </div>

      <div className="traffic-filter-bar">
        <div className="traffic-filter-field" role="group" aria-labelledby="traffic-filter-date-label">
          <span id="traffic-filter-date-label" className="traffic-filter-label">日期</span>
          <RangePicker
            className="traffic-filter-date"
            classNames={{ popup: { root: 'traffic-filter-date-popup' } }}
            value={range}
            presets={datePresets}
            allowClear={false}
            disabledDate={(current) => current && current >= dayjs().startOf('day')}
            onChange={(dates) => {
              if (dates?.[0] && dates?.[1]) setRange([dates[0], dates[1]])
            }}
          />
        </div>
        <div className="traffic-filter-field" role="group" aria-labelledby="traffic-filter-platform-label">
          <span id="traffic-filter-platform-label" className="traffic-filter-label">平台</span>
          <Select
            mode="multiple"
            value={platforms}
            allowClear
            showSearch
            optionFilterProp="label"
            maxTagCount={1}
            maxTagPlaceholder={(omittedValues) => `+${omittedValues.length}`}
            placeholder="全部平台"
            className="traffic-filter-select traffic-filter-select--platform"
            options={Object.entries(platformLabels).map(([value, label]) => ({ value, label }))}
            optionRender={(option) => filterOption(option.label, platforms.includes(String(option.value)))}
            onChange={(values) => {
              setPlatforms(values)
              const selectedPlatforms = new Set(values)
              const availableRegionSet = new Set(
                regionsForPlatforms(knownRegionsByPlatform, values)
              )
              setRegions((current) =>
                current.filter((region) => availableRegionSet.has(region))
              )
              setAccountIds((current) =>
                current.filter((id) => {
                  const account = accounts.find((item) => item.id === id)
                  return account && (!selectedPlatforms.size || selectedPlatforms.has(account.platform))
                })
              )
            }}
          />
        </div>
        <div className="traffic-filter-field" role="group" aria-labelledby="traffic-filter-shop-label">
          <span id="traffic-filter-shop-label" className="traffic-filter-label">店铺</span>
          <Select
            mode="multiple"
            value={accountIds}
            allowClear
            showSearch
            optionFilterProp="label"
            maxTagCount={1}
            maxTagPlaceholder={(omittedValues) => `+${omittedValues.length}`}
            placeholder="全部店铺"
            className="traffic-filter-select traffic-filter-select--shop"
            options={visibleAccounts.map((account) => ({ value: account.id, label: account.display_name }))}
            optionRender={(option) => filterOption(option.label, accountIds.includes(Number(option.value)))}
            onChange={setAccountIds}
          />
        </div>
        <div className="traffic-filter-field" role="group" aria-labelledby="traffic-filter-source-label">
          <span id="traffic-filter-source-label" className="traffic-filter-label">来源</span>
          <Select
            value={source || undefined}
            allowClear
            placeholder="全部来源"
            className="traffic-filter-select"
            options={[
              { value: 'platform', label: '平台全量' },
              { value: 'organic', label: '自然流量' },
              { value: 'ads', label: '广告流量' }
            ]}
            onChange={(value) => setSource(value || '')}
          />
        </div>
        <div className="traffic-filter-field" role="group" aria-labelledby="traffic-filter-region-label">
          <span id="traffic-filter-region-label" className="traffic-filter-label">地区</span>
          <Select
            mode="multiple"
            value={regions}
            allowClear
            showSearch
            optionFilterProp="label"
            maxTagCount={1}
            maxTagPlaceholder={(omittedValues) => `+${omittedValues.length}`}
            placeholder="全部地区"
            className="traffic-filter-select traffic-filter-select--region"
            options={regionOptions}
            optionRender={(option) => filterOption(option.label, regions.includes(String(option.value)))}
            onChange={setRegions}
          />
        </div>
      </div>

      {statusAlert ? (
        <Alert
          className="traffic-status-alert"
          type={statusAlert.type}
          showIcon
          message={statusAlert.message}
          description={statusAlert.description}
        />
      ) : null}

      <div
        ref={tableSurfaceRef}
        className="traffic-table-surface"
        style={{ '--traffic-table-body-height': `${tableBodyHeight}px` } as CSSProperties}
      >
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          tabBarExtraContent={(
            <Tooltip title="设置字段">
              <Button
                type="text"
                size="small"
                icon={<SettingOutlined />}
                aria-label="设置字段"
                onClick={() => setSettingsTab(activeTab)}
              />
            </Tooltip>
          )}
          items={[
            {
              key: 'summary',
              label: '店铺分析',
              children: <DataTable<TrafficMetricRow> persistentHorizontalScrollbar tableConfig={TRAFFIC_SUMMARY_TABLE_CONFIG} showColumnSettingsButton={false} columnSettingsOpen={settingsTab === 'summary'} onColumnSettingsOpenChange={(open) => setSettingsTab(open ? 'summary' : null)} rowKey={(row) => `${row.platform_account_id}-${row.source}-${row.grain}-${row.region}`} columns={summaryColumns} dataSource={summary} loading={dataLoading} locale={tableLocale} sticky scroll={{ x: 2140, y: tableBodyHeight }} pagination={{ defaultPageSize: 20, showSizeChanger: true, showTotal: (total) => `共 ${total} 条` }} />
            },
            {
              key: 'categories',
              label: '品类分析',
              children: (
                <>
                  <div className="traffic-category-toolbar">
                    <div className="traffic-category-coverage" aria-live="polite">
                      <span>品类覆盖</span>
                      <strong>{formatPercent(categoryResult.classification_rate)}</strong>
                      <span>{formatInteger(categoryResult.categorized_sku_count)} / {formatInteger(categoryResult.total_sku_count)} SKU</span>
                      <span className="traffic-category-unmatched">未归类 {formatInteger(categoryResult.uncategorized_sku_count)}</span>
                    </div>
                    <div className="traffic-category-controls">
                      <Select
                        mode="multiple"
                        allowClear
                        showSearch
                        optionFilterProp="label"
                        maxTagCount={1}
                        maxTagPlaceholder={(omittedValues) => `+${omittedValues.length}`}
                        aria-label="筛选平台品类"
                        placeholder="全部品类"
                        className="traffic-category-select"
                        value={categoryKeys}
                        options={categoryOptions}
                        onChange={setCategoryKeys}
                      />
                      <Checkbox
                        checked={includeUncategorized}
                        onChange={(event) => setIncludeUncategorized(event.target.checked)}
                      >
                        包含未归类
                      </Checkbox>
                    </div>
                  </div>
                  <DataTable<TrafficCategoryRow>
                    key={platforms.length ? 'platform-categories' : 'all-platform-categories'}
                    persistentHorizontalScrollbar
                    fitContentColumns={false}
                    tableConfig={TRAFFIC_CATEGORY_TABLE_CONFIG}
                    showColumnSettingsButton={false}
                    columnSettingsOpen={settingsTab === 'categories'}
                    onColumnSettingsOpenChange={(open) => setSettingsTab(open ? 'categories' : null)}
                    rowKey={(row) => `${row.platform_account_id}-${row.source}-${row.grain}-${row.region}-${row.platform_category_id || 'uncategorized'}`}
                    columns={categoryColumns}
                    dataSource={visibleCategoryRows}
                    loading={dataLoading}
                    locale={{
                      emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={includeUncategorized ? '当前筛选条件暂无品类数据' : '当前筛选条件暂无已归类数据'} />
                    }}
                    sticky
                    scroll={{ y: tableBodyHeight }}
                    pagination={{ defaultPageSize: 20, showSizeChanger: true, showTotal: (total) => `共 ${total} 条` }}
                  />
                </>
              )
            },
            {
              key: 'rankings',
              label: 'SKU Top20',
              children: (
                <>
                  <div className="traffic-tab-toolbar"><Segmented<TrafficMetricKey> value={rankMetric} options={availableRankingMetricOptions} onChange={(metric) => { setRankMetric(metric); setRankRateSort(null) }} /></div>
                  <DataTable<TrafficMetricRow> persistentHorizontalScrollbar tableConfig={TRAFFIC_RANKING_TABLE_CONFIG} showColumnSettingsButton={false} columnSettingsOpen={settingsTab === 'rankings'} onColumnSettingsOpenChange={(open) => setSettingsTab(open ? 'rankings' : null)} rowKey={(row) => `${row.rank}-${row.platform_account_id}-${row.region}-${row.entity_id}`} columns={rankingColumns} dataSource={orderedRankings} loading={dataLoading} locale={tableLocale} onChange={handleRankingTableChange} sticky scroll={{ x: 2330, y: tableBodyHeight }} pagination={false} />
                </>
              )
            },
            {
              key: 'comparison',
              label: '环比分析',
              children: (
                <>
                  <div className="traffic-tab-toolbar">
                    <Segmented<TrafficMetricKey> value={comparisonMetric} options={availableComparisonMetricOptions} onChange={setComparisonMetric} />
                    <div className="traffic-comparison-dimension">
                      <span>分析维度：</span>
                      <Segmented<TrafficComparisonDimension>
                        aria-label="环比分析维度"
                        value={comparisonDimension}
                        options={comparisonDimensionOptions}
                        onChange={setComparisonDimension}
                      />
                    </div>
                    <span>对比期：{comparisonPeriod || '--'}</span>
                  </div>
                  <DataTable<TrafficComparisonRow> key={comparisonDimension} persistentHorizontalScrollbar tableConfig={comparisonDimension === 'category' ? TRAFFIC_CATEGORY_COMPARISON_TABLE_CONFIG : TRAFFIC_COMPARISON_TABLE_CONFIG} showColumnSettingsButton={false} columnSettingsOpen={settingsTab === 'comparison'} onColumnSettingsOpenChange={(open) => setSettingsTab(open ? 'comparison' : null)} rowKey={(row) => comparisonDimension === 'category' ? trafficComparisonCategoryKey(row) : `${row.rank}-${row.platform_account_id}-${row.region}-${row.entity_id}`} columns={comparisonColumns} dataSource={comparison} loading={dataLoading} locale={tableLocale} onChange={handleComparisonTableChange} sticky scroll={{ x: comparisonDimension === 'category' ? 1824 : 1700, y: tableBodyHeight }} pagination={false} />
                </>
              )
            }
          ]}
        />
      </div>
      {categorySkuComparisonModal}
    </div>
  )
}
