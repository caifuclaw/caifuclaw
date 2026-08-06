/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { describe, expect, it } from 'vitest'

import type { PlatformSettingDto } from '@/api/system'
import { buildDeadlinePlatformOptions } from './deadlinePlatformOptions'

const platformSettings: PlatformSettingDto[] = [
  { id: 1, platform: 'ozon', platform_name: 'Ozon', enabled: true },
  { id: 2, platform: 'wildberries', platform_name: 'Wildberries', enabled: false },
  { id: 3, platform: 'joom_logistics', platform_name: 'Joom', enabled: true }
]

describe('buildDeadlinePlatformOptions', () => {
  it('shows enabled platforms in platform-list order and keeps the fallback rule', () => {
    expect(buildDeadlinePlatformOptions(platformSettings)).toEqual([
      { value: 'ozon', label: 'Ozon' },
      { value: 'joom_logistics', label: 'Joom' },
      { value: 'other', label: '其他' }
    ])
  })

  it('keeps the current disabled platform visible only for its existing rule', () => {
    expect(buildDeadlinePlatformOptions(platformSettings, 'wildberries', '旧名称')).toEqual([
      { value: 'ozon', label: 'Ozon' },
      { value: 'joom_logistics', label: 'Joom' },
      { value: 'wildberries', label: 'Wildberries' },
      { value: 'other', label: '其他' }
    ])
    expect(buildDeadlinePlatformOptions(platformSettings).map((item) => item.value)).not.toContain('wildberries')
  })

  it('keeps an unknown historical platform readable', () => {
    expect(buildDeadlinePlatformOptions(platformSettings, 'legacy_market', 'Legacy Market')).toContainEqual({
      value: 'legacy_market',
      label: 'Legacy Market'
    })
  })
})
