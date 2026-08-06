import { describe, expect, it, vi } from 'vitest'
import { shouldIgnoreTableRowDoubleClick } from './tableInteractions'

describe('shouldIgnoreTableRowDoubleClick', () => {
  it('allows double-clicks on ordinary table content', () => {
    const target = { closest: vi.fn(() => null) } as unknown as EventTarget

    expect(shouldIgnoreTableRowDoubleClick(target)).toBe(false)
  })

  it('ignores double-clicks inside interactive controls', () => {
    const target = { closest: vi.fn(() => ({} as Element)) } as unknown as EventTarget

    expect(shouldIgnoreTableRowDoubleClick(target)).toBe(true)
  })

  it('allows missing event targets', () => {
    expect(shouldIgnoreTableRowDoubleClick(null)).toBe(false)
  })
})
