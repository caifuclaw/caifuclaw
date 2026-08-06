/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

export const PLATFORM_OPTIONS = [
  { code: 'ozon', label: 'Ozon' },
  { code: 'mercadolibre', label: 'MercadoLibre' },
  { code: 'allegro', label: 'Allegro' },
  { code: 'wildberries', label: 'Wildberries' },
  { code: 'joom_logistics', label: 'Joom' },
  { code: 'amazon', label: 'Amazon' },
  { code: 'shopee', label: 'Shopee' },
  { code: 'tiktok_shop', label: 'TikTok Shop' },
  { code: 'aliexpress', label: 'AliExpress' },
  { code: 'lazada', label: 'Lazada' },
  { code: 'shopify', label: 'Shopify' },
  { code: 'ebay', label: 'eBay' },
  { code: 'walmart', label: 'Walmart' },
  { code: 'temu', label: 'Temu' },
  { code: 'shein', label: 'SHEIN' },
  { code: 'coupang', label: 'Coupang' },
  { code: 'wayfair', label: 'Wayfair' },
  { code: 'dmsmatrix', label: 'DMSMatrix' }
]

export const PRINT_ONLY_PLATFORM_OPTIONS = [
  { code: 'chinese_label', label: '中文标签' }
]

const PLATFORM_LABEL_BY_KEY = new Map<string, string>(
  [...PLATFORM_OPTIONS, ...PRINT_ONLY_PLATFORM_OPTIONS].flatMap((option): Array<[string, string]> => [
    [option.code, option.label],
    [option.code.toLowerCase(), option.label],
    [option.label, option.label],
    [option.label.toLowerCase(), option.label]
  ])
)

const PLATFORM_CODE_ALIASES: Record<string, string> = {
  joom: 'joom_logistics',
  joomlogistics: 'joom_logistics',
  mercado_libre: 'mercadolibre',
  tiktok: 'tiktok_shop',
  tiktokshop: 'tiktok_shop',
  ali_express: 'aliexpress',
  shopify_admin: 'shopify',
  ebay_sell: 'ebay',
  walmart_marketplace: 'walmart',
  shein_open: 'shein',
  coupang_openapi: 'coupang',
  wayfair_partner: 'wayfair',
  dms_matrix: 'dmsmatrix',
  'dms-matrix': 'dmsmatrix',
  dms_matrix_erp: 'dmsmatrix',
  dmsmatrix_erp: 'dmsmatrix'
}

export function formatPlatformLabel(value?: string | null) {
  const platform = value?.trim()
  if (!platform) return '-'

  const normalized = platform.toLowerCase()
  const canonical = PLATFORM_CODE_ALIASES[normalized] || normalized
  return PLATFORM_LABEL_BY_KEY.get(platform) || PLATFORM_LABEL_BY_KEY.get(normalized) || PLATFORM_LABEL_BY_KEY.get(canonical) || platform
}

export const ORDER_STATUSES = [
  { code: 'all', label: '全部' },
  { code: 'pending', label: '待处理' },
  { code: 'waiting_print', label: '待打印' },
  { code: 'waiting_purchase', label: '待采购' },
  { code: 'picking', label: '配货中' },
  { code: 'shipped', label: '已发货' },
  { code: 'awaiting_pickup', label: '待揽收' },
  { code: 'delivered', label: '已妥投' },
  { code: 'voided', label: '已作废' }
] as const

export type OrderStatus = (typeof ORDER_STATUSES)[number]['code']

export const ORDER_STATUS_COLOR: Record<string, string> = {
  pending: 'orange',
  待处理: 'orange',
  waiting_print: 'gold',
  待打印: 'gold',
  waiting_purchase: 'volcano',
  待采购: 'volcano',
  picking: 'blue',
  配货中: 'blue',
  shipped: 'cyan',
  已发货: 'cyan',
  awaiting_pickup: 'purple',
  待揽收: 'purple',
  awaiting_delivery: 'purple',
  待配送: 'purple',
  delivered: 'green',
  已妥投: 'green',
  completed: 'green',
  已完成: 'green',
  voided: 'default',
  cancelled: 'default',
  已作废: 'default'
}

export const SHOP_STATUS_COLOR: Record<string, string> = {
  success: 'success',
  pending: 'processing',
  failed: 'error'
}
