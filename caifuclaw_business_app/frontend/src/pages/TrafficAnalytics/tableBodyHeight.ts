/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

export const TRAFFIC_TABLE_MIN_BODY_HEIGHT = 160

export function fitTableBodyHeightToRows(
  availableHeight: number,
  rowHeight: number,
  scrollbarReserve: number
): number {
  const available = Math.max(
    TRAFFIC_TABLE_MIN_BODY_HEIGHT,
    Math.floor(availableHeight)
  )
  if (!Number.isFinite(rowHeight) || rowHeight <= 0) return available

  const reserve = Number.isFinite(scrollbarReserve)
    ? Math.max(0, scrollbarReserve)
    : 0
  const completeRows = Math.floor((available - reserve) / rowHeight)
  if (completeRows < 1) return available

  return Math.floor(completeRows * rowHeight + reserve)
}
