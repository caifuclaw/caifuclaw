/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import type { PlatformSettingDto } from '@/api/system'
import { platformSettingsToOptions, type EnabledPlatformOption } from '@/hooks/useEnabledPlatformOptions'
import { formatPlatformLabel } from '@/stores/dict'

export const OTHER_DEADLINE_PLATFORM_OPTION: EnabledPlatformOption = { value: 'other', label: '其他' }

export function buildDeadlinePlatformOptions(
  platformSettings: PlatformSettingDto[],
  currentPlatform?: string,
  currentPlatformName?: string
): EnabledPlatformOption[] {
  const options = new Map(
    platformSettingsToOptions(platformSettings).map((item) => [item.value, item])
  )
  const platform = (currentPlatform || '').trim()

  if (platform && platform !== OTHER_DEADLINE_PLATFORM_OPTION.value && !options.has(platform)) {
    const setting = platformSettings.find((item) => item.platform === platform)
    options.set(platform, {
      value: platform,
      label: setting?.platform_name || currentPlatformName || formatPlatformLabel(platform)
    })
  }

  options.set(OTHER_DEADLINE_PLATFORM_OPTION.value, OTHER_DEADLINE_PLATFORM_OPTION)
  return [...options.values()]
}
