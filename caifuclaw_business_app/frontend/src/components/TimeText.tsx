/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { formatTime, formatTimeUtc } from '@/utils/format'

export function TimeText({ value, utc = false, seconds = false }: { value?: string | number | Date | null; utc?: boolean; seconds?: boolean }) {
  const text = utc ? formatTimeUtc(value) : formatTime(value, seconds)
  return <span className="time-text tabular-nums">{text}</span>
}
