import { formatMoney } from '@/utils/format'

export function MoneyText({ amount, currency }: { amount?: number | string | null; currency?: string }) {
  return <span className="money-text tabular-nums">{formatMoney(amount, currency)}</span>
}
