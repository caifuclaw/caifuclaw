/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import type {
  TrafficCategorySkuComparisonFilters,
  TrafficComparisonRow
} from '@/api/trafficAnalytics'

type CategorySkuContext = Pick<
  TrafficCategorySkuComparisonFilters,
  'platform' | 'platform_account_id' | 'source' | 'grain' | 'region' | 'platform_category_id'
>

const defaultContextByPlatform: Record<string, Pick<CategorySkuContext, 'source' | 'grain'>> = {
  ozon: { source: 'organic', grain: 'daily' },
  joom_logistics: { source: 'platform', grain: 'date_range' },
  mercadolibre: { source: 'organic', grain: 'date_range' },
  allegro: { source: 'organic', grain: 'rolling_30d' },
  wildberries: { source: 'organic', grain: 'date_range' }
}

export function resolveCategorySkuComparisonContext(row: TrafficComparisonRow): CategorySkuContext | null {
  const platform = String(row.platform || '').trim().toLowerCase()
  const accountId = Number(row.platform_account_id || 0)
  const defaults = defaultContextByPlatform[platform]
  const source = String(row.source || defaults?.source || '').trim().toLowerCase()
  const grain = String(row.grain || defaults?.grain || '').trim().toLowerCase()

  if (!platform || !accountId || !grain) return null

  return {
    platform,
    platform_account_id: accountId,
    source,
    grain,
    region: String(row.region || '').trim().toUpperCase(),
    platform_category_id: String(row.platform_category_id || '').trim()
  }
}

export function categorySkuComparisonContextError(row: TrafficComparisonRow): string {
  const platform = String(row.platform || '').trim()
  const accountId = Number(row.platform_account_id || 0)
  const grain = String(row.grain || defaultContextByPlatform[platform.toLowerCase()]?.grain || '').trim()
  const missing: string[] = []

  if (!platform) missing.push('平台')
  if (!accountId) missing.push('店铺')
  if (!grain) missing.push('统计粒度')

  return missing.length
    ? `品类明细上下文不完整，缺少${missing.join('、')}`
    : '品类 SKU 明细加载失败'
}
