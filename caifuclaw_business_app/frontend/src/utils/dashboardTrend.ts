import dayjs from 'dayjs'
import type { DashboardRange } from './dashboardPeriod'

export type DashboardGroupBy = 'day' | 'week' | 'month'
export type DashboardTrendMetric = 'orders' | 'expected_receipt'

export interface DashboardTrendDailyRow {
  date: string
  orders: number
  expected_receipt: number
}

export interface DashboardTrendPoint {
  currentStartDate: string
  currentEndDate: string
  comparisonStartDate: string
  comparisonEndDate: string
  currentValue: number
  comparisonValue: number
}

const DASHBOARD_GROUP_VALUES: DashboardGroupBy[] = ['day', 'week', 'month']

export function initialDashboardGroupBy(searchParams: URLSearchParams): DashboardGroupBy {
  const requested = searchParams.get('group_by') as DashboardGroupBy | null
  return requested && DASHBOARD_GROUP_VALUES.includes(requested) ? requested : 'day'
}

function rowsByDate(rows: DashboardTrendDailyRow[]) {
  return new Map(rows.map((row) => [row.date, row]))
}

function naturalPeriodKey(date: dayjs.Dayjs, groupBy: DashboardGroupBy) {
  if (groupBy === 'day') return date.format('YYYY-MM-DD')
  if (groupBy === 'month') return date.format('YYYY-MM')
  const daysSinceMonday = (date.day() + 6) % 7
  return date.subtract(daysSinceMonday, 'day').format('YYYY-MM-DD')
}

export function dashboardTrendPoints(
  currentRows: DashboardTrendDailyRow[],
  comparisonRows: DashboardTrendDailyRow[],
  currentRange: DashboardRange,
  comparisonRange: DashboardRange,
  groupBy: DashboardGroupBy,
  metric: DashboardTrendMetric
): DashboardTrendPoint[] {
  const currentByDate = rowsByDate(currentRows)
  const comparisonByDate = rowsByDate(comparisonRows)
  const dayCount = currentRange[1].diff(currentRange[0], 'day') + 1
  const groupedPoints: Array<DashboardTrendPoint & { key: string }> = []

  // Pair comparison values by day offset so each dashed point covers the same slice of its selected range.
  for (let index = 0; index < dayCount; index += 1) {
    const currentDate = currentRange[0].add(index, 'day')
    const comparisonDate = comparisonRange[0].add(index, 'day')
    const currentDateKey = currentDate.format('YYYY-MM-DD')
    const comparisonDateKey = comparisonDate.format('YYYY-MM-DD')
    const key = naturalPeriodKey(currentDate, groupBy)
    const currentValue = currentByDate.get(currentDateKey)?.[metric] || 0
    const comparisonValue = comparisonByDate.get(comparisonDateKey)?.[metric] || 0
    const existing = groupedPoints.at(-1)

    if (existing?.key === key) {
      existing.currentEndDate = currentDateKey
      existing.comparisonEndDate = comparisonDateKey
      existing.currentValue += currentValue
      existing.comparisonValue += comparisonValue
      continue
    }

    groupedPoints.push({
      key,
      currentStartDate: currentDateKey,
      currentEndDate: currentDateKey,
      comparisonStartDate: comparisonDateKey,
      comparisonEndDate: comparisonDateKey,
      currentValue,
      comparisonValue
    })
  }

  return groupedPoints.map(({ key: _key, ...point }) => point)
}
