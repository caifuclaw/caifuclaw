/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { del, get, put } from './http'

export interface TableColumnPreference {
  key: string
  visible?: boolean
  order?: number
  width?: number
  fixed?: 'left' | 'right' | boolean | null
}

export interface TablePreferenceConfig {
  schemaVersion: number
  widthMode: 'adaptive-left'
  columns: TableColumnPreference[]
}

export interface TablePreferenceDto {
  id: number | null
  table_key: string
  config_json: TablePreferenceConfig | null
  created_at: string | null
  updated_at: string | null
}

function encodedTableKey(tableKey: string) {
  return tableKey.split('/').map(encodeURIComponent).join('/')
}

export function fetchTablePreference(tableKey: string) {
  return get<TablePreferenceDto>(`/api/v1/table-preferences/${encodedTableKey(tableKey)}`, { background: true })
}

export function saveTablePreference(tableKey: string, config: TablePreferenceConfig) {
  return put<TablePreferenceDto>(
    `/api/v1/table-preferences/${encodedTableKey(tableKey)}`,
    { config_json: config },
    { background: true }
  )
}

export function resetTablePreference(tableKey: string) {
  return del<{ ok: boolean }>(`/api/v1/table-preferences/${encodedTableKey(tableKey)}`, { background: true })
}
