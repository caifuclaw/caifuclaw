import { useEffect, useMemo, useState } from 'react'

import { listPlatformSettings, type PlatformSettingDto } from '@/api/system'
import { formatPlatformLabel } from '@/stores/dict'

export interface EnabledPlatformOption {
  value: string
  label: string
}

function platformLabel(item: PlatformSettingDto) {
  return item.platform_name || formatPlatformLabel(item.platform)
}

export function platformSettingsToOptions(items: PlatformSettingDto[] = []): EnabledPlatformOption[] {
  const options = new Map<string, EnabledPlatformOption>()
  for (const item of items) {
    const platform = (item.platform || '').trim()
    if (!platform) continue
    if (item.enabled === false) continue
    options.set(platform, { value: platform, label: platformLabel(item) })
  }
  return Array.from(options.values())
}

export function useEnabledPlatformOptions() {
  const [platforms, setPlatforms] = useState<PlatformSettingDto[]>([])

  useEffect(() => {
    let active = true
    listPlatformSettings()
      .then((data) => {
        if (active) setPlatforms(data || [])
      })
      .catch(() => {
        if (active) setPlatforms([])
      })
    return () => {
      active = false
    }
  }, [])

  return useMemo(() => platformSettingsToOptions(platforms), [platforms])
}
