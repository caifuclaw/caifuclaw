/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { useEffect, useMemo, useState } from 'react'

import { listTranslationLanguageOptions, type TranslationLanguageOptionDto } from '@/api/system'

export interface TranslationLanguageSelectOption {
  value: string
  label: string
}

let cachedOptions: TranslationLanguageSelectOption[] | null = null
let pendingRequest: Promise<TranslationLanguageSelectOption[]> | null = null

function toSelectOptions(items: TranslationLanguageOptionDto[] = []): TranslationLanguageSelectOption[] {
  return items
    .map((item) => ({ value: String(item.code || '').trim(), label: String(item.label || '').trim() }))
    .filter((item) => item.value && item.label)
}

function loadOptions() {
  if (cachedOptions) return Promise.resolve(cachedOptions)
  if (!pendingRequest) {
    pendingRequest = listTranslationLanguageOptions()
      .then((items) => {
        cachedOptions = toSelectOptions(items)
        return cachedOptions
      })
      .finally(() => {
        pendingRequest = null
      })
  }
  return pendingRequest
}

export function formatTranslationLanguageLabel(
  value?: string | null,
  options: TranslationLanguageSelectOption[] = []
) {
  const code = String(value || '').trim()
  if (!code) return ''
  return options.find((item) => item.value === code)?.label || code
}

export function useTranslationLanguageOptions() {
  const [options, setOptions] = useState<TranslationLanguageSelectOption[]>(cachedOptions || [])
  const [loading, setLoading] = useState(!cachedOptions)

  useEffect(() => {
    let active = true
    setLoading(!cachedOptions)
    loadOptions()
      .then((items) => {
        if (active) setOptions(items)
      })
      .catch(() => {
        if (active) setOptions([])
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  return useMemo(() => ({ options, loading }), [loading, options])
}
