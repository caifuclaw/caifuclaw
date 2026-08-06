import { Tag } from 'antd'
import { ORDER_STATUS_COLOR } from '@/stores/dict'

export function StatusTag({ status, label }: { status?: string | null; label?: string | null }) {
  const value = status || '-'
  return <Tag color={ORDER_STATUS_COLOR[value] || 'default'}>{label || value}</Tag>
}
