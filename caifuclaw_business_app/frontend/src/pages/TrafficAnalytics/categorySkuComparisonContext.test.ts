import { describe, expect, it } from 'vitest'
import type { TrafficComparisonRow } from '@/api/trafficAnalytics'
import {
  categorySkuComparisonContextError,
  resolveCategorySkuComparisonContext
} from './categorySkuComparisonContext'

function comparisonRow(overrides: Partial<TrafficComparisonRow> = {}): TrafficComparisonRow {
  return {
    rank: 1,
    platform: 'joom_logistics',
    platform_account_id: 8,
    account_id: 'shop-8',
    shop_name: 'HEAVEN',
    source: '',
    region: '',
    current_impressions: 100,
    previous_impressions: 40,
    delta_impressions: 60,
    delta_rate_impressions: 1.5,
    current_clicks: 20,
    previous_clicks: 10,
    delta_clicks: 10,
    delta_rate_clicks: 1,
    current_add_to_cart: 8,
    previous_add_to_cart: 4,
    delta_add_to_cart: 4,
    delta_rate_add_to_cart: 1,
    current_orders: 2,
    previous_orders: 1,
    delta_orders: 1,
    delta_rate_orders: 1,
    ...overrides
  }
}

describe('resolveCategorySkuComparisonContext', () => {
  it('fills Joom category rows with the platform default source and grain', () => {
    expect(resolveCategorySkuComparisonContext(comparisonRow({ platform_category_id: 'cat-a' }))).toEqual({
      platform: 'joom_logistics',
      platform_account_id: 8,
      source: 'platform',
      grain: 'date_range',
      region: '',
      platform_category_id: 'cat-a'
    })
  })

  it('keeps an empty category id for uncategorized rows', () => {
    expect(resolveCategorySkuComparisonContext(comparisonRow({ platform_category_id: '' }))).toMatchObject({
      platform_category_id: ''
    })
  })

  it('reports missing required row context without rejecting uncategorized rows', () => {
    expect(resolveCategorySkuComparisonContext(comparisonRow({ platform: '', platform_account_id: 0 }))).toBeNull()
    expect(categorySkuComparisonContextError(comparisonRow({ platform: '', platform_account_id: 0 }))).toContain('平台、店铺')
  })
})
