/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

export function sortShopTrendsByRevenue<T extends { total_revenue_cny: number }>(shops: readonly T[]): T[] {
  return shops
    .map((shop, index) => ({ shop, index }))
    .sort((left, right) => (
      right.shop.total_revenue_cny - left.shop.total_revenue_cny
      || left.index - right.index
    ))
    .map(({ shop }) => shop)
}
