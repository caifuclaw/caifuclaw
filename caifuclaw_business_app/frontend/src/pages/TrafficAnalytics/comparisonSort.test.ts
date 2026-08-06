import { describe, expect, it } from 'vitest'
import { categorySkuSortFromTable, comparisonSortFromTable } from './comparisonSort'

describe('comparisonSortFromTable', () => {
  it('maps the rate column directions to server-side sorting', () => {
    expect(comparisonSortFromTable({ columnKey: 'delta_rate_metric', order: 'descend' })).toBe('rate_desc')
    expect(comparisonSortFromTable({ columnKey: 'delta_rate_metric', order: 'ascend' })).toBe('rate_asc')
  })

  it('restores the default ranking when table sorting is cleared', () => {
    expect(comparisonSortFromTable({})).toBe('delta_abs')
    expect(comparisonSortFromTable()).toBe('delta_abs')
  })

  it('maps the metric columns to server-side sorting', () => {
    expect(comparisonSortFromTable({ columnKey: 'current_metric', order: 'descend' })).toBe('current_desc')
    expect(comparisonSortFromTable({ columnKey: 'previous_metric', order: 'ascend' })).toBe('previous_asc')
    expect(comparisonSortFromTable({ columnKey: 'delta_metric', order: 'descend' })).toBe('delta_desc')
  })

  it('shares the same server-side mapping with the category SKU table', () => {
    expect(categorySkuSortFromTable({ columnKey: 'delta_rate_metric', order: 'ascend' })).toBe('rate_asc')
  })

  it('ignores sorting from unrelated columns', () => {
    expect(comparisonSortFromTable({ columnKey: 'sku', order: 'descend' })).toBeNull()
  })
})
