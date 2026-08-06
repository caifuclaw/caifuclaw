import { del, get, post, put } from './http'

export interface PlatformProductCatalogItemDto {
  id: number
  shop_id: number
  shop_name: string
  platform: string
  product_id?: number | null
  product_code: string
  internal_product_name: string
  platform_product_id: string
  platform_sku: string
  product_name: string
  main_image_url: string
  listing_status: string
  warehouse_code: string
  warehouse_name: string
  fulfillment_type: string
  logistics_type: string
  available_stock: number
  reserved_stock?: number | null
  price_amount?: string | null
  price_currency: string
  exchange_rate?: string | null
  exchange_rate_date?: string | null
  current_price_cny?: string | null
  cost_cny?: string | null
  commission_rate?: string | null
  shipping_fee_cny?: string | null
  target_margin_rate?: string | null
  current_profit_cny?: string | null
  current_margin_rate?: string | null
  suggested_price_cny?: string | null
  calculation_status: string
  calculation_message: string
  last_synced_at?: string | null
  calculated_at?: string | null
  is_active: boolean
}

export interface PlatformProductCatalogListParams {
  platform?: string
  shop_id?: number
  keyword?: string
  calculation_status?: string
  mapped?: boolean
  include_inactive?: boolean
  page?: number
  page_size?: number
}

export interface PlatformProductCatalogListResponse {
  items: PlatformProductCatalogItemDto[]
  total: number
  page: number
  page_size: number
  summary: Record<string, number>
}

export interface CatalogShopOption {
  id: number
  platform: string
  label: string
  account_id: string
}

export interface CatalogProductOption {
  id: number
  product_code: string
  internal_name: string
}

export interface PlatformProductCatalogOptionsResponse {
  shops: CatalogShopOption[]
  products: CatalogProductOption[]
}

export interface PlatformProductCatalogSyncResult {
  shops: Array<{ shop_id: number; shop_name: string; status: string; synced: number; message?: string }>
  success: number
  failed: number
  synced: number
}

export interface PlatformProductPricingRuleDto {
  id: number
  name: string
  platform: string
  shop_id?: number | null
  shop_name: string
  product_id?: number | null
  product_name: string
  warehouse_code: string
  logistics_type: string
  commission_rate: string
  base_shipping_fee_cny: string
  shipping_fee_per_kg_cny: string
  target_margin_rate: string
  price_increment_cny: string
  priority: number
  enabled: boolean
  remark: string
  updated_at?: string | null
}

export interface PlatformProductPricingRuleInput {
  name: string
  platform: string
  shop_id?: number | null
  product_id?: number | null
  warehouse_code: string
  logistics_type: string
  commission_rate: string | number
  base_shipping_fee_cny: string | number
  shipping_fee_per_kg_cny: string | number
  target_margin_rate: string | number
  price_increment_cny: string | number
  priority: number
  enabled: boolean
  remark: string
}

export function listPlatformProductCatalog(params: PlatformProductCatalogListParams) {
  return get<PlatformProductCatalogListResponse>('/api/v1/platform-product-catalog', { params, background: true })
}

export function getPlatformProductCatalogOptions() {
  return get<PlatformProductCatalogOptionsResponse>('/api/v1/platform-product-catalog/options', { background: true })
}

export function syncPlatformProductCatalog(shop_ids: number[] = [], mode: 'full' | 'incremental' = 'full') {
  return post<PlatformProductCatalogSyncResult>('/api/v1/platform-product-catalog/sync', { shop_ids, mode }, { timeout: 600000 })
}

export function recalculatePlatformProductCatalog(item_ids: number[] = []) {
  return post<{ recalculated: number }>('/api/v1/platform-product-catalog/recalculate', { item_ids })
}

export function mapPlatformProductCatalogItem(itemId: number, product_id: number | null) {
  return put<PlatformProductCatalogItemDto>(`/api/v1/platform-product-catalog/items/${itemId}/mapping`, { product_id })
}

export function listPlatformProductPricingRules() {
  return get<PlatformProductPricingRuleDto[]>('/api/v1/platform-product-catalog/rules', { background: true })
}

export function createPlatformProductPricingRule(payload: PlatformProductPricingRuleInput) {
  return post<PlatformProductPricingRuleDto>('/api/v1/platform-product-catalog/rules', payload)
}

export function updatePlatformProductPricingRule(id: number, payload: PlatformProductPricingRuleInput) {
  return put<PlatformProductPricingRuleDto>(`/api/v1/platform-product-catalog/rules/${id}`, payload)
}

export function deletePlatformProductPricingRule(id: number) {
  return del<void>(`/api/v1/platform-product-catalog/rules/${id}`)
}
