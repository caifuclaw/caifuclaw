/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import http, { post } from './http'

export type AiImageOperation = 'generate' | 'edit' | 'split' | 'merge'

export interface AiImageAssetDto {
  name: string
  url: string
  oss_object_key: string
  width: number
  height: number
  format: string
  size_bytes: number
}

export interface AiImageProcessResponse {
  operation: AiImageOperation
  model_setting_id?: number | null
  model_setting_name?: string
  model?: string
  source_assets: AiImageAssetDto[]
  assets: AiImageAssetDto[]
}

export function processAiImage(payload: FormData) {
  return post<AiImageProcessResponse>('/api/v1/ai-image/process', payload, {
    timeout: 330000,
    retry: 0
  })
}

export async function downloadAiImage(asset: Pick<AiImageAssetDto, 'name' | 'oss_object_key'>) {
  const blob = await fetchAiImageBlob(asset)
  const objectUrl = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = asset.name || 'image'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
}

export async function fetchAiImageBlob(asset: Pick<AiImageAssetDto, 'name' | 'oss_object_key'>) {
  const response = await http.get<Blob>('/api/v1/ai-image/download', {
    params: {
      object_key: asset.oss_object_key,
      filename: asset.name
    },
    responseType: 'blob',
    timeout: 120000,
    retry: 0
  })
  return response.data
}

export async function downloadAiImagesZip(assets: Array<Pick<AiImageAssetDto, 'name' | 'oss_object_key'>>) {
  const response = await http.post<Blob>('/api/v1/ai-image/download-batch', {
    items: assets.map((asset) => ({ object_key: asset.oss_object_key, filename: asset.name }))
  }, {
    responseType: 'blob',
    timeout: 300000,
    retry: 0
  })
  const objectUrl = URL.createObjectURL(response.data)
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = `ai-images-${new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '')}.zip`
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
}
