import dayjs from 'dayjs'
import { describe, expect, it } from 'vitest'
import {
  currentDashboardRange,
  dashboardComparisonRange,
  initialDashboardComparison,
  initialDashboardSelection,
  type DashboardRange
} from './dashboardPeriod'

function formattedRange(range: DashboardRange) {
  return range.map((value) => value.format('YYYY-MM-DD'))
}

describe('dashboard period selection', () => {
  const now = dayjs('2026-07-18T19:48:00')

  it('defaults to the rolling 28 day period', () => {
    const selection = initialDashboardSelection(new URLSearchParams(), now)

    expect(selection.period).toBe('28d')
    expect(formattedRange(selection.range)).toEqual(['2026-06-20', '2026-07-17'])
  })

  it('builds rolling preset ranges through yesterday', () => {
    expect(formattedRange(currentDashboardRange('7d', now))).toEqual(['2026-07-11', '2026-07-17'])
    expect(formattedRange(currentDashboardRange('quarter', now))).toEqual(['2026-04-18', '2026-07-17'])
    expect(formattedRange(currentDashboardRange('year', now))).toEqual(['2025-07-18', '2026-07-17'])
  })

  it('refreshes a persisted preset instead of keeping stale dates', () => {
    const params = new URLSearchParams('period=28d&date_from=2026-06-20&date_to=2026-07-17')
    const selection = initialDashboardSelection(params, now)

    expect(selection.period).toBe('28d')
    expect(formattedRange(selection.range)).toEqual(['2026-06-20', '2026-07-17'])
  })

  it('maps legacy week and month presets to the new rolling periods', () => {
    expect(initialDashboardSelection(new URLSearchParams('period=week'), now).period).toBe('7d')
    expect(initialDashboardSelection(new URLSearchParams('period=month'), now).period).toBe('28d')
  })

  it('preserves a valid custom date range', () => {
    const params = new URLSearchParams('period=custom&date_from=2026-06-01&date_to=2026-06-20')
    const selection = initialDashboardSelection(params, now)

    expect(selection.period).toBe('custom')
    expect(formattedRange(selection.range)).toEqual(['2026-06-01', '2026-06-20'])
  })

  it('removes today from a custom date range', () => {
    const params = new URLSearchParams('period=custom&date_from=2026-07-01&date_to=2026-07-18')
    const selection = initialDashboardSelection(params, now)

    expect(selection.period).toBe('custom')
    expect(formattedRange(selection.range)).toEqual(['2026-07-01', '2026-07-17'])
  })

  it('falls back to the default period when a custom range starts today', () => {
    const params = new URLSearchParams('period=custom&date_from=2026-07-18&date_to=2026-07-18')
    const selection = initialDashboardSelection(params, now)

    expect(selection.period).toBe('28d')
    expect(formattedRange(selection.range)).toEqual(['2026-06-20', '2026-07-17'])
  })
})

describe('dashboard comparison selection', () => {
  const current: DashboardRange = [dayjs('2026-07-01'), dayjs('2026-07-14')]

  it('uses the immediately preceding period with the same length', () => {
    expect(formattedRange(dashboardComparisonRange('previous', current))).toEqual(['2026-06-17', '2026-06-30'])
  })

  it('keeps last year comparison equal in length across leap years', () => {
    const leapRange: DashboardRange = [dayjs('2024-02-28'), dayjs('2024-03-01')]
    expect(formattedRange(dashboardComparisonRange('last_year', leapRange))).toEqual(['2023-02-28', '2023-03-02'])
  })

  it('accepts only an equal-length custom comparison range', () => {
    const equal = new URLSearchParams('compare=custom&compare_from=2026-05-01&compare_to=2026-05-14')
    const unequal = new URLSearchParams('compare=custom&compare_from=2026-05-01&compare_to=2026-05-10')

    expect(initialDashboardComparison(equal, current, dayjs('2026-07-18')).mode).toBe('custom')
    expect(formattedRange(initialDashboardComparison(equal, current, dayjs('2026-07-18')).range)).toEqual([
      '2026-05-01',
      '2026-05-14'
    ])
    expect(initialDashboardComparison(unequal, current, dayjs('2026-07-18')).mode).toBe('previous')
  })

  it('rejects a custom comparison period that includes today after clamping', () => {
    const params = new URLSearchParams('compare=custom&compare_from=2026-07-05&compare_to=2026-07-18')
    const comparison = initialDashboardComparison(params, current, dayjs('2026-07-18'))

    expect(comparison.mode).toBe('previous')
    expect(formattedRange(comparison.range)).toEqual(['2026-06-17', '2026-06-30'])
  })

  it('preserves the disabled comparison mode', () => {
    expect(initialDashboardComparison(new URLSearchParams('compare=none'), current).mode).toBe('none')
  })
})
