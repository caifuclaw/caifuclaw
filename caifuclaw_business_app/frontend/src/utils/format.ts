import dayjs from 'dayjs'

export function formatTime(value?: string | number | Date | null, withSeconds = false): string {
  if (!value) return '-'
  const d = dayjs(value)
  if (!d.isValid()) return '-'
  return d.format(withSeconds ? 'YYYY-MM-DD HH:mm:ss' : 'YYYY-MM-DD HH:mm')
}

export function formatDate(value?: string | number | Date | null): string {
  if (!value) return '-'
  const d = dayjs(value)
  if (!d.isValid()) return '-'
  return d.format('YYYY-MM-DD')
}

export function formatTimeUtc(value?: string | number | Date | null): string {
  if (!value) return '-'
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())} ` +
    `${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}:${pad(date.getUTCSeconds())} UTC`
  )
}

export function formatRemainHours(deadlineUtc?: string | number | Date | null): {
  hours: number
  text: string
  level: 'overdue' | 'warning' | 'ok' | 'unknown'
} {
  if (!deadlineUtc) return { hours: 0, text: '-', level: 'unknown' }
  const d = dayjs(deadlineUtc)
  if (!d.isValid()) return { hours: 0, text: '-', level: 'unknown' }
  const diffMinutes = d.diff(dayjs(), 'minute')
  const hours = diffMinutes / 60
  if (hours <= 0) {
    return { hours, text: `已超时 ${Math.ceil(-hours)}h`, level: 'overdue' }
  }
  if (hours <= 24) {
    const intH = Math.floor(hours)
    const m = Math.max(0, diffMinutes - intH * 60)
    return { hours, text: m > 0 ? `${intH}h${m}m` : `${intH}h`, level: 'warning' }
  }
  const days = Math.floor(hours / 24)
  return { hours, text: `${days}d ${Math.floor(hours % 24)}h`, level: 'ok' }
}

const moneyFormatterCache = new Map<string, Intl.NumberFormat>()

export function formatMoney(amount?: number | string | null, currency = 'CNY'): string {
  if (amount == null || amount === '') return '-'
  const num = typeof amount === 'string' ? Number(amount) : amount
  if (Number.isNaN(num)) return '-'
  let fmt = moneyFormatterCache.get(currency)
  if (!fmt) {
    try {
      fmt = new Intl.NumberFormat('zh-CN', {
        style: 'currency',
        currency,
        currencyDisplay: 'symbol'
      })
      moneyFormatterCache.set(currency, fmt)
    } catch {
      fmt = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    }
  }
  return fmt.format(num)
}

export function formatNumber(num?: number | string | null, fractionDigits = 0): string {
  if (num == null || num === '') return '-'
  const n = typeof num === 'string' ? Number(num) : num
  if (Number.isNaN(n)) return '-'
  return n.toLocaleString('zh-CN', {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits
  })
}

export function truncate(text?: string | null, max = 20): string {
  if (!text) return '-'
  return text.length > max ? `${text.slice(0, max)}...` : text
}
