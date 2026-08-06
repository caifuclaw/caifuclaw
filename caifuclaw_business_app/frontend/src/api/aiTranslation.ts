/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { post } from './http'

export interface TextTranslationPayload {
  text: string
  source_language: string
  target_language: string
}

export interface TextTranslationResponse {
  status: string
  message: string
  request_id: string
  provider: string
  source_language: string
  target_language: string
  translated_text: string
  source_char_count: number
  translated_char_count: number
}

export function translateText(payload: TextTranslationPayload) {
  return post<TextTranslationResponse>('/api/v1/ai-translation/translate', payload, {
    timeout: 120000,
    retry: 0
  })
}
