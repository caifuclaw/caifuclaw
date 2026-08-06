import type { TrafficRateMetricKey, TrafficSortOrder } from '@/api/trafficAnalytics'

export interface TrafficRankingRateSort {
  metric: TrafficRateMetricKey
  order: TrafficSortOrder
}

type RankingTableSorter = {
  columnKey?: unknown
  order?: 'ascend' | 'descend' | null
}

type TableSortOrder = 'ascend' | 'descend' | null | undefined

export function compareNullableTableMetric(
  left: number | null | undefined,
  right: number | null | undefined,
  order: TableSortOrder
): number {
  if (left == null && right == null) return 0
  if (left == null) return order === 'descend' ? -1 : 1
  if (right == null) return order === 'descend' ? 1 : -1
  return left - right
}

export function rankingRateSortFromTable(
  sorter?: RankingTableSorter
): TrafficRankingRateSort | null | undefined {
  if (!sorter?.order) return null
  if (sorter.columnKey !== 'ctr' && sorter.columnKey !== 'cvr') return undefined
  return {
    metric: sorter.columnKey,
    order: sorter.order === 'ascend' ? 'asc' : 'desc'
  }
}
