import { describe, expect, it } from 'vitest'
import {
  fitTableBodyHeightToRows,
  TRAFFIC_TABLE_MIN_BODY_HEIGHT
} from './tableBodyHeight'

describe('fitTableBodyHeightToRows', () => {
  it('keeps the custom scrollbar below a whole number of rows', () => {
    expect(fitTableBodyHeightToRows(324, 47, 16)).toBe(298)
  })

  it('reserves native scrollbar height before fitting rows', () => {
    expect(fitTableBodyHeightToRows(300, 39, 12)).toBe(285)
  })

  it('uses the available height when row height is not measurable', () => {
    expect(fitTableBodyHeightToRows(220.8, 0, 16)).toBe(220)
  })

  it('preserves the minimum fallback for short empty tables', () => {
    expect(fitTableBodyHeightToRows(120, 0, 0)).toBe(
      TRAFFIC_TABLE_MIN_BODY_HEIGHT
    )
  })
})
