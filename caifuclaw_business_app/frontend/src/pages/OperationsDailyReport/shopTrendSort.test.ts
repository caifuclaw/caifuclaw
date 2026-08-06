import { describe, expect, it } from 'vitest'
import { sortShopTrendsByRevenue } from './shopTrendSort'

describe('sortShopTrendsByRevenue', () => {
  it('sorts shops by seven-day revenue in descending order', () => {
    const shops = [
      { shop: 'Zero', total_revenue_cny: 0 },
      { shop: 'High', total_revenue_cny: 3200 },
      { shop: 'Middle', total_revenue_cny: 1250 }
    ]

    expect(sortShopTrendsByRevenue(shops).map((item) => item.shop)).toEqual(['High', 'Middle', 'Zero'])
  })

  it('preserves the original order when revenues are equal without mutating the source', () => {
    const shops = [
      { shop: 'First', total_revenue_cny: 100 },
      { shop: 'Second', total_revenue_cny: 100 },
      { shop: 'Third', total_revenue_cny: 0 }
    ]
    const sorted = sortShopTrendsByRevenue(shops)

    expect(sorted.map((item) => item.shop)).toEqual(['First', 'Second', 'Third'])
    expect(shops.map((item) => item.shop)).toEqual(['First', 'Second', 'Third'])
    expect(sorted).not.toBe(shops)
  })
})
