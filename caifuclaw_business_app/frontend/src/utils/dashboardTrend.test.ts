import dayjs from 'dayjs'
import { describe, expect, it } from 'vitest'
import type { DashboardRange } from './dashboardPeriod'
import {
  dashboardTrendPoints,
  initialDashboardGroupBy,
  type DashboardTrendDailyRow
} from './dashboardTrend'

function dailyRows(start: string, days: number, orders: number, expectedReceipt: number): DashboardTrendDailyRow[] {
  return Array.from({ length: days }, (_, index) => ({
    date: dayjs(start).add(index, 'day').format('YYYY-MM-DD'),
    orders,
    expected_receipt: expectedReceipt
  }))
}

function range(start: string, end: string): DashboardRange {
  return [dayjs(start), dayjs(end)]
}

describe('dashboard trend grouping selection', () => {
  it('defaults to day grouping', () => {
    expect(initialDashboardGroupBy(new URLSearchParams())).toBe('day')
    expect(initialDashboardGroupBy(new URLSearchParams('group_by=invalid'))).toBe('day')
  })

  it('restores valid grouping from the URL', () => {
    expect(initialDashboardGroupBy(new URLSearchParams('group_by=week'))).toBe('week')
    expect(initialDashboardGroupBy(new URLSearchParams('group_by=month'))).toBe('month')
  })
})

describe('dashboard trend point aggregation', () => {
  it('keeps one point per day and fills missing dates with zero', () => {
    const points = dashboardTrendPoints(
      [{ date: '2026-07-01', orders: 5, expected_receipt: 50 }],
      [],
      range('2026-07-01', '2026-07-02'),
      range('2026-06-01', '2026-06-02'),
      'day',
      'orders'
    )

    expect(points.map((point) => point.currentValue)).toEqual([5, 0])
    expect(points.map((point) => point.comparisonValue)).toEqual([0, 0])
  })

  it('groups weeks from Monday through Sunday with partial edge weeks', () => {
    const points = dashboardTrendPoints(
      dailyRows('2026-06-27', 11, 1, 10),
      dailyRows('2026-06-16', 11, 2, 20),
      range('2026-06-27', '2026-07-07'),
      range('2026-06-16', '2026-06-26'),
      'week',
      'orders'
    )

    expect(points.map((point) => [point.currentStartDate, point.currentEndDate])).toEqual([
      ['2026-06-27', '2026-06-28'],
      ['2026-06-29', '2026-07-05'],
      ['2026-07-06', '2026-07-07']
    ])
    expect(points.map((point) => point.currentValue)).toEqual([2, 7, 2])
    expect(points.map((point) => point.comparisonValue)).toEqual([4, 14, 4])
  })

  it('groups by natural month and preserves totals', () => {
    const points = dashboardTrendPoints(
      dailyRows('2026-06-29', 35, 1, 10),
      dailyRows('2026-05-01', 35, 2, 20),
      range('2026-06-29', '2026-08-02'),
      range('2026-05-01', '2026-06-04'),
      'month',
      'expected_receipt'
    )

    expect(points.map((point) => [point.currentStartDate, point.currentEndDate])).toEqual([
      ['2026-06-29', '2026-06-30'],
      ['2026-07-01', '2026-07-31'],
      ['2026-08-01', '2026-08-02']
    ])
    expect(points.map((point) => point.currentValue)).toEqual([20, 310, 20])
    expect(points.map((point) => point.comparisonValue)).toEqual([40, 620, 40])
    expect(points.reduce((sum, point) => sum + point.currentValue, 0)).toBe(350)
  })
})
