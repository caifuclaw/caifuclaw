/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { describe, expect, it } from 'vitest'
import { compareNullableTableMetric, rankingRateSortFromTable } from './rankingSort'

describe('rankingRateSortFromTable', () => {
  it('maps CTR and CVR table sorting to server query values', () => {
    expect(rankingRateSortFromTable({ columnKey: 'ctr', order: 'descend' })).toEqual({
      metric: 'ctr',
      order: 'desc'
    })
    expect(rankingRateSortFromTable({ columnKey: 'cvr', order: 'ascend' })).toEqual({
      metric: 'cvr',
      order: 'asc'
    })
  })

  it('clears rate sorting when the active table sort is removed', () => {
    expect(rankingRateSortFromTable({ columnKey: 'ctr' })).toBeNull()
    expect(rankingRateSortFromTable()).toBeNull()
  })

  it('ignores unrelated sortable columns', () => {
    expect(rankingRateSortFromTable({ columnKey: 'clicks', order: 'descend' })).toBeUndefined()
  })
})

describe('compareNullableTableMetric', () => {
  it('sorts numeric values while keeping missing values last in both directions', () => {
    const values = [0.25, null, 0.5, 0.1]
    const ascending = [...values].sort((left, right) => compareNullableTableMetric(left, right, 'ascend'))
    const descending = [...values].sort((left, right) => -compareNullableTableMetric(left, right, 'descend'))

    expect(ascending).toEqual([0.1, 0.25, 0.5, null])
    expect(descending).toEqual([0.5, 0.25, 0.1, null])
  })
})
