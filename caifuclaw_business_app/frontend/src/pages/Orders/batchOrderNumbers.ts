/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

export const MAX_BATCH_ORDER_NUMBERS = 100
export const MAX_BATCH_ORDER_NUMBER_LENGTH = 160

export interface BatchOrderNumberParseResult {
  tokens: string[]
  uniqueNumbers: string[]
  duplicateCount: number
  tooLongNumbers: string[]
  overLimit: boolean
}

export function parseBatchOrderNumbers(text: string): BatchOrderNumberParseResult {
  const tokens = text
    .split(/[\r\n,，;；\t]+/)
    .map((value) => value.trim())
    .filter(Boolean)
  const uniqueNumbers = [...new Set(tokens)]

  return {
    tokens,
    uniqueNumbers,
    duplicateCount: tokens.length - uniqueNumbers.length,
    tooLongNumbers: uniqueNumbers.filter((value) => value.length > MAX_BATCH_ORDER_NUMBER_LENGTH),
    overLimit: uniqueNumbers.length > MAX_BATCH_ORDER_NUMBERS
  }
}
