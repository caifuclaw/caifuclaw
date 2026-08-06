import type { TrafficComparisonSort } from '@/api/trafficAnalytics'

type ComparisonTableSorter = {
  columnKey?: unknown
  order?: 'ascend' | 'descend' | null
}

export function comparisonSortFromTable(
  sorter?: ComparisonTableSorter
): TrafficComparisonSort | null {
  if (!sorter?.order) return 'delta_abs'
  const direction = sorter.order === 'descend' ? 'desc' : 'asc'
  const sortByColumn: Record<string, TrafficComparisonSort> = {
    current_metric: `current_${direction}` as TrafficComparisonSort,
    previous_metric: `previous_${direction}` as TrafficComparisonSort,
    delta_metric: `delta_${direction}` as TrafficComparisonSort,
    delta_rate_metric: `rate_${direction}` as TrafficComparisonSort
  }
  return sortByColumn[String(sorter.columnKey)] || null
}

export function categorySkuSortFromTable(
  sorter?: ComparisonTableSorter
): TrafficComparisonSort | null {
  return comparisonSortFromTable(sorter)
}
