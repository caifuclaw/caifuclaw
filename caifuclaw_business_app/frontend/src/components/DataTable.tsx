/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { isValidElement, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type {
  CSSProperties,
  KeyboardEvent as ReactKeyboardEvent,
  PointerEvent as ReactPointerEvent,
  ReactNode
} from 'react'
import { Button, Checkbox, Empty, Input, Modal, Space, Table as AntTable, Tooltip } from 'antd'
import { CloseOutlined, HolderOutlined, ReloadOutlined, SearchOutlined, SettingOutlined, VerticalAlignTopOutlined } from '@ant-design/icons'
import type { TableProps } from 'antd'
import type { ColumnGroupType, ColumnType, ColumnsType } from 'antd/es/table'
import {
  fetchTablePreference,
  resetTablePreference,
  saveTablePreference,
  type TableColumnPreference,
  type TablePreferenceConfig
} from '@/api/tablePreferences'
import {
  DEFAULT_TABLE_CELL_EXTRA_WIDTH,
  DEFAULT_TABLE_COLUMN_MAX_WIDTH,
  DEFAULT_TABLE_COLUMN_MIN_WIDTH,
  contentColumnWidth,
  isEmptyTableValue,
  measureTextWidth,
  normalizeTableCellText
} from '@/utils/tableWidth'

const MAX_COLUMN_WIDTH = DEFAULT_TABLE_COLUMN_MAX_WIDTH
const MIN_COLUMN_WIDTH = DEFAULT_TABLE_COLUMN_MIN_WIDTH
const ADAPTIVE_TEXT_EXTRA_WIDTH = 24
const TABLE_MIN_BODY_HEIGHT = 160
const TABLE_HEADER_FALLBACK_HEIGHT = 48
const TABLE_BOTTOM_RESERVE = 28
const TABLE_PAGINATION_RESERVE = 46
const TABLET_BREAKPOINT = 1024
const MOBILE_BREAKPOINT = 640
const HORIZONTAL_SCROLLBAR_MIN_THUMB_WIDTH = 32

type DataTableBreakpoint = 'mobile' | 'tablet' | 'desktop'

type ResponsiveWidth = Partial<Record<DataTableBreakpoint, number>>

export type DataTableColumnType<RecordType> = ColumnType<RecordType> & {
  minWidth?: number
  maxWidth?: number
  flex?: number
  responsiveWidth?: ResponsiveWidth
  userFixedWidth?: boolean
  showFullTextOnHover?: boolean
}

export type DataTableColumnGroupType<RecordType> = Omit<ColumnGroupType<RecordType>, 'children'> & {
  children: DataTableColumnsType<RecordType>
}

export type DataTableColumnsType<RecordType> = Array<
  DataTableColumnType<RecordType> | DataTableColumnGroupType<RecordType>
>

export type DataTableWidthMode = 'adaptive-left'
export type DataTableColumnFixed = 'left' | 'right' | boolean | null

export interface DataTableVisibleColumn {
  key: string
  title: string
}

export interface DataTableColumnConfig {
  key: string
  title?: ReactNode
  required?: boolean
  settingsHidden?: boolean
  visible?: boolean
  order?: number
  width?: number
  minWidth?: number
  maxWidth?: number
  fixed?: DataTableColumnFixed
  protectedWidth?: number
}

export interface DataTableConfig {
  tableKey: string
  primaryColumnKey: string
  widthMode?: DataTableWidthMode
  columns: DataTableColumnConfig[]
}

export type DataTableProps<RecordType extends object = Record<string, unknown>> = Omit<
  TableProps<RecordType>,
  'columns'
> & {
  columns?: DataTableColumnsType<RecordType>
  fitContainerHeight?: boolean
  fitContentColumns?: boolean
  persistentHorizontalScrollbar?: boolean
  showSelectionFooter?: boolean
  tableConfig?: DataTableConfig
  showColumnSettingsButton?: boolean
  columnSettingsOpen?: boolean
  onColumnSettingsOpenChange?: (open: boolean) => void
  onVisibleColumnsChange?: (columns: DataTableVisibleColumn[]) => void
  showFullTextOnHover?: boolean
}

type DataTableColumn<RecordType> = DataTableColumnsType<RecordType>[number]

interface LeafSizing<RecordType> {
  column: DataTableColumnType<RecordType>
  minWidth: number
  maxWidth: number
  flex: number
}

interface RenderedCellMeasurement {
  value: unknown
  interactive: boolean
}

interface EffectiveColumnPreference {
  key: string
  visible: boolean
  order: number
  width?: number
  fixed?: DataTableColumnFixed
}

interface HorizontalScrollState {
  visible: boolean
  scrollLeft: number
  scrollWidth: number
  clientWidth: number
}

const noWrapCellStyle: CSSProperties = {
  maxWidth: MAX_COLUMN_WIDTH,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap'
}

const defaultHorizontalScrollState: HorizontalScrollState = {
  visible: false,
  scrollLeft: 0,
  scrollWidth: 0,
  clientWidth: 0
}

const preferenceSaveTimers = new Map<string, number>()
const preferenceSavePromises = new Map<string, Promise<unknown>>()
const preferenceSaveVersions = new Map<string, number>()

function currentPreferenceSaveVersion(tableKey: string): number {
  return preferenceSaveVersions.get(tableKey) ?? 0
}

function invalidatePreferenceSaves(tableKey: string) {
  preferenceSaveVersions.set(tableKey, currentPreferenceSaveVersion(tableKey) + 1)
  const currentTimer = preferenceSaveTimers.get(tableKey)
  if (currentTimer) {
    window.clearTimeout(currentTimer)
    preferenceSaveTimers.delete(tableKey)
  }
}

function savePreferenceNow(tableKey: string, config: TablePreferenceConfig, version = currentPreferenceSaveVersion(tableKey)) {
  if (currentPreferenceSaveVersion(tableKey) !== version) return Promise.resolve()
  const savePromise = saveTablePreference(tableKey, config)
    .catch(() => undefined)
    .finally(() => {
      if (preferenceSavePromises.get(tableKey) === savePromise) {
        preferenceSavePromises.delete(tableKey)
      }
    })
  preferenceSavePromises.set(tableKey, savePromise)
  return savePromise
}

function isColumnGroup<RecordType>(
  column: DataTableColumn<RecordType>
): column is DataTableColumnGroupType<RecordType> {
  return Array.isArray((column as DataTableColumnGroupType<RecordType>).children)
}

function parseWidth(width: ColumnType<unknown>['width']): number | undefined {
  if (typeof width === 'number' && Number.isFinite(width)) return width
  if (typeof width === 'string') {
    const matched = width.match(/^(\d+(?:\.\d+)?)px$/)
    if (matched) return Number(matched[1])
  }
  return undefined
}

function columnKey<RecordType>(column: DataTableColumnType<RecordType>): string | undefined {
  if (column.key != null) return String(column.key)
  if (column.dataIndex == null) return undefined
  return Array.isArray(column.dataIndex) ? column.dataIndex.map(String).join('.') : String(column.dataIndex)
}

function columnsWithFullTextHover<RecordType>(
  columns: DataTableColumnsType<RecordType> | undefined,
  enabled: boolean
): DataTableColumnsType<RecordType> | undefined {
  if (!columns || !enabled) return columns
  return columns.map((column) => {
    if (isColumnGroup(column)) {
      return {
        ...column,
        children: columnsWithFullTextHover(column.children, true) || []
      }
    }
    return {
      ...column,
      showFullTextOnHover: columnKey(column) !== 'actions'
    }
  })
}

function fixedValue(value: DataTableColumnFixed | undefined): DataTableColumnFixed | undefined {
  if (value === 'left' || value === 'right' || value === true || value === false || value == null) return value
  return undefined
}

function normalizedColumnConfig(config: DataTableConfig | undefined): DataTableConfig | undefined {
  if (!config) return undefined
  const primaryColumnKey = config.primaryColumnKey
  return {
    ...config,
    widthMode: config.widthMode ?? 'adaptive-left',
    columns: config.columns.map((column, index) => {
      const required = column.required || column.key === primaryColumnKey
      const settingsHidden = column.settingsHidden ?? column.key === 'actions'
      return {
        ...column,
        required,
        settingsHidden,
        visible: column.visible ?? true,
        order: column.order ?? index + 1,
        fixed: fixedValue(column.fixed ?? (column.key === primaryColumnKey ? 'left' : column.key === 'actions' ? 'right' : undefined))
      }
    })
  }
}

function preferenceConfigFromColumns(config: DataTableConfig, columns: EffectiveColumnPreference[]): TablePreferenceConfig {
  return {
    schemaVersion: 1,
    widthMode: config.widthMode ?? 'adaptive-left',
    columns: columns.map((column) => ({
      key: column.key,
      visible: column.visible,
      order: column.order,
      width: column.width,
      fixed: column.fixed ?? undefined
    }))
  }
}

function mergedPreferences(
  config: DataTableConfig | undefined,
  userConfig: TablePreferenceConfig | null | undefined
): EffectiveColumnPreference[] {
  if (!config) return []
  const userColumns = new Map<string, TableColumnPreference>()
  userConfig?.columns?.forEach((column) => {
    if (column?.key) userColumns.set(column.key, column)
  })
  const hasUserColumns = userColumns.size > 0
  const maxUserOrder = Array.from(userColumns.values()).reduce((maxOrder, column) => {
    return Number.isFinite(column.order) ? Math.max(maxOrder, Number(column.order)) : maxOrder
  }, 0)
  let appendedOrder = maxUserOrder

  return config.columns.map((column, index) => {
    const userColumn = userColumns.get(column.key)
    const required = !!column.required || column.key === config.primaryColumnKey
    const forceVisible = required || !!column.settingsHidden
    const order = column.settingsHidden
      ? hasUserColumns
        ? ++appendedOrder
        : column.order ?? index + 1
      : userColumn
        ? Number.isFinite(userColumn.order)
          ? Number(userColumn.order)
          : column.order ?? index + 1
        : hasUserColumns
          ? ++appendedOrder
          : column.order ?? index + 1
    return {
      key: column.key,
      visible: forceVisible ? true : userColumn?.visible ?? column.visible ?? true,
      order,
      width: typeof userColumn?.width === 'number' && Number.isFinite(userColumn.width) ? userColumn.width : column.width,
      fixed: fixedValue(
        column.settingsHidden
          ? column.fixed ?? (column.key === 'actions' ? 'right' : undefined)
          : userColumn?.fixed ?? column.fixed ?? (column.key === config.primaryColumnKey ? 'left' : undefined)
      )
    }
  })
}

function schedulePreferenceSave(tableKey: string, config: TablePreferenceConfig) {
  const currentTimer = preferenceSaveTimers.get(tableKey)
  if (currentTimer) window.clearTimeout(currentTimer)
  const saveVersion = currentPreferenceSaveVersion(tableKey)
  const timer = window.setTimeout(() => {
    preferenceSaveTimers.delete(tableKey)
    savePreferenceNow(tableKey, config, saveVersion)
  }, 450)
  preferenceSaveTimers.set(tableKey, timer)
}

function clampColumnWidth(width: number, minWidth = MIN_COLUMN_WIDTH, maxWidth = MAX_COLUMN_WIDTH): number {
  const min = Math.max(MIN_COLUMN_WIDTH, minWidth)
  const max = Math.max(min, maxWidth)
  return Math.min(max, Math.max(min, Math.ceil(width)))
}

function dataTableBreakpoint(width: number): DataTableBreakpoint {
  if (width < MOBILE_BREAKPOINT) return 'mobile'
  if (width < TABLET_BREAKPOINT) return 'tablet'
  return 'desktop'
}

function titleText(title: ReactNode): string {
  if (title == null || typeof title === 'boolean') return ''
  if (typeof title === 'string' || typeof title === 'number') return String(title)
  if (Array.isArray(title)) return title.map(titleText).join('')
  if (isValidElement(title)) return titleText(title.props.children)
  return ''
}

function valueByDataIndex<RecordType>(record: RecordType, dataIndex: ColumnType<RecordType>['dataIndex']): unknown {
  if (dataIndex == null) return ''
  const path = Array.isArray(dataIndex) ? dataIndex : String(dataIndex).split('.')
  return path.reduce<unknown>((current, key) => {
    if (current == null) return ''
    return (current as Record<string, unknown>)[String(key)]
  }, record)
}

function renderNodeText(value: ReactNode): string {
  if (value == null || typeof value === 'boolean') return ''
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  if (Array.isArray(value)) return value.map(renderNodeText).join('')
  if (isValidElement(value)) return renderNodeText(value.props.children)
  return ''
}

function reactElementTypeName(type: unknown): string {
  if (typeof type === 'string') return type
  if (typeof type === 'function') {
    const namedType = type as { displayName?: string; name?: string }
    return namedType.displayName || namedType.name || ''
  }
  if (type && typeof type === 'object') {
    const namedType = type as { displayName?: string; name?: string; render?: { displayName?: string; name?: string } }
    return namedType.displayName || namedType.name || namedType.render?.displayName || namedType.render?.name || ''
  }
  return ''
}

function isInteractiveNode(value: unknown): boolean {
  if (value == null || typeof value === 'boolean' || typeof value === 'string' || typeof value === 'number') return false
  if (Array.isArray(value)) return value.some(isInteractiveNode)
  if (!isValidElement(value)) return false

  const typeName = reactElementTypeName(value.type).toLowerCase()
  if (['a', 'button', 'input', 'select', 'textarea'].includes(typeName)) return true
  if (/(button|input|select|checkbox|radio|switch|picker|upload|dropdown|popconfirm)/.test(typeName)) return true

  const props = value.props as {
    children?: ReactNode
    href?: unknown
    onClick?: unknown
    onChange?: unknown
    onSelect?: unknown
    onSearch?: unknown
  }
  if (props.href) return true
  if (props.onClick || props.onChange || props.onSelect || props.onSearch) return true
  return isInteractiveNode(props.children)
}

function renderedCellMeasurement<RecordType>(
  column: DataTableColumnType<RecordType>,
  record: RecordType,
  rowIndex: number
): RenderedCellMeasurement {
  const rawValue = valueByDataIndex(record, column.dataIndex)
  if (!column.render) return { value: rawValue, interactive: false }

  const rendered = column.render(rawValue, record, rowIndex)
  if (
    rendered &&
    typeof rendered === 'object' &&
    !isValidElement(rendered) &&
    ('children' in rendered || 'props' in rendered)
  ) {
    const cell = rendered as { children?: ReactNode; props?: { children?: ReactNode } }
    const children = cell.children ?? cell.props?.children
    return { value: renderNodeText(children), interactive: isInteractiveNode(children) }
  }

  if (isValidElement(rendered) || Array.isArray(rendered)) {
    const text = renderNodeText(rendered as ReactNode)
    return {
      value: text || rawValue,
      interactive: isInteractiveNode(rendered)
    }
  }
  return { value: rendered, interactive: false }
}

function estimateColumnWidth<RecordType>(
  column: DataTableColumnType<RecordType>,
  data: readonly RecordType[],
  fitContentColumns: boolean
): number {
  const explicitWidth = parseWidth(column.width as ColumnType<unknown>['width'])
  const minWidth = column.minWidth ?? MIN_COLUMN_WIDTH
  const maxWidth = column.userFixedWidth
    ? Math.max(explicitWidth ?? 0, column.maxWidth ?? MAX_COLUMN_WIDTH)
    : column.maxWidth ?? MAX_COLUMN_WIDTH
  const values: unknown[] = []
  let hasInteractiveContent = false

  if (column.userFixedWidth && explicitWidth) {
    return clampColumnWidth(explicitWidth, minWidth, maxWidth)
  }

  if (column.dataIndex != null || column.render) {
    for (const [rowIndex, row] of data.entries()) {
      const measurement = renderedCellMeasurement(column, row, rowIndex)
      const value = measurement.value
      hasInteractiveContent ||= measurement.interactive
      if (!isEmptyTableValue(value)) values.push(value)
    }
  }

  const width = contentColumnWidth([titleText(column.title as ReactNode), ...values], {
    minWidth,
    maxWidth,
    extraWidth: fitContentColumns && !hasInteractiveContent ? ADAPTIVE_TEXT_EXTRA_WIDTH : DEFAULT_TABLE_CELL_EXTRA_WIDTH
  })

  if (fitContentColumns) {
    if (hasInteractiveContent && explicitWidth) {
      return clampColumnWidth(Math.max(width, explicitWidth), minWidth, maxWidth)
    }
    return width
  }
  return explicitWidth ? clampColumnWidth(Math.max(width, explicitWidth), minWidth, maxWidth) : width
}

function noWrapStyle(width: number): CSSProperties {
  return {
    ...noWrapCellStyle,
    maxWidth: width
  }
}

function bodyCellTitle<RecordType>(
  record: RecordType,
  column: DataTableColumnType<RecordType>,
  rowIndex?: number
): string | undefined {
  if (column.dataIndex == null && !column.render) return undefined
  const measurement = renderedCellMeasurement(column, record, rowIndex ?? 0)
  if (!column.showFullTextOnHover && (column.dataIndex == null || measurement.interactive)) return undefined
  const text = normalizeTableCellText(measurement.value)
  return text === '-' ? undefined : text
}

function withNoWrap<RecordType>(column: DataTableColumnType<RecordType>, width: number): ColumnType<RecordType> {
  const onCell = column.onCell
  const onHeaderCell = column.onHeaderCell
  const minWidth = column.minWidth ?? MIN_COLUMN_WIDTH
  return {
    ...column,
    width,
    ellipsis: column.ellipsis ?? { showTitle: true },
    onCell: (record, rowIndex) => {
      const cell = onCell?.(record, rowIndex) || {}
      const title = bodyCellTitle(record, column, rowIndex)
      return {
        ...cell,
        title: cell.title ?? title,
        style: { ...(cell.style || {}), ...noWrapStyle(width) }
      }
    },
    onHeaderCell: (col) => {
      const cell = onHeaderCell?.(col) || {}
      return {
        ...cell,
        title: cell.title ?? (column.showFullTextOnHover ? titleText(column.title as ReactNode) || undefined : undefined),
        style: { ...(cell.style || {}), ...noWrapStyle(width) },
        width,
        minWidth,
        maxWidth: column.maxWidth ?? MAX_COLUMN_WIDTH
      }
    }
  }
}

function hasAdaptiveSizing<RecordType>(columns: DataTableColumnsType<RecordType>): boolean {
  return columns.some((column) => {
    if (isColumnGroup(column)) return hasAdaptiveSizing(column.children)
    return (
      column.minWidth != null ||
      column.maxWidth != null ||
      column.flex != null ||
      column.responsiveWidth != null
    )
  })
}

function responsiveColumnWidth<RecordType>(
  column: DataTableColumnType<RecordType>,
  breakpoint: DataTableBreakpoint
): number | undefined {
  return column.responsiveWidth?.[breakpoint]
}

function baseColumnWidth<RecordType>(
  column: DataTableColumnType<RecordType>,
  data: readonly RecordType[],
  breakpoint: DataTableBreakpoint,
  fitContentColumns: boolean
): number {
  const responsiveWidth = responsiveColumnWidth(column, breakpoint)
  const explicitWidth = parseWidth(column.width as ColumnType<unknown>['width'])
  const maxWidth = column.maxWidth ?? MAX_COLUMN_WIDTH
  const contentWidth = estimateColumnWidth(column, data, fitContentColumns)
  const titleWidth = clampColumnWidth(
    measureTextWidth(titleText(column.title as ReactNode)) +
      (fitContentColumns ? ADAPTIVE_TEXT_EXTRA_WIDTH : DEFAULT_TABLE_CELL_EXTRA_WIDTH),
    MIN_COLUMN_WIDTH,
    maxWidth
  )

  if (column.userFixedWidth && explicitWidth) {
    return clampColumnWidth(explicitWidth, column.minWidth ?? MIN_COLUMN_WIDTH, Math.max(explicitWidth, maxWidth))
  }

  if ((column.flex ?? 0) > 0) {
    const minWidth = column.minWidth ?? (fitContentColumns ? undefined : responsiveWidth ?? explicitWidth) ?? MIN_COLUMN_WIDTH
    return clampColumnWidth(Math.max(minWidth, contentWidth, titleWidth), minWidth, maxWidth)
  }

  if (responsiveWidth != null || explicitWidth != null || column.minWidth != null) {
    const width = fitContentColumns
      ? Math.max(column.minWidth ?? 0, contentWidth, titleWidth)
      : Math.max(responsiveWidth ?? 0, explicitWidth ?? 0, column.minWidth ?? 0, contentWidth, titleWidth)
    return clampColumnWidth(width, column.minWidth ?? MIN_COLUMN_WIDTH, maxWidth)
  }

  return contentWidth
}

function collectLeafSizing<RecordType>(
  columns: DataTableColumnsType<RecordType>,
  data: readonly RecordType[],
  breakpoint: DataTableBreakpoint,
  fitContentColumns: boolean
): Array<LeafSizing<RecordType>> {
  return columns.flatMap((column) => {
    if (isColumnGroup(column)) return collectLeafSizing(column.children, data, breakpoint, fitContentColumns)
    const minWidth = baseColumnWidth(column, data, breakpoint, fitContentColumns)
    return [
      {
        column,
        minWidth,
        maxWidth: Math.max(minWidth, column.maxWidth ?? MAX_COLUMN_WIDTH),
        flex: fitContentColumns ? 0 : Math.max(0, column.flex ?? 0)
      }
    ]
  })
}

function adaptiveColumnWidths<RecordType>(
  columns: DataTableColumnsType<RecordType>,
  data: readonly RecordType[],
  containerWidth: number,
  reservedWidth: number,
  fitContentColumns: boolean
): Map<DataTableColumnType<RecordType>, number> {
  const breakpoint = dataTableBreakpoint(containerWidth)
  const leaves = collectLeafSizing(columns, data, breakpoint, fitContentColumns)
  const widths = new Map<DataTableColumnType<RecordType>, number>()
  const availableWidth = Math.max(0, containerWidth - reservedWidth)
  const minTableWidth = leaves.reduce((total, leaf) => total + leaf.minWidth, 0)
  const flexLeaves = leaves.filter((leaf) => leaf.flex > 0)

  leaves.forEach((leaf) => widths.set(leaf.column, leaf.minWidth))

  if (flexLeaves.length && minTableWidth < availableWidth) {
    const remainingWidth = availableWidth - minTableWidth
    const totalFlex = flexLeaves.reduce((total, leaf) => total + leaf.flex, 0)
    let usedExtra = 0

    flexLeaves.forEach((leaf) => {
      const extra = remainingWidth * (leaf.flex / totalFlex)
      const width = clampColumnWidth(leaf.minWidth + extra, leaf.minWidth, leaf.maxWidth)
      widths.set(leaf.column, width)
      usedExtra += width - leaf.minWidth
    })

    if (usedExtra > 0 && minTableWidth + usedExtra > availableWidth) {
      flexLeaves.forEach((leaf) => widths.set(leaf.column, leaf.minWidth))
    }
  }

  return widths
}

function applyColumnWidths<RecordType>(
  columns: DataTableColumnsType<RecordType>,
  widths: Map<DataTableColumnType<RecordType>, number>
): ColumnsType<RecordType> {
  return columns.map((column) => {
    if (isColumnGroup(column)) {
      return {
        ...column,
        children: applyColumnWidths(column.children, widths)
      }
    }
    return withNoWrap(column, widths.get(column) ?? MIN_COLUMN_WIDTH)
  })
}

function normalizeColumns<RecordType>(
  columns: DataTableColumnsType<RecordType> | undefined,
  data: readonly RecordType[],
  containerWidth: number,
  reservedWidth: number,
  fitContentColumns: boolean
): ColumnsType<RecordType> {
  const sourceColumns = columns || []

  if (containerWidth > 0 && hasAdaptiveSizing(sourceColumns)) {
    return applyColumnWidths(
      sourceColumns,
      adaptiveColumnWidths(sourceColumns, data, containerWidth, reservedWidth, fitContentColumns)
    )
  }

  return sourceColumns.map((column) => {
    if (isColumnGroup(column)) {
      return {
        ...column,
        children: normalizeColumns(column.children, data, containerWidth, reservedWidth, fitContentColumns)
      }
    }
    const width = estimateColumnWidth(column, data, fitContentColumns)
    return withNoWrap(column, width)
  })
}

function flattenDataColumns<RecordType>(
  columns: DataTableColumnsType<RecordType> | undefined
): Array<DataTableColumnType<RecordType>> {
  return (columns || []).flatMap((column) => (isColumnGroup(column) ? flattenDataColumns(column.children) : [column]))
}

function widthMemoryKey<RecordType>(
  column: DataTableColumnType<RecordType>,
  containerWidth: number,
  rowSelectionColumnWidth: number,
  fitContentColumns: boolean
): string {
  return [
    columnKey(column) ?? titleText(column.title as ReactNode),
    containerWidth,
    rowSelectionColumnWidth,
    fitContentColumns ? 'fit' : 'flow',
    parseWidth(column.width as ColumnType<unknown>['width']) ?? '',
    column.minWidth ?? '',
    column.maxWidth ?? '',
    column.flex ?? '',
    JSON.stringify(column.responsiveWidth ?? {})
  ].join('|')
}

function widthMemorySignature<RecordType>(
  columns: DataTableColumnsType<RecordType> | undefined,
  data: readonly RecordType[],
  containerWidth: number,
  rowSelectionColumnWidth: number,
  fitContentColumns: boolean,
  resetVersion = 0
): string {
  const dataColumns = flattenDataColumns(columns)
  const columnParts = dataColumns.map((column) =>
    [
      widthMemoryKey(column, containerWidth, rowSelectionColumnWidth, fitContentColumns),
      titleText(column.title as ReactNode)
    ].join(':')
  )
  const dataParts = data.map((row, rowIndex) =>
    dataColumns
      .map((column) => {
        const key = columnKey(column)
        const value = column.dataIndex == null ? '' : valueByDataIndex(row, column.dataIndex)
        return `${key ?? ''}:${normalizeTableCellText(value)}:${rowIndex}`
      })
      .join(',')
  )
  return [resetVersion, ...columnParts, ...dataParts].join('|')
}

function rememberColumnWidths<RecordType>(
  columns: ColumnsType<RecordType>,
  sourceColumns: DataTableColumnsType<RecordType> | undefined,
  containerWidth: number,
  rowSelectionColumnWidth: number,
  fitContentColumns: boolean,
  memory: Map<string, number>
) {
  const sourceColumnMap = new Map(flattenDataColumns(sourceColumns).map((column) => [columnKey(column), column]))
  flattenDataColumns(columns as DataTableColumnsType<RecordType>).forEach((column) => {
    const key = columnKey(column)
    const sourceColumn = sourceColumnMap.get(key)
    if (!sourceColumn) return
    const width = parseWidth(column.width as ColumnType<unknown>['width'])
    if (width) memory.set(widthMemoryKey(sourceColumn, containerWidth, rowSelectionColumnWidth, fitContentColumns), width)
  })
}

function applyRememberedWidths<RecordType>(
  columns: ColumnsType<RecordType>,
  sourceColumns: DataTableColumnsType<RecordType> | undefined,
  containerWidth: number,
  rowSelectionColumnWidth: number,
  fitContentColumns: boolean,
  memory: Map<string, number>
): ColumnsType<RecordType> {
  const sourceColumnMap = new Map(flattenDataColumns(sourceColumns).map((column) => [columnKey(column), column]))
  return columns.map((column) => {
    if (isColumnGroup(column)) {
      return {
        ...column,
        children: applyRememberedWidths(
          column.children,
          sourceColumns,
          containerWidth,
          rowSelectionColumnWidth,
          fitContentColumns,
          memory
        )
      }
    }
    const key = columnKey(column as DataTableColumnType<RecordType>)
    const sourceColumn = sourceColumnMap.get(key)
    if (!sourceColumn) return column
    const rememberedWidth = memory.get(widthMemoryKey(sourceColumn, containerWidth, rowSelectionColumnWidth, fitContentColumns))
    return rememberedWidth ? withNoWrap(column as DataTableColumnType<RecordType>, rememberedWidth) : column
  })
}

function leafWidth<RecordType>(columns: ColumnsType<RecordType>): number {
  return columns.reduce((total, column) => {
    if (isColumnGroup(column)) return total + leafWidth(column.children)
    return total + (parseWidth(column.width as ColumnType<unknown>['width']) || MIN_COLUMN_WIDTH)
  }, 0)
}

function releaseRightFixedColumns<RecordType>(columns: ColumnsType<RecordType>): ColumnsType<RecordType> {
  return columns.map((column) => {
    if (isColumnGroup(column)) {
      return {
        ...column,
        children: releaseRightFixedColumns(column.children)
      }
    }
    if ((column as ColumnType<RecordType>).fixed !== 'right' || columnKey(column as DataTableColumnType<RecordType>) === 'actions') return column
    return {
      ...column,
      fixed: undefined
    }
  })
}

function antTableColumns<RecordType>(columns: ColumnsType<RecordType>): ColumnsType<RecordType> {
  return columns.map((column) => {
    const {
      minWidth: _minWidth,
      maxWidth: _maxWidth,
      flex: _flex,
      responsiveWidth: _responsiveWidth,
      userFixedWidth: _userFixedWidth,
      showFullTextOnHover: _showFullTextOnHover,
      ...rest
    } = column as DataTableColumnType<RecordType>

    if (isColumnGroup(column)) {
      return {
        ...(rest as ColumnGroupType<RecordType>),
        children: antTableColumns(column.children)
      }
    }

    return rest as ColumnType<RecordType>
  })
}

function applyPreferencesToColumns<RecordType>(
  columns: DataTableColumnsType<RecordType> | undefined,
  config: DataTableConfig | undefined,
  preferences: EffectiveColumnPreference[]
): DataTableColumnsType<RecordType> | undefined {
  if (!columns || !config) return columns

  const systemColumns = new Map(config.columns.map((column) => [column.key, column]))
  const columnMap = new Map<string, DataTableColumnType<RecordType>>()

  for (const column of columns) {
    if (isColumnGroup(column)) continue
    const key = columnKey(column)
    if (!key) continue
    columnMap.set(key, column)
  }

  return preferences
    .filter((preference) => preference.visible)
    .sort((a, b) => a.order - b.order)
    .map((preference) => {
      const column = columnMap.get(preference.key)
      if (!column) return undefined
      const systemColumn = systemColumns.get(preference.key)
      const protectedWidth = systemColumn?.protectedWidth
      const systemMinWidth = systemColumn?.minWidth
      const systemMaxWidth = systemColumn?.maxWidth
      const width = preference.width ?? protectedWidth
      const userFixedWidth = preference.width != null
      const maxWidth =
        userFixedWidth && width != null
          ? Math.max(width, systemMaxWidth ?? column.maxWidth ?? MAX_COLUMN_WIDTH)
          : protectedWidth
            ? Math.max(protectedWidth, systemMaxWidth ?? column.maxWidth ?? protectedWidth)
            : systemMaxWidth ?? column.maxWidth
      return {
        ...column,
        key: column.key ?? preference.key,
        width: width ?? column.width,
        minWidth: protectedWidth ?? systemMinWidth ?? column.minWidth,
        maxWidth,
        userFixedWidth,
        fixed: preference.fixed ?? column.fixed
      }
    })
    .filter(Boolean) as DataTableColumnsType<RecordType>
}

function rowSelectionWidth<RecordType>(rowSelection: TableProps<RecordType>['rowSelection']): number {
  if (!rowSelection) return 0
  const width = parseWidth(rowSelection.columnWidth as ColumnType<unknown>['width'])
  return width || 48
}

function isPageTable(element: HTMLElement | null): boolean {
  if (!element?.closest('.page-card')) return false
  return !element.closest('.ant-modal, .ant-drawer, .ant-card')
}

function visibleNativeScrollbarWidth(): number {
  const probe = document.createElement('div')
  probe.style.position = 'absolute'
  probe.style.top = '-9999px'
  probe.style.width = '100px'
  probe.style.height = '100px'
  probe.style.overflow = 'scroll'
  document.body.appendChild(probe)
  const width = probe.offsetWidth - probe.clientWidth
  probe.remove()
  return width
}

function tableHorizontalScrollElement(wrapper: HTMLElement | null): HTMLElement | null {
  if (!wrapper) return null
  const candidates = Array.from(
    wrapper.querySelectorAll<HTMLElement>('.ant-table-body, .ant-table-content')
  )
  return candidates.find((element) => element.scrollWidth > element.clientWidth + 1) ?? candidates[0] ?? null
}

function horizontalScrollStateFromElement(
  element: HTMLElement | null,
  showAssist: boolean,
  persistentWhenOverflowing = false
): HorizontalScrollState {
  if (!element) return defaultHorizontalScrollState
  const scrollWidth = Math.ceil(element.scrollWidth)
  const clientWidth = Math.ceil(element.clientWidth)
  const viewportWidth = Math.ceil(window.innerWidth || document.documentElement.clientWidth || 0)
  const maxScrollLeft = Math.max(0, scrollWidth - clientWidth)
  const scrollLeft = Math.min(maxScrollLeft, Math.max(0, element.scrollLeft))
  return {
    visible:
      showAssist &&
      clientWidth > 0 &&
      maxScrollLeft > 1 &&
      (persistentWhenOverflowing || scrollWidth > viewportWidth + 1),
    scrollLeft,
    scrollWidth,
    clientWidth
  }
}

function sameHorizontalScrollState(current: HorizontalScrollState, next: HorizontalScrollState): boolean {
  return (
    current.visible === next.visible &&
    Math.abs(current.scrollLeft - next.scrollLeft) <= 1 &&
    Math.abs(current.scrollWidth - next.scrollWidth) <= 1 &&
    Math.abs(current.clientWidth - next.clientWidth) <= 1
  )
}

function horizontalScrollbarGeometry(state: HorizontalScrollState) {
  const trackWidth = Math.max(0, state.clientWidth)
  const maxScrollLeft = Math.max(0, state.scrollWidth - state.clientWidth)
  const rawThumbWidth = state.scrollWidth > 0 ? (state.clientWidth / state.scrollWidth) * trackWidth : trackWidth
  const thumbWidth = trackWidth > 0 ? Math.min(trackWidth, Math.max(HORIZONTAL_SCROLLBAR_MIN_THUMB_WIDTH, rawThumbWidth)) : 0
  const maxThumbLeft = Math.max(0, trackWidth - thumbWidth)
  const thumbLeft =
    maxScrollLeft > 0 && maxThumbLeft > 0
      ? Math.min(maxThumbLeft, (state.scrollLeft / maxScrollLeft) * maxThumbLeft)
      : 0

  return { trackWidth, thumbWidth, thumbLeft, maxScrollLeft, maxThumbLeft }
}

interface TableSettingsModalProps {
  open: boolean
  config: DataTableConfig
  preferences: EffectiveColumnPreference[]
  onCancel: () => void
  onApply: (columns: EffectiveColumnPreference[]) => void
  onResetDefault: () => void
}

function TableSettingsModal({
  open,
  config,
  preferences,
  onCancel,
  onApply,
  onResetDefault
}: TableSettingsModalProps) {
  const [draft, setDraft] = useState<EffectiveColumnPreference[]>(preferences)
  const [availableKeyword, setAvailableKeyword] = useState('')
  const [selectedKeyword, setSelectedKeyword] = useState('')
  const [dragKey, setDragKey] = useState<string | null>(null)
  const configMap = useMemo(() => new Map(config.columns.map((column) => [column.key, column])), [config.columns])
  const configurableKeys = useMemo(
    () => new Set(config.columns.filter((column) => !column.settingsHidden).map((column) => column.key)),
    [config.columns]
  )

  useEffect(() => {
    if (open) {
      setDraft(preferences)
      setAvailableKeyword('')
      setSelectedKeyword('')
      setDragKey(null)
    }
  }, [open, preferences])

  const selectedColumns = useMemo(
    () => draft.filter((column) => column.visible && configurableKeys.has(column.key)).sort((a, b) => a.order - b.order),
    [configurableKeys, draft]
  )
  const selectableColumns = useMemo(() => {
    const text = availableKeyword.trim().toLowerCase()
    return draft
      .slice()
      .sort((a, b) => a.order - b.order)
      .filter((column) => configurableKeys.has(column.key))
      .filter((column) => {
        if (!text) return true
        const systemColumn = configMap.get(column.key)
        const label = titleText((systemColumn?.title ?? column.key) as ReactNode).toLowerCase()
        return label.includes(text) || column.key.toLowerCase().includes(text)
      })
  }, [availableKeyword, configMap, configurableKeys, draft])
  const visibleSelectedColumns = useMemo(() => {
    const text = selectedKeyword.trim().toLowerCase()
    return selectedColumns.filter((column) => {
      if (!text) return true
      const systemColumn = configMap.get(column.key)
      const label = titleText((systemColumn?.title ?? column.key) as ReactNode).toLowerCase()
      return label.includes(text) || column.key.toLowerCase().includes(text)
    })
  }, [configMap, selectedColumns, selectedKeyword])
  const requiredKeys = useMemo(
    () =>
      new Set(
        config.columns
          .filter((column) => !column.settingsHidden && (column.required || column.key === config.primaryColumnKey))
          .map((column) => column.key)
      ),
    [config.columns, config.primaryColumnKey]
  )
  const configurableDraft = useMemo(() => draft.filter((column) => configurableKeys.has(column.key)), [configurableKeys, draft])
  const selectedCount = selectedColumns.length
  const selectableCount = configurableDraft.length
  const allOptionalSelected = configurableDraft.every((column) => column.visible || requiredKeys.has(column.key))
  const someOptionalSelected =
    configurableDraft.some((column) => column.visible && !requiredKeys.has(column.key)) && !allOptionalSelected

  function updateColumn(key: string, patch: Partial<EffectiveColumnPreference>) {
    setDraft((columns) => columns.map((column) => (column.key === key ? { ...column, ...patch } : column)))
  }

  function toggleAllColumns(checked: boolean) {
    setDraft((columns) =>
      columns.map((column) => ({
        ...column,
        visible: !configurableKeys.has(column.key) || requiredKeys.has(column.key) ? true : checked
      }))
    )
  }

  function moveSelectedToTop(key: string) {
    setDraft((columns) => {
      const selected = columns
        .filter((column) => column.visible && configurableKeys.has(column.key))
        .sort((a, b) => a.order - b.order)
      const current = selected.find((column) => column.key === key)
      if (!current) return columns
      const nextSelected = [current, ...selected.filter((column) => column.key !== key)]
      const orderMap = new Map(nextSelected.map((column, index) => [column.key, index + 1]))
      const maxVisibleOrder = nextSelected.length
      return columns.map((column) => ({
        ...column,
        order: orderMap.get(column.key) ?? (configurableKeys.has(column.key) ? maxVisibleOrder + (configMap.get(column.key)?.order ?? column.order) : column.order)
      }))
    })
  }

  function reorderSelected(sourceKey: string, targetKey: string) {
    if (sourceKey === targetKey) return
    setDraft((columns) => {
      const selected = columns
        .filter((column) => column.visible && configurableKeys.has(column.key))
        .sort((a, b) => a.order - b.order)
      const from = selected.findIndex((column) => column.key === sourceKey)
      const to = selected.findIndex((column) => column.key === targetKey)
      if (from < 0 || to < 0) return columns

      const nextSelected = selected.slice()
      const [moved] = nextSelected.splice(from, 1)
      nextSelected.splice(to, 0, moved)
      const orderMap = new Map(nextSelected.map((column, index) => [column.key, index + 1]))
      const maxVisibleOrder = nextSelected.length
      return columns.map((column) => ({
        ...column,
        order: orderMap.get(column.key) ?? (configurableKeys.has(column.key) ? maxVisibleOrder + (configMap.get(column.key)?.order ?? column.order) : column.order)
      }))
    })
  }

  function confirm() {
    onApply(draft.map((column, index) => ({ ...column, order: column.order ?? index + 1 })))
  }

  return (
	    <Modal
	      open={open}
	      title="选择表头显示内容"
	      width={980}
	      centered
      className="data-table-settings-modal"
      onCancel={onCancel}
      footer={
        <div className="data-table-settings-footer">
          <Button icon={<ReloadOutlined />} onClick={onResetDefault}>
            恢复默认值
          </Button>
          <Space>
            <Button onClick={onCancel}>取消</Button>
            <Button type="primary" onClick={confirm}>
              确定
            </Button>
          </Space>
        </div>
      }
    >
      <div className="data-table-settings">
        <section className="data-table-settings__panel data-table-settings__panel--available">
          <div className="data-table-settings__head">
            <span>可选属性</span>
            <small>共 {selectableCount} 个</small>
          </div>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索可选属性"
            value={availableKeyword}
            onChange={(event) => setAvailableKeyword(event.target.value)}
          />
          <div className="data-table-settings__group">
            <div className="data-table-settings__group-title">页面默认列</div>
            <Checkbox
              indeterminate={someOptionalSelected}
              checked={allOptionalSelected}
              onChange={(event) => toggleAllColumns(event.target.checked)}
            >
              全选
            </Checkbox>
            <div className="data-table-settings__checkbox-grid">
              {selectableColumns.map((column) => {
                const systemColumn = configMap.get(column.key)
                const required = requiredKeys.has(column.key)
                return (
                  <Checkbox
                    key={column.key}
                    checked={column.visible}
                    disabled={required}
                    onChange={(event) => updateColumn(column.key, { visible: event.target.checked })}
                  >
                    {titleText((systemColumn?.title ?? column.key) as ReactNode) || column.key}
                  </Checkbox>
                )
              })}
            </div>
          </div>
        </section>
        <section className="data-table-settings__panel data-table-settings__panel--selected">
          <div className="data-table-settings__head">
            <span>已选属性</span>
            <small>共 {selectedCount} 个</small>
          </div>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索已选属性"
            value={selectedKeyword}
            onChange={(event) => setSelectedKeyword(event.target.value)}
          />
          <div className="data-table-settings__selected">
            {visibleSelectedColumns.length ? (
              visibleSelectedColumns.map((column) => {
                const systemColumn = configMap.get(column.key)
                const required = requiredKeys.has(column.key)
                return (
                  <div
                    key={column.key}
                    className="data-table-settings__selected-item"
                    draggable
                    onDragStart={() => setDragKey(column.key)}
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={(event) => {
                      event.preventDefault()
                      if (dragKey) reorderSelected(dragKey, column.key)
                      setDragKey(null)
                    }}
                    onDragEnd={() => setDragKey(null)}
                  >
                    <HolderOutlined className="data-table-settings__drag-icon" />
                    <span>{titleText((systemColumn?.title ?? column.key) as ReactNode) || column.key}</span>
                    <Button
                      type="text"
                      size="small"
                      className="data-table-settings__icon-button"
                      icon={<VerticalAlignTopOutlined />}
                      aria-label="置顶"
                      title="置顶"
                      onClick={() => moveSelectedToTop(column.key)}
                    />
                    <Button
                      type="text"
                      size="small"
                      className="data-table-settings__icon-button"
                      icon={<CloseOutlined />}
                      aria-label="移除"
                      title={required ? '必选列不可移除' : '移除'}
                      disabled={required}
                      onClick={() => updateColumn(column.key, { visible: false })}
                    />
                  </div>
                )
              })
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无已选列" />
            )}
          </div>
        </section>
      </div>
    </Modal>
  )
}

interface ResizableHeaderCellProps extends React.ThHTMLAttributes<HTMLTableCellElement> {
  width?: number
  resizeWidth?: number
  minWidth?: number
  maxWidth?: number
  columnKey?: string
  resizeHandleSide?: 'left' | 'right'
  resizeDirection?: 'normal' | 'inverse'
  onColumnResize?: (columnKey: string, width: number) => void
  settingsButton?: ReactNode
}

function ResizableHeaderCell({
  width,
  resizeWidth,
  minWidth,
  maxWidth,
  columnKey: resizeColumnKey,
  resizeHandleSide = 'right',
  resizeDirection,
  onColumnResize,
  settingsButton,
  children,
  ...restProps
}: ResizableHeaderCellProps) {
  const [dragging, setDragging] = useState(false)
  const effectiveResizeWidth = resizeWidth ?? width
  const effectiveResizeDirection = resizeDirection ?? (resizeHandleSide === 'left' ? 'inverse' : 'normal')
  const effectiveMinWidth = minWidth ?? MIN_COLUMN_WIDTH
  const effectiveMaxWidth = maxWidth ?? Math.max(effectiveResizeWidth ?? 0, MAX_COLUMN_WIDTH)

  const resizeTo = useCallback(
    (nextWidth: number) => {
      if (!resizeColumnKey || !onColumnResize) return
      onColumnResize(
        resizeColumnKey,
        clampColumnWidth(nextWidth, effectiveMinWidth, effectiveMaxWidth)
      )
    },
    [effectiveMaxWidth, effectiveMinWidth, onColumnResize, resizeColumnKey]
  )

  const onPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLSpanElement>) => {
      if (event.button !== 0) return
      if (!resizeColumnKey || !effectiveResizeWidth || !onColumnResize) return
      event.preventDefault()
      event.stopPropagation()

      const pointerId = event.pointerId
      const startX = event.clientX
      const startWidth = effectiveResizeWidth
      setDragging(true)

      const onPointerMove = (moveEvent: PointerEvent) => {
        if (moveEvent.pointerId !== pointerId) return
        const deltaX = moveEvent.clientX - startX
        resizeTo(startWidth + (effectiveResizeDirection === 'inverse' ? -deltaX : deltaX))
      }
      const onPointerUp = (upEvent: PointerEvent) => {
        if (upEvent.pointerId !== pointerId) return
        setDragging(false)
        window.removeEventListener('pointermove', onPointerMove)
        window.removeEventListener('pointerup', onPointerUp)
        window.removeEventListener('pointercancel', onPointerUp)
      }

      window.addEventListener('pointermove', onPointerMove)
      window.addEventListener('pointerup', onPointerUp)
      window.addEventListener('pointercancel', onPointerUp)
    },
    [effectiveResizeDirection, effectiveResizeWidth, onColumnResize, resizeColumnKey, resizeTo]
  )

  const onResizeKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLSpanElement>) => {
      if (!effectiveResizeWidth) return
      const step = event.shiftKey ? 40 : 10
      let nextWidth: number | undefined
      if (event.key === 'ArrowLeft') nextWidth = effectiveResizeWidth - step
      if (event.key === 'ArrowRight') nextWidth = effectiveResizeWidth + step
      if (event.key === 'Home') nextWidth = effectiveMinWidth
      if (event.key === 'End') nextWidth = effectiveMaxWidth
      if (nextWidth == null) return
      event.preventDefault()
      event.stopPropagation()
      resizeTo(nextWidth)
    },
    [effectiveMaxWidth, effectiveMinWidth, effectiveResizeWidth, resizeTo]
  )

  return (
    <th {...restProps}>
      {settingsButton ? (
        <span className="data-table-header-content data-table-header-content--with-settings">
          <span className="data-table-header-title">{children}</span>
          {settingsButton}
        </span>
      ) : (
        children
      )}
      {resizeColumnKey && effectiveResizeWidth && onColumnResize ? (
        <span
          className={[
            'data-table-resize-handle',
            resizeHandleSide === 'left' ? 'data-table-resize-handle--left' : '',
            dragging ? 'is-dragging' : ''
          ].filter(Boolean).join(' ')}
          role="separator"
          aria-label={`调整${titleText(children)}列宽`}
          aria-orientation="vertical"
          aria-valuemin={effectiveMinWidth}
          aria-valuemax={effectiveMaxWidth}
          aria-valuenow={effectiveResizeWidth}
          aria-valuetext={`${effectiveResizeWidth}px`}
          tabIndex={0}
          title="拖动或使用左右方向键调整列宽"
          onPointerDown={onPointerDown}
          onKeyDown={onResizeKeyDown}
        />
      ) : null}
    </th>
  )
}

