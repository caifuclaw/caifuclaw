import dayjs, { type Dayjs } from 'dayjs'

export type DashboardPeriod = '7d' | '28d' | 'quarter' | 'year' | 'custom'
export type DashboardCompareMode = 'previous' | 'last_year' | 'custom' | 'none'
export type DashboardRange = [Dayjs, Dayjs]

export interface DashboardSelection {
  period: DashboardPeriod
  range: DashboardRange
}

export interface DashboardComparisonSelection {
  mode: DashboardCompareMode
  range: DashboardRange
}

const PRESET_PERIODS: Exclude<DashboardPeriod, 'custom'>[] = ['7d', '28d', 'quarter', 'year']
const COMPARE_MODES: DashboardCompareMode[] = ['previous', 'last_year', 'custom', 'none']

function normalizedRange(start: Dayjs, end: Dayjs): DashboardRange {
  return [start.startOf('day'), end.startOf('day')]
}

export function currentDashboardRange(
  period: Exclude<DashboardPeriod, 'custom'>,
  now: Dayjs = dayjs()
): DashboardRange {
  const end = now.subtract(1, 'day').startOf('day')
  if (period === '7d') return [end.subtract(6, 'day'), end]
  if (period === '28d') return [end.subtract(27, 'day'), end]
  if (period === 'quarter') return [end.subtract(3, 'month').add(1, 'day'), end]
  return [end.subtract(1, 'year').add(1, 'day'), end]
}

function rangeThroughYesterday(range: DashboardRange | null, now: Dayjs): DashboardRange | null {
  if (!range) return null
  const latestDate = now.subtract(1, 'day').startOf('day')
  const end = range[1].isAfter(latestDate, 'day') ? latestDate : range[1]
  if (range[0].isAfter(end, 'day')) return null
  return [range[0], end]
}

function rangeFromSearchParams(
  searchParams: URLSearchParams,
  fromKey = 'date_from',
  toKey = 'date_to'
): DashboardRange | null {
  const from = dayjs(searchParams.get(fromKey) || '')
  const to = dayjs(searchParams.get(toKey) || '')
  if (!from.isValid() || !to.isValid() || from.isAfter(to)) return null
  return normalizedRange(from, to)
}

function normalizedRequestedPeriod(value: string | null): DashboardPeriod | null {
  if (PRESET_PERIODS.includes(value as Exclude<DashboardPeriod, 'custom'>) || value === 'custom') {
    return value as DashboardPeriod
  }
  if (value === 'week') return '7d'
  if (value === 'month') return '28d'
  return null
}

function sameRange(left: DashboardRange, right: DashboardRange) {
  return left[0].isSame(right[0], 'day') && left[1].isSame(right[1], 'day')
}

function sameRangeLength(left: DashboardRange, right: DashboardRange) {
  return left[1].diff(left[0], 'day') === right[1].diff(right[0], 'day')
}

export function dashboardComparisonRange(
  mode: DashboardCompareMode,
  currentRange: DashboardRange,
  customRange?: DashboardRange | null
): DashboardRange {
  const daySpan = currentRange[1].diff(currentRange[0], 'day')
  if (mode === 'custom' && customRange && sameRangeLength(currentRange, customRange)) {
    return normalizedRange(customRange[0], customRange[1])
  }
  if (mode === 'last_year') {
    const start = currentRange[0].subtract(1, 'year')
    return [start, start.add(daySpan, 'day')]
  }
  const end = currentRange[0].subtract(1, 'day')
  return [end.subtract(daySpan, 'day'), end]
}

export function initialDashboardSelection(
  searchParams: URLSearchParams,
  now: Dayjs = dayjs()
): DashboardSelection {
  const requestedPeriod = normalizedRequestedPeriod(searchParams.get('period'))
  const requestedRange = rangeThroughYesterday(rangeFromSearchParams(searchParams), now)

  if (requestedPeriod && requestedPeriod !== 'custom') {
    return { period: requestedPeriod, range: currentDashboardRange(requestedPeriod, now) }
  }
  if (requestedPeriod === 'custom' && requestedRange) {
    return { period: 'custom', range: requestedRange }
  }
  if (requestedRange) {
    const matchingPreset = PRESET_PERIODS.find((period) => sameRange(requestedRange, currentDashboardRange(period, now)))
    return matchingPreset ? { period: matchingPreset, range: requestedRange } : { period: 'custom', range: requestedRange }
  }

  return { period: '28d', range: currentDashboardRange('28d', now) }
}

export function initialDashboardComparison(
  searchParams: URLSearchParams,
  currentRange: DashboardRange,
  now: Dayjs = dayjs()
): DashboardComparisonSelection {
  const requestedMode = searchParams.get('compare')
  const mode = COMPARE_MODES.includes(requestedMode as DashboardCompareMode)
    ? (requestedMode as DashboardCompareMode)
    : 'previous'
  const requestedRange = rangeThroughYesterday(
    rangeFromSearchParams(searchParams, 'compare_from', 'compare_to'),
    now
  )

  if (mode === 'custom' && requestedRange && sameRangeLength(currentRange, requestedRange)) {
    return { mode, range: requestedRange }
  }
  if (mode === 'custom') {
    return { mode: 'previous', range: dashboardComparisonRange('previous', currentRange) }
  }
  return { mode, range: dashboardComparisonRange(mode, currentRange) }
}

export function initialDashboardShopIds(searchParams: URLSearchParams): number[] {
  const values = searchParams.getAll('shop_ids').flatMap((value) => value.split(','))
  return [...new Set(values.map((value) => Number(value.trim())).filter((value) => Number.isInteger(value) && value > 0))].slice(0, 100)
}
