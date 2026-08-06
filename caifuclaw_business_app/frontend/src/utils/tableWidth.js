export const DEFAULT_TABLE_COLUMN_MAX_WIDTH = 450
export const DEFAULT_TABLE_COLUMN_MIN_WIDTH = 72
export const DEFAULT_TABLE_CELL_EXTRA_WIDTH = 32
export const TABLE_EMPTY_TEXT = '-'

const measuredTextCache = new Map()
let measureCanvas

function fallbackTextWidth(text) {
  return Array.from(String(text ?? '')).reduce((total, char) => total + (char.charCodeAt(0) > 255 ? 14 : 7.5), 0)
}

function defaultTableFont() {
  if (typeof document === 'undefined' || typeof window === 'undefined') return '14px Arial'

  const source = document.querySelector('.data-table .ant-table-cell') || document.body
  const style = window.getComputedStyle(source)
  return `${style.fontStyle} ${style.fontVariant} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`
}

function clampWidth(width, minWidth, maxWidth) {
  const cap = Math.min(maxWidth ?? DEFAULT_TABLE_COLUMN_MAX_WIDTH, DEFAULT_TABLE_COLUMN_MAX_WIDTH)
  const floor = Math.min(Math.max(DEFAULT_TABLE_COLUMN_MIN_WIDTH, minWidth ?? DEFAULT_TABLE_COLUMN_MIN_WIDTH), cap)
  return Math.min(cap, Math.max(floor, Math.ceil(width)))
}

function widthOptions(minWidthOrOptions, maxWidth) {
  if (minWidthOrOptions && typeof minWidthOrOptions === 'object') {
    return {
      minWidth: minWidthOrOptions.minWidth,
      maxWidth: minWidthOrOptions.maxWidth,
      extraWidth: minWidthOrOptions.extraWidth,
      font: minWidthOrOptions.font,
      emptyText: minWidthOrOptions.emptyText
    }
  }

  return {
    minWidth: minWidthOrOptions,
    maxWidth,
    extraWidth: DEFAULT_TABLE_CELL_EXTRA_WIDTH,
    emptyText: TABLE_EMPTY_TEXT
  }
}

export function isEmptyTableValue(value) {
  if (value == null) return true
  if (typeof value === 'string') {
    const trimmed = value.trim()
    return trimmed === '' || trimmed === TABLE_EMPTY_TEXT
  }
  if (Array.isArray(value)) return value.length === 0
  return false
}

export function normalizeTableCellText(value, emptyText = TABLE_EMPTY_TEXT) {
  if (isEmptyTableValue(value)) return emptyText
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (value instanceof Date) return value.toISOString()
  if (Array.isArray(value)) {
    const text = value
      .map((item) => normalizeTableCellText(item, ''))
      .filter(Boolean)
      .join(', ')
    return text || emptyText
  }
  return String(value)
}

export function measureTextWidth(value, options = {}) {
  const text = String(value ?? '')
  if (!text) return 0

  const font = options.font || defaultTableFont()
  const cacheKey = `${font}\n${text}`
  const cached = measuredTextCache.get(cacheKey)
  if (cached != null) return cached

  let width = fallbackTextWidth(text)
  if (typeof document !== 'undefined') {
    measureCanvas ||= document.createElement('canvas')
    const context = measureCanvas.getContext('2d')
    if (context) {
      context.font = font
      width = context.measureText(text).width
    }
  }

  if (measuredTextCache.size > 5000) measuredTextCache.clear()
  measuredTextCache.set(cacheKey, width)
  return width
}

export function displayTextWidth(value, options) {
  return measureTextWidth(value == null ? '' : String(value), options)
}

export function contentColumnWidth(values, minWidthOrOptions, maxWidth) {
  const options = widthOptions(minWidthOrOptions, maxWidth)
  const extraWidth = options.extraWidth ?? DEFAULT_TABLE_CELL_EXTRA_WIDTH
  const emptyText = options.emptyText ?? TABLE_EMPTY_TEXT
  const maxTextWidth = values.reduce((largest, value) => {
    const text = normalizeTableCellText(value, emptyText)
    return Math.max(largest, measureTextWidth(text, { font: options.font }))
  }, 0)

  return clampWidth(maxTextWidth + extraWidth, options.minWidth, options.maxWidth)
}

export function autoColumnWidth(rows, label, getter, minWidthOrOptions, maxWidth) {
  const values = []

  for (const row of rows) {
    const value = typeof getter === 'function' ? getter(row) : row?.[getter]
    if (!isEmptyTableValue(value)) values.push(value)
  }

  return contentColumnWidth(values.length ? [label, ...values] : [label], minWidthOrOptions, maxWidth)
}