export function DataTable<RecordType extends object = Record<string, unknown>>({
  fitContainerHeight = false,
  fitContentColumns = true,
  persistentHorizontalScrollbar = false,
  showSelectionFooter = true,
  tableConfig,
  showColumnSettingsButton = true,
  columnSettingsOpen,
  onColumnSettingsOpenChange,
  onVisibleColumnsChange,
  showFullTextOnHover = false,
  ...props
}: DataTableProps<RecordType>) {
  const wrapperRef = useRef<HTMLDivElement | null>(null)
  const horizontalScrollTrackRef = useRef<HTMLDivElement | null>(null)
  const horizontalScrollElementRef = useRef<HTMLElement | null>(null)
  const widthMemoryRef = useRef(new Map<string, number>())
  const [autoScrollY, setAutoScrollY] = useState<number>()
  const [containerWidth, setContainerWidth] = useState(0)
  const [nativeScrollbarWidth, setNativeScrollbarWidth] = useState<number>()
  const [horizontalScrollState, setHorizontalScrollState] = useState<HorizontalScrollState>(
    defaultHorizontalScrollState
  )
  const [hasRenderedPagination, setHasRenderedPagination] = useState(false)
  const [internalSelectedCount, setInternalSelectedCount] = useState(0)
  const [userConfig, setUserConfig] = useState<TablePreferenceConfig | null>(null)
  const [preferenceLoadedKey, setPreferenceLoadedKey] = useState('')
  const [localPreferences, setLocalPreferences] = useState<EffectiveColumnPreference[] | null>(null)
  const [resetVersion, setResetVersion] = useState(0)
  const visibleColumnsSignatureRef = useRef('')
  const [internalSettingsOpen, setInternalSettingsOpen] = useState(false)
  const settingsOpen = columnSettingsOpen ?? internalSettingsOpen
  const setSettingsOpen = useCallback(
    (open: boolean) => {
      if (columnSettingsOpen === undefined) setInternalSettingsOpen(open)
      onColumnSettingsOpenChange?.(open)
    },
    [columnSettingsOpen, onColumnSettingsOpenChange]
  )
  const data = (props.dataSource || []) as readonly RecordType[]
  const explicitScrollY = props.scroll?.y
  const paginationConfig = props.pagination
  const controlledSelectedKeys = props.rowSelection?.selectedRowKeys
  const defaultSelectedKeys = props.rowSelection?.defaultSelectedRowKeys
  const normalizedConfig = useMemo(() => normalizedColumnConfig(tableConfig), [tableConfig])
  const defaultPreferences = useMemo(
    () => mergedPreferences(normalizedConfig, userConfig),
    [normalizedConfig, userConfig]
  )
  const effectivePreferences = localPreferences ?? defaultPreferences
  const configColumnsFingerprint = normalizedConfig?.columns
    .map((column) => [
      column.key,
      column.visible,
      column.order,
      column.width,
      column.minWidth,
      column.maxWidth,
      column.fixed,
      column.required,
      column.settingsHidden,
      column.protectedWidth
    ].join(':'))
    .join('|')
  const hoverColumns = useMemo(
    () => columnsWithFullTextHover(props.columns, showFullTextOnHover),
    [props.columns, showFullTextOnHover]
  )
  const configuredColumns = useMemo(
    () => applyPreferencesToColumns(hoverColumns, normalizedConfig, effectivePreferences),
    [effectivePreferences, hoverColumns, normalizedConfig, resetVersion]
  )
  const preferenceLoading = !!normalizedConfig?.tableKey && preferenceLoadedKey !== normalizedConfig.tableKey

  const rowSelection = useMemo<TableProps<RecordType>['rowSelection']>(() => {
    if (!props.rowSelection) return undefined
    return {
      ...props.rowSelection,
      onChange: (selectedRowKeys, selectedRows, info) => {
        setInternalSelectedCount(selectedRowKeys.length)
        props.rowSelection?.onChange?.(selectedRowKeys, selectedRows, info)
      }
    }
  }, [props.rowSelection])

  useEffect(() => {
    const tableKey = normalizedConfig?.tableKey
    if (!tableKey) {
      setUserConfig(null)
      setLocalPreferences(null)
      setPreferenceLoadedKey('')
      return
    }

    let cancelled = false
    setPreferenceLoadedKey('')
    setLocalPreferences(null)
    fetchTablePreference(tableKey)
      .then((preference) => {
        if (cancelled) return
        setUserConfig(preference.config_json || null)
        setPreferenceLoadedKey(tableKey)
      })
      .catch(() => {
        if (cancelled) return
        setUserConfig(null)
        setPreferenceLoadedKey(tableKey)
      })
    return () => {
      cancelled = true
    }
  }, [normalizedConfig?.tableKey])

  useEffect(() => {
    setLocalPreferences(null)
  }, [normalizedConfig?.primaryColumnKey, configColumnsFingerprint])

  const persistPreferences = useCallback(
    (columns: EffectiveColumnPreference[]) => {
      if (!normalizedConfig) return
      const nextConfig = preferenceConfigFromColumns(normalizedConfig, columns)
      setUserConfig(nextConfig)
      schedulePreferenceSave(normalizedConfig.tableKey, nextConfig)
    },
    [normalizedConfig]
  )

  const updatePreferences = useCallback(
    (updater: (columns: EffectiveColumnPreference[]) => EffectiveColumnPreference[]) => {
      if (!normalizedConfig) return
      const base = localPreferences ?? defaultPreferences
      const next = updater(base).map((column) =>
        column.key === normalizedConfig.primaryColumnKey
          ? { ...column, visible: true, fixed: column.fixed ?? 'left' }
          : normalizedConfig.columns.find((configColumn) => configColumn.key === column.key)?.settingsHidden
            ? { ...column, visible: true, fixed: column.fixed ?? (column.key === 'actions' ? 'right' : column.fixed) }
            : column
      )
      setLocalPreferences(next)
      persistPreferences(next)
    },
    [defaultPreferences, localPreferences, normalizedConfig, persistPreferences]
  )

  const onColumnResize = useCallback(
    (resizedColumnKey: string, width: number) => {
      updatePreferences((columns) =>
        columns.map((column) =>
          column.key === resizedColumnKey
            ? { ...column, width: clampColumnWidth(width, MIN_COLUMN_WIDTH, Math.max(width, MAX_COLUMN_WIDTH)) }
            : column
        )
      )
    },
    [updatePreferences]
  )

  const tableComponents = useMemo<TableProps<RecordType>['components']>(() => {
    if (props.components?.header?.cell) return props.components
    return {
      ...props.components,
      header: {
        ...props.components?.header,
        cell: ResizableHeaderCell
      }
    }
  }, [props.components])

  const rowSelectionColumnWidth = rowSelectionWidth(rowSelection)
  const widthSignature = widthMemorySignature(
    configuredColumns,
    data,
    containerWidth,
    rowSelectionColumnWidth,
    fitContentColumns,
    resetVersion
  )
  const columns = useMemo(
    () => {
      const normalizedColumns = normalizeColumns(
        configuredColumns,
        data,
        containerWidth,
        rowSelectionColumnWidth,
        fitContentColumns
      )
      const stableColumns = data.length
        ? normalizedColumns
        : applyRememberedWidths(
            normalizedColumns,
            configuredColumns,
            containerWidth,
            rowSelectionColumnWidth,
            fitContentColumns,
            widthMemoryRef.current
          )

      if (data.length) {
        rememberColumnWidths(
          stableColumns,
          configuredColumns,
          containerWidth,
          rowSelectionColumnWidth,
          fitContentColumns,
          widthMemoryRef.current
        )
      }

      let lastLeafKey = ''
      const previousResizableColumnByKey = new Map<
        string,
        { key: string; width: number; minWidth: number; maxWidth: number }
      >()
      let previousDataColumn: { key: string; width: number; minWidth: number; maxWidth: number } | undefined

      flattenDataColumns(stableColumns as DataTableColumnsType<RecordType>).forEach((column) => {
        const key = columnKey(column)
        if (key) lastLeafKey = key
        if (!key) return

        if (previousDataColumn) {
          previousResizableColumnByKey.set(key, previousDataColumn)
        }

        if ((column as ColumnType<RecordType>).fixed !== 'right') {
          const width = parseWidth(column.width as ColumnType<unknown>['width']) || MIN_COLUMN_WIDTH
          const minWidth = column.minWidth ?? MIN_COLUMN_WIDTH
          previousDataColumn = {
            key,
            width,
            minWidth,
            maxWidth: Math.max(column.maxWidth ?? 0, width, MAX_COLUMN_WIDTH)
          }
        }
      })

      return stableColumns.map((column) => {
          if (isColumnGroup(column)) return column
          const key = columnKey(column as DataTableColumnType<RecordType>)
          if (!key || !normalizedConfig) return column
          const onHeaderCell = column.onHeaderCell
          const isFixedRightColumn = (column as ColumnType<RecordType>).fixed === 'right'
          const resizeProxyColumn = isFixedRightColumn ? previousResizableColumnByKey.get(key) : undefined
          return {
            ...column,
            onHeaderCell: (col: Parameters<NonNullable<typeof onHeaderCell>>[0]) => {
              const cell = onHeaderCell?.(col) || {}
              return {
                ...cell,
                columnKey: resizeProxyColumn?.key ?? key,
                resizeWidth: resizeProxyColumn?.width,
                resizeHandleSide: resizeProxyColumn ? 'left' : 'right',
                resizeDirection: 'normal',
                onColumnResize,
                minWidth: resizeProxyColumn?.minWidth ?? (cell as { minWidth?: number }).minWidth ?? MIN_COLUMN_WIDTH,
                maxWidth:
                  resizeProxyColumn?.maxWidth ??
                  Math.max(
                    (cell as { maxWidth?: number }).maxWidth ?? 0,
                    parseWidth(column.width) || 0,
                    MAX_COLUMN_WIDTH
                  ),
                settingsButton:
                  showColumnSettingsButton && key === lastLeafKey ? (
                    <Button
                      type="text"
                      size="small"
                      className="data-table-header-settings"
                      icon={<SettingOutlined />}
                      loading={preferenceLoading}
                      aria-label="列设置"
                      onClick={(event) => {
                        event.preventDefault()
                        event.stopPropagation()
                        setSettingsOpen(true)
                      }}
                    />
                  ) : undefined
              }
            }
          }
        })
    },
    [
      configuredColumns,
      data,
      containerWidth,
      rowSelectionColumnWidth,
      fitContentColumns,
      normalizedConfig,
      onColumnResize,
      preferenceLoading,
      setSettingsOpen,
      showColumnSettingsButton,
      widthSignature
    ]
  )
  const computedScrollX = useMemo(
    () => Math.max(leafWidth(columns) + rowSelectionColumnWidth, 1),
    [columns, rowSelectionColumnWidth]
  )
  const resolvedScrollX = useMemo(() => {
    const explicitScrollX = props.scroll?.x
    if (explicitScrollX == null) {
      return data.length || normalizedConfig ? computedScrollX : undefined
    }
    return typeof explicitScrollX === 'number' ? Math.max(explicitScrollX, computedScrollX) : explicitScrollX
  }, [computedScrollX, data.length, normalizedConfig, props.scroll?.x])
  const fixedColumnScrollWidth = typeof resolvedScrollX === 'number' ? resolvedScrollX : computedScrollX
  const displayColumns = useMemo(
    () => (containerWidth > 0 && fixedColumnScrollWidth <= containerWidth ? releaseRightFixedColumns(columns) : columns),
    [columns, fixedColumnScrollWidth, containerWidth]
  )
  const tableColumns = useMemo(() => antTableColumns(displayColumns), [displayColumns])
  useEffect(() => {
    if (!normalizedConfig || !onVisibleColumnsChange) return
    const configMap = new Map(normalizedConfig.columns.map((column) => [column.key, column]))
    const visibleColumns = flattenDataColumns(displayColumns as DataTableColumnsType<RecordType>)
      .map((column) => {
        const key = columnKey(column)
        if (!key) return undefined
        const configColumn = configMap.get(key)
        if (configColumn?.settingsHidden) return undefined
        return {
          key,
          title: titleText((configColumn?.title ?? column.title ?? key) as ReactNode) || key
        }
      })
      .filter(Boolean) as DataTableVisibleColumn[]
    const signature = visibleColumns.map((column) => `${column.key}:${column.title}`).join('|')
    if (signature === visibleColumnsSignatureRef.current) return
    visibleColumnsSignatureRef.current = signature
    onVisibleColumnsChange(visibleColumns)
  }, [displayColumns, normalizedConfig, onVisibleColumnsChange])
  const selectedCount =
    controlledSelectedKeys?.length ?? (internalSelectedCount || defaultSelectedKeys?.length || 0)
  const hasSelectionFooter = Boolean(showSelectionFooter && props.rowSelection && props.pagination === false)
  const selectionSummary = props.rowSelection ? (
    <span className="data-table-selection-count" aria-live="polite">
      已选 <strong>{selectedCount}</strong> 条
    </span>
  ) : null
  const pagination = useMemo<TableProps<RecordType>['pagination']>(() => {
    if (!props.rowSelection || props.pagination === false) return props.pagination
    const config = props.pagination && typeof props.pagination === 'object' ? props.pagination : {}
    const showTotal = config.showTotal
    return {
      ...config,
      showTotal: (total, range) => (
        <span className="data-table-pagination-total">
          {selectionSummary}
          <span>{showTotal ? showTotal(total, range) : `共 ${total} 条`}</span>
        </span>
      )
    }
  }, [props.pagination, props.rowSelection, selectedCount])

  useLayoutEffect(() => {
    const update = () => {
      const rect = wrapperRef.current?.getBoundingClientRect()
      if (!rect) return
      const next = Math.floor(rect.width)
      setContainerWidth((current) => (Math.abs(current - next) > 2 ? next : current))
    }
    update()
    window.addEventListener('resize', update)
    const resizeObserver = new ResizeObserver(update)
    if (wrapperRef.current) resizeObserver.observe(wrapperRef.current)
    return () => {
      window.removeEventListener('resize', update)
      resizeObserver.disconnect()
    }
  }, [])

  useLayoutEffect(() => {
    if (explicitScrollY != null || (!fitContainerHeight && !isPageTable(wrapperRef.current))) {
      setAutoScrollY(undefined)
      return
    }
    const update = () => {
      const wrapper = wrapperRef.current
      const rect = wrapper?.getBoundingClientRect()
      if (!wrapper || !rect) return
      const pageCard = wrapper.closest('.page-card') as HTMLElement | null
      const pageRect = pageCard?.getBoundingClientRect()
      const tableHeader = wrapper.querySelector('.ant-table-thead') as HTMLElement | null
      const tablePagination = wrapper.querySelector('.ant-table-pagination') as HTMLElement | null
      const tableBody = wrapper.querySelector('.ant-table-body') as HTMLElement | null
      const pageCardStyle = pageCard ? window.getComputedStyle(pageCard) : null
      const pageCardBottomInset =
        Number.parseFloat(pageCardStyle?.paddingBottom || '0') +
        Number.parseFloat(pageCardStyle?.borderBottomWidth || '0')
      const headerHeight = Math.ceil(tableHeader?.getBoundingClientRect().height || TABLE_HEADER_FALLBACK_HEIGHT)
      const paginationHeight =
        paginationConfig === false || !tablePagination
          ? paginationConfig === false
            ? fitContainerHeight
              ? 0
              : TABLE_BOTTOM_RESERVE
            : TABLE_PAGINATION_RESERVE
          : Math.ceil(
              tablePagination.getBoundingClientRect().height +
                Number.parseFloat(window.getComputedStyle(tablePagination).marginTop || '0') +
                Number.parseFloat(window.getComputedStyle(tablePagination).marginBottom || '0')
            )
      const pageVisibleBottom = Math.min(window.innerHeight, pageRect?.bottom ?? window.innerHeight)
      const visibleBottom = fitContainerHeight ? Math.min(pageVisibleBottom, rect.bottom) : pageVisibleBottom
      const bodyTop = tableBody?.getBoundingClientRect().top ?? rect.top + headerHeight
      const bottomInset = fitContainerHeight ? 0 : pageCardBottomInset
      const availableBodyHeight = visibleBottom - bodyTop - paginationHeight - bottomInset
      const next = Math.max(TABLE_MIN_BODY_HEIGHT, availableBodyHeight)
      setAutoScrollY((current) => (current == null || Math.abs(current - next) > 2 ? next : current))
    }
    update()
    window.addEventListener('resize', update)
    const resizeObserver = new ResizeObserver(update)
    if (wrapperRef.current) {
      resizeObserver.observe(wrapperRef.current)
      const pageCard = wrapperRef.current.closest('.page-card')
      if (pageCard) resizeObserver.observe(pageCard)
    }
    return () => {
      window.removeEventListener('resize', update)
      resizeObserver.disconnect()
    }
  }, [explicitScrollY, fitContainerHeight, paginationConfig])

  useLayoutEffect(() => {
    setNativeScrollbarWidth(visibleNativeScrollbarWidth())
  }, [])

  const resolvedScrollY = props.scroll?.y ?? autoScrollY
  const scroll = {
    ...props.scroll,
    x: resolvedScrollX,
    y: resolvedScrollY
  }
  const showHorizontalScrollAssist = nativeScrollbarWidth === 0
  const shellStyle =
    resolvedScrollY == null
      ? undefined
      : ({
          '--data-table-body-height':
            typeof resolvedScrollY === 'number' ? `${resolvedScrollY}px` : String(resolvedScrollY)
        } as CSSProperties)
  const shellClassName = [
    'data-table-shell',
    resolvedScrollY != null ? 'data-table-shell--scroll-y' : '',
    horizontalScrollState.visible ? 'data-table-shell--horizontal-scroll-assist' : '',
    hasRenderedPagination ? 'data-table-shell--with-pagination' : '',
    hasSelectionFooter ? 'data-table-shell--with-selection-footer' : '',
    autoScrollY != null ? 'data-table-shell--auto-height' : '',
    normalizedConfig ? 'data-table-shell--configurable' : '',
    containerWidth > 0 && containerWidth < 1200 ? 'data-table-shell--compact' : ''
  ]
    .filter(Boolean)
    .join(' ')
  const horizontalScrollGeometry = horizontalScrollbarGeometry(horizontalScrollState)

  useLayoutEffect(() => {
    if (nativeScrollbarWidth == null) return

    const wrapper = wrapperRef.current
    let animationFrame = 0
    const update = () => {
      animationFrame = 0
      const currentWrapper = wrapperRef.current
      setHasRenderedPagination((current) => {
        const next = Boolean(currentWrapper?.querySelector('.ant-table-pagination'))
        return current === next ? current : next
      })
      const scrollElement = tableHorizontalScrollElement(currentWrapper)
      horizontalScrollElementRef.current = scrollElement
      const nextState = horizontalScrollStateFromElement(
        scrollElement,
        showHorizontalScrollAssist,
        persistentHorizontalScrollbar
      )
      setHorizontalScrollState((current) => (sameHorizontalScrollState(current, nextState) ? current : nextState))
    }
    const scheduleUpdate = () => {
      if (animationFrame) window.cancelAnimationFrame(animationFrame)
      animationFrame = window.requestAnimationFrame(update)
    }

    update()
    wrapper?.addEventListener('scroll', update, true)
    window.addEventListener('resize', scheduleUpdate)

    const resizeObserver = new ResizeObserver(scheduleUpdate)
    if (wrapper) resizeObserver.observe(wrapper)
    const currentScrollElement = tableHorizontalScrollElement(wrapper)
    if (currentScrollElement) resizeObserver.observe(currentScrollElement)

    const mutationObserver = new MutationObserver(scheduleUpdate)
    if (wrapper) {
      mutationObserver.observe(wrapper, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['class', 'style']
      })
    }

    return () => {
      if (animationFrame) window.cancelAnimationFrame(animationFrame)
      wrapper?.removeEventListener('scroll', update, true)
      window.removeEventListener('resize', scheduleUpdate)
      resizeObserver.disconnect()
      mutationObserver.disconnect()
    }
  }, [containerWidth, data.length, displayColumns, nativeScrollbarWidth, persistentHorizontalScrollbar, resolvedScrollX, resolvedScrollY, showHorizontalScrollAssist])

  const scrollTableHorizontally = useCallback(
    (scrollLeft: number) => {
      const scrollElement = horizontalScrollElementRef.current ?? tableHorizontalScrollElement(wrapperRef.current)
      if (!scrollElement) return

      const maxScrollLeft = Math.max(0, scrollElement.scrollWidth - scrollElement.clientWidth)
      scrollElement.scrollLeft = Math.min(maxScrollLeft, Math.max(0, scrollLeft))
      const nextState = horizontalScrollStateFromElement(
        scrollElement,
        showHorizontalScrollAssist,
        persistentHorizontalScrollbar
      )
      setHorizontalScrollState((current) => (sameHorizontalScrollState(current, nextState) ? current : nextState))
    },
    [persistentHorizontalScrollbar, showHorizontalScrollAssist]
  )

  const onHorizontalScrollTrackPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (event.button !== 0) return
      const target = event.target as HTMLElement
      if (target.closest('.data-table-horizontal-scrollbar__thumb')) return
      const track = horizontalScrollTrackRef.current
      if (!track || horizontalScrollGeometry.maxScrollLeft <= 0) return

      event.preventDefault()
      const rect = track.getBoundingClientRect()
      const thumbCenter = event.clientX - rect.left - horizontalScrollGeometry.thumbWidth / 2
      const ratio = thumbCenter / Math.max(1, horizontalScrollGeometry.maxThumbLeft)
      scrollTableHorizontally(ratio * horizontalScrollGeometry.maxScrollLeft)
    },
    [horizontalScrollGeometry, scrollTableHorizontally]
  )

  const onHorizontalScrollThumbPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (event.button !== 0 || horizontalScrollGeometry.maxScrollLeft <= 0) return
      const scrollElement = horizontalScrollElementRef.current ?? tableHorizontalScrollElement(wrapperRef.current)
      if (!scrollElement) return

      event.preventDefault()
      event.stopPropagation()

      const startX = event.clientX
      const startScrollLeft = scrollElement.scrollLeft
      const scrollPerPixel =
        horizontalScrollGeometry.maxThumbLeft > 0
          ? horizontalScrollGeometry.maxScrollLeft / horizontalScrollGeometry.maxThumbLeft
          : 0

      const onPointerMove = (moveEvent: PointerEvent) => {
        scrollTableHorizontally(startScrollLeft + (moveEvent.clientX - startX) * scrollPerPixel)
      }
      const onPointerUp = () => {
        window.removeEventListener('pointermove', onPointerMove)
        window.removeEventListener('pointerup', onPointerUp)
        window.removeEventListener('pointercancel', onPointerUp)
      }

      window.addEventListener('pointermove', onPointerMove)
      window.addEventListener('pointerup', onPointerUp)
      window.addEventListener('pointercancel', onPointerUp)
    },
    [horizontalScrollGeometry, scrollTableHorizontally]
  )

  const onHorizontalScrollbarKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      const scrollElement = horizontalScrollElementRef.current ?? tableHorizontalScrollElement(wrapperRef.current)
      const currentScrollLeft = scrollElement?.scrollLeft ?? horizontalScrollState.scrollLeft
      const step = Math.max(40, Math.floor(horizontalScrollState.clientWidth / 10))
      const pageStep = Math.max(step, Math.floor(horizontalScrollState.clientWidth * 0.8))
      let nextScrollLeft: number | undefined

      if (event.key === 'ArrowLeft') nextScrollLeft = currentScrollLeft - step
      if (event.key === 'ArrowRight') nextScrollLeft = currentScrollLeft + step
      if (event.key === 'PageUp') nextScrollLeft = currentScrollLeft - pageStep
      if (event.key === 'PageDown') nextScrollLeft = currentScrollLeft + pageStep
      if (event.key === 'Home') nextScrollLeft = 0
      if (event.key === 'End') nextScrollLeft = horizontalScrollGeometry.maxScrollLeft
      if (nextScrollLeft == null) return

      event.preventDefault()
      scrollTableHorizontally(nextScrollLeft)
    },
    [horizontalScrollGeometry.maxScrollLeft, horizontalScrollState, scrollTableHorizontally]
  )

  async function applyColumnSettings(columns: EffectiveColumnPreference[]) {
    if (!normalizedConfig) return
    const normalizedColumns = columns
      .slice()
      .sort((a, b) => a.order - b.order)
      .map((column, index) => ({
        ...column,
        order: index + 1,
        visible:
          column.key === normalizedConfig.primaryColumnKey ||
          normalizedConfig.columns.find((configColumn) => configColumn.key === column.key)?.settingsHidden
            ? true
            : column.visible
      }))
    setLocalPreferences(normalizedColumns)
    const nextConfig = preferenceConfigFromColumns(normalizedConfig, normalizedColumns)
    setUserConfig(nextConfig)
    setSettingsOpen(false)
    try {
      const tableKey = normalizedConfig.tableKey
      const saveVersion = currentPreferenceSaveVersion(tableKey)
      await savePreferenceNow(tableKey, nextConfig, saveVersion)
    } catch {
      // The global HTTP interceptor surfaces request failures.
    }
  }

  async function restoreDefaultSettings() {
    if (!normalizedConfig) return
    const tableKey = normalizedConfig.tableKey
    invalidatePreferenceSaves(tableKey)
    const pendingSave = preferenceSavePromises.get(tableKey)
    widthMemoryRef.current.clear()
    setUserConfig(null)
    setLocalPreferences(null)
    setSettingsOpen(false)
    setResetVersion((version) => version + 1)
    try {
      await pendingSave
      await resetTablePreference(tableKey)
      preferenceSavePromises.delete(tableKey)
    } catch {
      // The global HTTP interceptor surfaces request failures.
    }
  }

  return (
    <div ref={wrapperRef} className={shellClassName} style={shellStyle}>
      <AntTable<RecordType>
        {...props}
        key={normalizedConfig ? `${normalizedConfig.tableKey}:${resetVersion}` : undefined}
        className={['data-table', props.className].filter(Boolean).join(' ')}
        columns={tableColumns}
        components={tableComponents}
        pagination={pagination}
        rowSelection={rowSelection}
        scroll={scroll}
      />
      {hasSelectionFooter ? (
        <div className="data-table-footer">{selectionSummary}</div>
      ) : null}
      {horizontalScrollState.visible ? (
        <div
          className="data-table-horizontal-scrollbar"
          ref={horizontalScrollTrackRef}
          role="scrollbar"
          aria-label="横向滚动表格"
          aria-controls={props.id}
          aria-orientation="horizontal"
          aria-valuemin={0}
          aria-valuemax={horizontalScrollGeometry.maxScrollLeft}
          aria-valuenow={Math.round(horizontalScrollState.scrollLeft)}
          tabIndex={0}
          onKeyDown={onHorizontalScrollbarKeyDown}
          onPointerDown={onHorizontalScrollTrackPointerDown}
        >
          <div
            className="data-table-horizontal-scrollbar__thumb"
            style={{
              width: horizontalScrollGeometry.thumbWidth,
              transform: `translateX(${horizontalScrollGeometry.thumbLeft}px)`
            }}
            onPointerDown={onHorizontalScrollThumbPointerDown}
          />
        </div>
      ) : null}
      {normalizedConfig ? (
        <TableSettingsModal
          open={settingsOpen}
          config={normalizedConfig}
          preferences={effectivePreferences}
          onCancel={() => setSettingsOpen(false)}
          onApply={applyColumnSettings}
          onResetDefault={restoreDefaultSettings}
        />
      ) : null}
    </div>
  )
}
