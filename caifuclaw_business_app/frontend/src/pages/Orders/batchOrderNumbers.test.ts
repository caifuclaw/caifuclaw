import { describe, expect, it } from 'vitest'
import {
  MAX_BATCH_ORDER_NUMBER_LENGTH,
  MAX_BATCH_ORDER_NUMBERS,
  parseBatchOrderNumbers
} from './batchOrderNumbers'

describe('parseBatchOrderNumbers', () => {
  it('parses supported separators, trims values, and removes duplicates', () => {
    const result = parseBatchOrderNumbers(' A-1\nA-2，A-1; A-3；A-4\tA-5 ')

    expect(result.tokens).toEqual(['A-1', 'A-2', 'A-1', 'A-3', 'A-4', 'A-5'])
    expect(result.uniqueNumbers).toEqual(['A-1', 'A-2', 'A-3', 'A-4', 'A-5'])
    expect(result.duplicateCount).toBe(1)
  })

  it('reports length and count validation without discarding the input', () => {
    const values = Array.from({ length: MAX_BATCH_ORDER_NUMBERS + 1 }, (_, index) => `ORDER-${index}`)
    values[0] = 'X'.repeat(MAX_BATCH_ORDER_NUMBER_LENGTH + 1)

    const result = parseBatchOrderNumbers(values.join('\n'))

    expect(result.overLimit).toBe(true)
    expect(result.tooLongNumbers).toEqual([values[0]])
  })

  it('ignores empty separators', () => {
    expect(parseBatchOrderNumbers('\n,，;；\t').uniqueNumbers).toEqual([])
  })
})
