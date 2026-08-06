/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { useEffect, useMemo, useState } from 'react'
import { App, Checkbox, Select } from 'antd'
import { listShops, type ShopDto } from '@/api/shops'
import './ShopMultiSelect.less'

interface ShopMultiSelectProps {
  platform?: string
  value?: number[]
  onChange?: (value: number[]) => void
  className?: string
}

function normalizedPlatform(value?: string): string {
  return (value || '').trim().toLowerCase()
}

export function ShopMultiSelect({ platform, value = [], onChange, className }: ShopMultiSelectProps) {
  const { message } = App.useApp()
  const [shops, setShops] = useState<ShopDto[]>([])
  const [loading, setLoading] = useState(true)
  const [loadFailed, setLoadFailed] = useState(false)

  useEffect(() => {
    let active = true
    setLoading(true)
    setLoadFailed(false)
    listShops(
      { enabled: true, sort_by: 'display_name', sort_order: 'asc' },
      { background: true, silent: true }
    )
      .then((rows) => {
        if (active) setShops(rows)
      })
      .catch(() => {
        if (!active) return
        setLoadFailed(true)
        message.error('店铺列表加载失败，请刷新页面重试')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [message])

  const options = useMemo(() => {
    const selectedPlatform = normalizedPlatform(platform)
    return shops
      .filter((shop) => !selectedPlatform || normalizedPlatform(shop.platform) === selectedPlatform)
      .flatMap((shop) => {
        if (typeof shop.id !== 'number') return []
        const shopName = shop.display_name || shop.account_id || shop.shop_id
        return [{
          value: shop.id,
          label: shopName
        }]
      })
      .sort((left, right) => left.label.localeCompare(right.label, 'zh-CN'))
  }, [platform, shops])

  useEffect(() => {
    if (loading || loadFailed || !value.length) return
    const availableIds = new Set(options.map((option) => option.value))
    const nextValue = value.filter((shopId) => availableIds.has(shopId))
    if (nextValue.length !== value.length) onChange?.(nextValue)
  }, [loadFailed, loading, onChange, options, value])

  return (
    <Select<number[]>
      mode="multiple"
      aria-label="筛选店铺"
      allowClear
      showSearch
      optionFilterProp="label"
      placeholder={loadFailed ? '店铺加载失败' : '全部店铺'}
      value={value}
      options={options}
      loading={loading}
      disabled={loadFailed}
      maxTagCount={1}
      maxTagPlaceholder={() => `已选 ${value.length} 家`}
      menuItemSelectedIcon={null}
      optionRender={(option) => (
        <Checkbox
          className="shop-filter-option-checkbox"
          checked={value.includes(Number(option.value))}
          tabIndex={-1}
          aria-hidden
          onChange={() => undefined}
        >
          {option.label}
        </Checkbox>
      )}
      className={['shop-filter-select', className].filter(Boolean).join(' ')}
      onChange={(nextValue) => onChange?.(nextValue)}
    />
  )
}
