import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from '@/router/navigation'
import { ArrowLeftOutlined, CheckCircleOutlined, CloseOutlined, ExportOutlined, UndoOutlined } from '@ant-design/icons'
import {
  Alert,
  App,
  Button,
  Checkbox,
  DatePicker,
  Descriptions,
  Form,
  Input,
  Modal,
  Segmented,
  Select,
  Space,
  Spin,
  Tabs,
  Tag
} from 'antd'
import { DataTable } from '@/components/DataTable'
import type { DataTableColumnsType, DataTableConfig, DataTableVisibleColumn } from '@/components/DataTable'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import type { Dayjs } from 'dayjs'
import http from '@/api/http'
import {
  batchConfirmPrinted,
  batchMarkShipped,
  batchPrintChineseLabel,
  batchPrintLabel,
  batchToPicking,
  batchToPrinting,
  batchUpdateRiskHandling,
  fetchOrderDetail,
  listOrders,
  type OrderDetailDto,
  type OrderDetailItemDto,
  type OrderDto,
  type OrderListParams,
  type OrderSearchSummary,
  type PrintLabelResponse
} from '@/api/orders'
import { fetchOrderStatusCounts, type OrderStatusCounts } from '@/api/dashboard'
import { MoneyText } from '@/components/MoneyText'
import { OrderOperationLogTable } from '@/components/OrderOperationLogTable'
import { ShopMultiSelect } from '@/components/ShopMultiSelect'
import { TimeText } from '@/components/TimeText'
import { useEnabledPlatformOptions } from '@/hooks/useEnabledPlatformOptions'
import { formatPlatformLabel, ORDER_STATUS_COLOR, ORDER_STATUSES } from '@/stores/dict'
import { downloadBlob } from '@/utils/download'
import { formatMoney, formatTime, formatTimeUtc } from '@/utils/format'
import {
  MAX_BATCH_ORDER_NUMBER_LENGTH,
  MAX_BATCH_ORDER_NUMBERS,
  parseBatchOrderNumbers
} from './batchOrderNumbers'
import './Orders.less'

const { RangePicker } = DatePicker
const COUNT_VISIBLE_STATUSES = new Set(['pending', 'waiting_print', 'waiting_purchase', 'picking'])
const ONE_DAY_SECONDS = 24 * 60 * 60
const FILTER_TEXT_DEBOUNCE_MS = 350
const REMAINING_SHIPPING_STATUSES = new Set(['pending', 'waiting_print', 'waiting_purchase', 'picking', '待处理', '待打印', '待采购', '配货中'])
const ORDER_DETAIL_MODAL_WIDTH = 1500
const ORDER_DETAIL_MODAL_BODY_HEIGHT = 'min(760px, calc(100dvh - 120px))'
type BatchAction = 'to-printing' | 'confirm-printed' | 'picking' | 'mark-shipped'
type OrderRiskFilter = NonNullable<OrderListParams['risk']>
type RiskHandlingAction = 'handled' | 'unhandled'
const ORDER_RISK_FILTERS = new Set<OrderRiskFilter>(['all', 'unhandled', 'handled', 'overdue', 'due_24'])
const ORDER_RISK_FILTER_OPTIONS: Array<{ label: string; value: OrderRiskFilter }> = [
  { label: '待跟进', value: 'unhandled' },
  { label: '全部风险', value: 'all' },
  { label: '已超时', value: 'overdue' },
  { label: '24小时内到期', value: 'due_24' },
  { label: '已处理', value: 'handled' }
]
const ORDER_TABLE_CONFIG: DataTableConfig = {
  tableKey: 'orders.list',
  primaryColumnKey: 'platform_order_no',
  widthMode: 'adaptive-left',
  columns: [
    { key: 'platform_order_no', title: '订单编号', required: true, fixed: 'left', minWidth: 132, maxWidth: 180 },
    { key: 'platform', title: '平台', minWidth: 88, maxWidth: 140 },
    { key: 'shop_name', title: '店铺', minWidth: 96, maxWidth: 180 },
    { key: 'transaction_id', title: '交易号', minWidth: 120, maxWidth: 180 },
    { key: 'posting_number', title: '交运单号', minWidth: 132, maxWidth: 190 },
    { key: 'tracking_number', title: '货运单号', minWidth: 120, maxWidth: 180 },
    { key: 'status', title: '状态', minWidth: 72, maxWidth: 96 },
    { key: 'platform_status', title: '平台状态', minWidth: 110, maxWidth: 150 },
    { key: 'fulfillment_type', title: '履约类型', minWidth: 86, maxWidth: 110 },
    { key: 'country_name_cn', title: '国家', minWidth: 72, maxWidth: 96 },
    { key: 'logistics_channel', title: '物流渠道', minWidth: 120, maxWidth: 190 },
    { key: 'logistics_match_rule_name', title: '物流匹配规则', minWidth: 140, maxWidth: 220 },
    { key: 'order_amount', title: '订单金额', minWidth: 88, maxWidth: 120 },
    { key: 'payment_at', title: '付款日期', minWidth: 150, maxWidth: 170 },
    { key: 'handover_at', title: '交运时间', minWidth: 150, maxWidth: 170 },
    { key: 'remaining_shipping_time', title: '剩余发货时间', minWidth: 126, maxWidth: 150 },
    { key: 'created_at', title: '订单导入时间', minWidth: 150, maxWidth: 170 },
    { key: 'bsi_order_no', title: 'BSI单号', minWidth: 150, maxWidth: 200 },
    { key: 'actions', title: '操作', fixed: 'right', protectedWidth: 90, settingsHidden: true }
  ]
}

const ORDER_RISK_TABLE_CONFIG: DataTableConfig = {
  tableKey: 'orders.shipping-risk',
  primaryColumnKey: 'platform_order_no',
  widthMode: 'adaptive-left',
  columns: [
    { key: 'platform_order_no', title: '订单编号', required: true, fixed: 'left', minWidth: 132, maxWidth: 180 },
    { key: 'risk_bucket', title: '风险等级', minWidth: 128, maxWidth: 160 },
    { key: 'risk_deadline_at', title: '风险截止时间', minWidth: 150, maxWidth: 170 },
    { key: 'risk_handled', title: '跟进状态', minWidth: 110, maxWidth: 160 },
    ...ORDER_TABLE_CONFIG.columns.filter(
      (column) => !['platform_order_no', 'remaining_shipping_time', 'actions'].includes(column.key)
    ),
    { key: 'actions', title: '操作', fixed: 'right', protectedWidth: 150, settingsHidden: true }
  ]
}

interface FilterValues {
  platform?: string
  shopIds?: number[]
  number?: string
  productKeyword?: string
  paymentRange?: [Dayjs | null, Dayjs | null] | null
}

interface PrintRow {
  id: number
  channelId: string
  channelName: string
  orderNo: string
  trackingNo: string
  hasLabel: boolean
  labelStatus: string
}

interface ChannelStat {
  id: string
  name: string
  hasCount: number
  noCount: number
  selected: boolean
  showHas: boolean
  showNo: boolean
}

function remainingShippingClass(seconds: number | null | undefined): string {
  if (seconds == null) return ''
  if (seconds <= 0) return 'orders-remaining-time orders-remaining-time--overdue'
  if (seconds <= ONE_DAY_SECONDS) return 'orders-remaining-time orders-remaining-time--warning'
  return 'orders-remaining-time orders-remaining-time--ok'
}

function normalizedRiskFilter(value: string | null): OrderRiskFilter | null {
  if (!value || !ORDER_RISK_FILTERS.has(value as OrderRiskFilter)) return null
  return value as OrderRiskFilter
}

function formatRiskDuration(seconds: number): string {
  const totalSeconds = Math.abs(seconds)
  const days = Math.floor(totalSeconds / ONE_DAY_SECONDS)
  const hours = Math.floor((totalSeconds % ONE_DAY_SECONDS) / 3600)
  const minutes = Math.max(1, Math.floor((totalSeconds % 3600) / 60))
  if (days > 0) return `${days}天${hours}小时`
  if (hours > 0) return `${hours}小时${minutes}分`
  return `${minutes}分`
}

function riskTimeText(seconds: number | null | undefined): string {
  if (seconds == null) return '-'
  return seconds < 0 ? `已超时 ${formatRiskDuration(seconds)}` : `剩余 ${formatRiskDuration(seconds)}`
}

function base64ToBytes(base64: string): Uint8Array {
  return Uint8Array.from(atob(base64), (char) => char.charCodeAt(0))
}

function shouldShowRemainingShipping(statusValue?: string | null): boolean {
  return !!statusValue && REMAINING_SHIPPING_STATUSES.has(statusValue)
}

function hasTrackingNumber(order: OrderDto): boolean {
  return isLogisticsLabelExempt(order) || Boolean((order.tracking_number || order.shipment_tracking_number || '').trim())
}

function hasPrintableLabel(order: OrderDto): boolean {
  return isLogisticsLabelExempt(order) || Boolean(order.has_label)
}

function printableLabelStatusText(order: OrderDto): string {
  if (isLogisticsLabelExempt(order)) return '无需面单'
  if (order.has_label) return '已有面单'
  return '缺少面单'
}

function isOverseasWarehouse(order: OrderDto): boolean {
  return Boolean(order.is_overseas_warehouse)
}

function isLogisticsLabelExempt(order: OrderDto): boolean {
  return Boolean(order.is_overseas_warehouse || order.logistics_label_exempt)
}

function fulfillmentTypeText(order: OrderDto): string {
  if (isOverseasWarehouse(order)) return '海外仓'
  if (order.is_joom_offline_shipping) return '线下物流'
  if (order.logistics_label_exempt) return '无需平台面单'
  return order.fulfillment_type || 'FBS'
}

function fulfillmentTypeColor(order: OrderDto): string {
  if (order.is_joom_offline_shipping) return 'orange'
  if (isLogisticsLabelExempt(order)) return 'purple'
  return 'default'
}

function trackingDisplayText(order: OrderDto): string {
  if (isLogisticsLabelExempt(order)) return '无需平台面单'
  return order.tracking_number || order.shipment_tracking_number || ''
}

function logisticsChannelText(order: OrderDto): string {
  if (order.logistics_channel) return order.logistics_channel
  if (order.logistics_match_status === 'manual') return '人工指定'
  return '未匹配'
}

function logisticsChannelColor(order: OrderDto): string {
  if (order.logistics_match_status === 'manual') return 'blue'
  if (order.logistics_channel) return 'success'
  return 'warning'
}

function orderDisplayNumber(order: OrderDto): string {
  return order.platform_order_no || order.posting_number || order.platform_order_id || String(order.id)
}

export function Orders() {
  const { message, modal } = App.useApp()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [form] = Form.useForm<FilterValues>()
  const riskFilter = normalizedRiskFilter(searchParams.get('risk'))
  const riskMode = riskFilter !== null
  const riskShop = searchParams.get('shop') || ''
  const riskShopIds = searchParams.get('shop_ids') || ''
  const riskShopCount = riskShopIds.split(',').filter(Boolean).length
  const initialPlatform = searchParams.get('platform') || undefined
  const [loading, setLoading] = useState(false)
  const [orders, setOrders] = useState<OrderDto[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [status, setStatus] = useState(riskMode ? 'all' : searchParams.get('status') || 'pending')
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [selectedRows, setSelectedRows] = useState<OrderDto[]>([])
  const [visibleExportColumns, setVisibleExportColumns] = useState<DataTableVisibleColumn[]>([])
  const [counts, setCounts] = useState<OrderStatusCounts | null>(null)
  const [submittedFilters, setSubmittedFilters] = useState<FilterValues>({ platform: initialPlatform })
  const [batchNumberModalOpen, setBatchNumberModalOpen] = useState(false)
  const [batchNumberDraft, setBatchNumberDraft] = useState('')
  const [batchNumbers, setBatchNumbers] = useState<string[]>([])
  const [batchSearchSummary, setBatchSearchSummary] = useState<OrderSearchSummary | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [printOpen, setPrintOpen] = useState(false)
  const [printLoading, setPrintLoading] = useState(false)
  const [chineseLabelLoading, setChineseLabelLoading] = useState(false)
  const [batchAction, setBatchAction] = useState<BatchAction | null>(null)
  const [riskAction, setRiskAction] = useState<RiskHandlingAction | null>(null)
  const [printRows, setPrintRows] = useState<OrderDto[]>([])
  const [printSelectedIds, setPrintSelectedIds] = useState<Set<number>>(new Set())
  const [printChannels, setPrintChannels] = useState<ChannelStat[]>([])
  const [detailLoading, setDetailLoading] = useState(false)
  const [detail, setDetail] = useState<OrderDetailDto | null>(null)
  const filterSubmitTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const batchActionRef = useRef(false)
  const platformOptions = useEnabledPlatformOptions()
  const selectedPlatform = Form.useWatch('platform', form)
  const batchNumberParseResult = useMemo(() => parseBatchOrderNumbers(batchNumberDraft), [batchNumberDraft])
  const hasSelectedOrders = selectedRowKeys.length > 0
  const canMarkRiskHandled = selectedRows.some((order) => !order.risk_handled)
  const canReopenRisk = selectedRows.some((order) => order.risk_handled)
  const showToPrinting = !riskMode && status === 'pending'
  const showWaitingPrintActions = !riskMode && status === 'waiting_print'
  const showWaitingPurchaseActions = !riskMode && status === 'waiting_purchase'
  const showPickingActions = !riskMode && status === 'picking'
  const showChineseLabel =
    !riskMode && (status === 'waiting_print' ||
    status === 'waiting_purchase' ||
    status === 'picking' ||
    status === 'shipped' ||
    status === 'delivered')
  const showPrintLabel =
    !riskMode && (status === 'waiting_print' ||
    status === 'waiting_purchase' ||
    status === 'picking' ||
    status === 'shipped' ||
    status === 'delivered')
  const canPrintLabel = hasSelectedOrders
  const canPrintPlatformLabel = hasSelectedOrders && selectedRows.some((order) => !order.is_joom_offline_shipping)
  const showRemainingShippingColumn = riskMode || status === 'all' || shouldShowRemainingShipping(status)

  const printAllRows = useMemo<PrintRow[]>(
    () =>
      printRows.map((order) => ({
        id: order.id,
        channelId: order.platform || 'unknown',
        channelName: formatPlatformLabel(order.platform),
        orderNo: orderDisplayNumber(order),
        trackingNo: trackingDisplayText(order),
        hasLabel: hasPrintableLabel(order),
        labelStatus: printableLabelStatusText(order)
      })),
    [printRows]
  )

  const printVisibleRows = useMemo(() => {
    const channelMap = new Map(printChannels.map((channel) => [channel.id, channel]))
    return printAllRows.filter((row) => {
      const channel = channelMap.get(row.channelId)
      if (!channel || !channel.selected) return false
      return row.hasLabel ? channel.showHas : channel.showNo
    })
  }, [printAllRows, printChannels])

  const selectedVisiblePrintIds = useMemo(
    () => printVisibleRows.filter((row) => printSelectedIds.has(row.id)).map((row) => row.id),
    [printSelectedIds, printVisibleRows]
  )

  const allVisiblePrintSelected =
    printVisibleRows.length > 0 && printVisibleRows.every((row) => printSelectedIds.has(row.id))
  const someVisiblePrintSelected =
    printVisibleRows.some((row) => printSelectedIds.has(row.id)) && !allVisiblePrintSelected

  const printSummary = useMemo(() => {
    const activeChannels = printChannels.filter((channel) => channel.selected)
    if (!activeChannels.length) return '请选择打印平台'
    if (!selectedVisiblePrintIds.length) return '当前未选中可打印订单'
    if (activeChannels.length === 1) {
      return `已选定 ${activeChannels[0].name} 的 ${selectedVisiblePrintIds.length} 条订单`
    }
    return `已选定 ${activeChannels.length} 个平台共 ${selectedVisiblePrintIds.length} 条订单`
  }, [printChannels, selectedVisiblePrintIds.length])
  function clearSelection() {
    setSelectedRowKeys([])
    setSelectedRows([])
  }

  function clearFilterSubmitTimer() {
    if (!filterSubmitTimerRef.current) return
    clearTimeout(filterSubmitTimerRef.current)
    filterSubmitTimerRef.current = null
  }

  function submitFilters(values: FilterValues) {
    clearFilterSubmitTimer()
    setSubmittedFilters(batchNumbers.length ? { ...values, number: undefined } : values)
    setPage(1)
    clearSelection()
  }

  function applyBatchNumberFilter() {
    const { uniqueNumbers, overLimit, tooLongNumbers } = batchNumberParseResult
    if (!uniqueNumbers.length || overLimit || tooLongNumbers.length) return

    clearFilterSubmitTimer()
    form.setFieldValue('number', undefined)
    setBatchNumbers(uniqueNumbers)
    setBatchSearchSummary(null)
    setSubmittedFilters({ ...form.getFieldsValue(), number: undefined })
    setPage(1)
    clearSelection()
    setBatchNumberModalOpen(false)
  }

  function clearBatchNumberFilter() {
    clearFilterSubmitTimer()
    setBatchNumbers([])
    setBatchNumberDraft('')
    setBatchSearchSummary(null)
    setSubmittedFilters({ ...form.getFieldsValue(), number: undefined })
    setPage(1)
    clearSelection()
  }

  function handleFilterValuesChange(changedValues: Partial<FilterValues>, allValues: FilterValues) {
    const shouldDebounce =
      Object.prototype.hasOwnProperty.call(changedValues, 'number') ||
      Object.prototype.hasOwnProperty.call(changedValues, 'productKeyword')

    clearFilterSubmitTimer()
    if (shouldDebounce) {
      filterSubmitTimerRef.current = setTimeout(() => submitFilters(allValues), FILTER_TEXT_DEBOUNCE_MS)
      return
    }

    submitFilters(allValues)
  }

  const queryParams = useMemo<OrderListParams>(() => {
    const params: OrderListParams = {
      page,
      page_size: pageSize,
      status: riskMode || status === 'all' ? undefined : status,
      risk: riskFilter || undefined,
      shop: riskMode && riskShop ? riskShop : undefined,
      shop_ids: submittedFilters.shopIds?.length
        ? submittedFilters.shopIds.join(',')
        : riskMode && riskShopIds
          ? riskShopIds
          : undefined,
      platform: submittedFilters.platform,
      number: batchNumbers.length ? undefined : submittedFilters.number?.trim() || undefined,
      numbers: batchNumbers.length ? batchNumbers : undefined,
      product_keyword: submittedFilters.productKeyword?.trim() || undefined
    }
    const [paymentStart, paymentEnd] = submittedFilters.paymentRange || []
    if (paymentStart && paymentEnd) {
      params.payment_start = paymentStart.format('YYYY-MM-DD')
      params.payment_end = paymentEnd.format('YYYY-MM-DD')
    }
    return params
  }, [page, pageSize, riskFilter, riskMode, riskShop, riskShopIds, status, submittedFilters, batchNumbers])

  async function loadStatusCounts() {
    try {
      const nextCounts = await fetchOrderStatusCounts()
      setCounts(nextCounts)
    } catch {
      // 状态数量只是页签辅助信息，失败时不阻塞订单列表。
    }
  }

  async function refresh() {
    setLoading(true)
    try {
      const list = await listOrders(queryParams)
      setOrders(list.items || [])
      setTotal(list.total || 0)
      setBatchSearchSummary(batchNumbers.length ? list.search_summary || null : null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadStatusCounts()
  }, [])

  useEffect(() => () => clearFilterSubmitTimer(), [])

  useEffect(() => {
    clearSelection()
    refresh()
  }, [queryParams])

  useEffect(() => {
    const next = new URLSearchParams(searchParams)
    if (riskMode || status === 'all') next.delete('status')
    else next.set('status', status)
    if (next.toString() !== searchParams.toString()) setSearchParams(next, { replace: true })
  }, [riskMode, searchParams, setSearchParams, status])

  async function openDetail(row: OrderDto) {
    setDetailOpen(true)
    setDetailLoading(true)
    try {
      setDetail(await fetchOrderDetail(row.id))
    } finally {
      setDetailLoading(false)
    }
  }

  function confirmToPrintingWithMissingTracking(missingRows: OrderDto[]) {
    const preview = missingRows.slice(0, 8).map(orderDisplayNumber)
    const restCount = missingRows.length - preview.length
    return new Promise<boolean>((resolve) => {
      modal.confirm({
        title: '存在无货运单号订单',
        content: (
          <div>
            <p>所选订单中有 {missingRows.length} 条没有货运单号，请等待自动订单任务同步物流信息。</p>
            <p>{preview.join('、')}{restCount > 0 ? ` 等 ${missingRows.length} 条` : ''}</p>
            <p>仍然转入待打印吗？</p>
          </div>
        ),
        okText: '仍然转入待打印',
        cancelText: '取消',
        onOk: () => resolve(true),
        onCancel: () => resolve(false)
      })
    })
  }

  async function runBatch(action: BatchAction) {
    if (batchActionRef.current) return
    const ids = selectedRowKeys.map(Number)
    if (!ids.length) {
      message.warning('请先选择订单')
      return
    }
    let allowMissingTracking = false
    if (action === 'to-printing') {
      const missingTrackingRows = selectedRows.filter((row) => !hasTrackingNumber(row))
      if (missingTrackingRows.length) {
        allowMissingTracking = await confirmToPrintingWithMissingTracking(missingTrackingRows)
        if (!allowMissingTracking) return
      }
    }
    batchActionRef.current = true
    setBatchAction(action)
    try {
      if (action === 'picking') {
        const res = await batchToPicking(ids)
        message.success(res.message || `已生成采购单并转入配货中：${res.updated}`)
      }
      if (action === 'to-printing') {
        const res = await batchToPrinting(ids, { allowMissingTracking })
        message.success(res.message || `已转入待打印：${res.updated}`)
      }
      if (action === 'confirm-printed') {
        const res = await batchConfirmPrinted(ids)
        message.success(res.message || `已确认打印并转入待采购：${res.updated}`)
      }
      if (action === 'mark-shipped') {
        const res = await batchMarkShipped(ids)
        message.success(res.message || `已标记发货：${res.updated}`)
      }
      clearSelection()
      await refresh()
      loadStatusCounts()
    } catch (e) {
      const detailText = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      message.error(detailText || '批量操作失败')
    } finally {
      batchActionRef.current = false
      setBatchAction(null)
    }
  }

  async function runRiskHandling(orderIds: number[], handled: boolean) {
    const ids = Array.from(new Set(orderIds.map(Number).filter(Boolean)))
    if (!ids.length || riskAction) return
    setRiskAction(handled ? 'handled' : 'unhandled')
    try {
      const response = await batchUpdateRiskHandling(ids, { handled })
      message.success(response.message || (handled ? '已标记风险处理' : '已取消风险处理'))
      clearSelection()
      await refresh()
    } catch (error) {
      const detailText = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      message.error(detailText || '风险处理状态更新失败')
    } finally {
      setRiskAction(null)
    }
  }

  function confirmRiskHandling(orderIds: number[], handled: boolean) {
    const ids = Array.from(new Set(orderIds.map(Number).filter(Boolean)))
    if (!ids.length) {
      message.warning('请先选择订单')
      return
    }
    modal.confirm({
      title: handled ? '标记风险已处理' : '取消风险处理标记',
      content: handled
        ? `确认将选中的 ${ids.length} 条订单标记为已处理吗？订单实际发货状态不会改变。`
        : `确认将选中的 ${ids.length} 条订单恢复为待跟进吗？`,
      okText: handled ? '确认处理' : '恢复待跟进',
      cancelText: '取消',
      onOk: () => runRiskHandling(ids, handled)
    })
  }

  function openPrintDialog() {
    if (!selectedRows.length) {
      message.warning('请先选择订单')
      return
    }
    const platformLabelRows = selectedRows.filter((order) => !order.is_joom_offline_shipping)
    if (!platformLabelRows.length) {
      message.info('Joom 线下物流订单不使用平台在线面单')
      return
    }
    setPrintRows(platformLabelRows)
    const channelMap = new Map<string, ChannelStat>()
    platformLabelRows.forEach((order) => {
      const channelId = order.platform || 'unknown'
      if (!channelMap.has(channelId)) {
        channelMap.set(channelId, {
          id: channelId,
          name: formatPlatformLabel(order.platform),
          hasCount: 0,
          noCount: 0,
          selected: true,
          showHas: true,
          showNo: true
        })
      }
      const channel = channelMap.get(channelId)
      if (!channel) return
      if (hasPrintableLabel(order)) channel.hasCount += 1
      else channel.noCount += 1
    })
    const channels = Array.from(channelMap.values()).map((channel) => {
      if (channel.hasCount > 0) return { ...channel, showHas: true, showNo: false }
      return { ...channel, showHas: false, showNo: true }
    })
    const printableIds = platformLabelRows.filter((order) => hasPrintableLabel(order)).map((order) => order.id)
    setPrintChannels(channels)
    setPrintSelectedIds(new Set(printableIds.length ? printableIds : platformLabelRows.map((order) => order.id)))
    setPrintOpen(true)
  }

  function openPdfResponse(res: PrintLabelResponse): boolean {
    if (!res.pdf_base64) return false
    const bytes = base64ToBytes(res.pdf_base64)
    const file = new File([bytes], res.filename || 'labels.pdf', { type: res.content_type || 'application/pdf' })
    const url = window.URL.createObjectURL(file)
    const win = window.open(url, '_blank')
    if (!win) {
      window.URL.revokeObjectURL(url)
      message.error('无法打开 PDF 预览页签，请检查浏览器弹窗设置')
      return false
    }
    return true
  }

  async function confirmPrintLabels() {
    const ids = selectedVisiblePrintIds
    if (!ids.length) {
      message.warning('请选择要打印的订单')
      return
    }
    setPrintLoading(true)
    try {
      const res = await batchPrintLabel(ids)
      if (res.pdf_base64 && !openPdfResponse(res)) return
      let successText = res.printed > 0
        ? `已打开 ${res.printed} / ${res.total} 条面单（缓存 ${res.cached}，新拉取 ${res.fetched}`
        : `已处理 ${res.total} 条订单，无需打开面单（缓存 ${res.cached}，新拉取 ${res.fetched}`
      if (res.skipped) successText += `，忽略 ${res.skipped}`
      if (res.failed) successText += `，失败 ${res.failed}`
      successText += '）'
      message.success(successText)
      clearSelection()
      await refresh()
      loadStatusCounts()
    } catch (e) {
      const detailText = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      message.error(detailText || '面单获取失败')
    } finally {
      setPrintLoading(false)
    }
  }

  async function printChineseLabels() {
    const ids = selectedRowKeys.map(Number)
    if (!ids.length) {
      message.warning('请先选择订单')
      return
    }
    setChineseLabelLoading(true)
    try {
      const res = await batchPrintChineseLabel(ids)
      if (res.pdf_base64 && !openPdfResponse(res)) return
      message.success(`已打开 ${res.printed} / ${res.total} 条中文标签`)
    } catch (e) {
      const detailText = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      message.error(detailText || '中文标签生成失败')
    } finally {
      setChineseLabelLoading(false)
    }
  }

  function togglePrintBucket(id: string, bucket: 'has' | 'no') {
    setPrintChannels((channels) =>
      channels.map((channel) => {
        if (channel.id !== id) return channel
        const next = bucket === 'has' ? { ...channel, showHas: !channel.showHas } : { ...channel, showNo: !channel.showNo }
        return { ...next, selected: next.showHas || next.showNo }
      })
    )
  }

  function togglePrintChannel(id: string) {
    setPrintChannels((channels) =>
      channels.map((channel) => {
        if (channel.id !== id) return channel
        const selected = !channel.selected
        return { ...channel, selected, showHas: selected, showNo: selected }
      })
    )
  }

  function openPrintSettings() {
    setPrintOpen(false)
    navigate('/system-settings')
  }

  function selectAllPrintChannels() {
    setPrintChannels((channels) => channels.map((channel) => ({ ...channel, selected: true, showHas: true, showNo: true })))
  }

  function clearAllPrintChannels() {
    setPrintChannels((channels) => channels.map((channel) => ({ ...channel, selected: false, showHas: false, showNo: false })))
  }

  function togglePrintRow(id: number) {
    setPrintSelectedIds((ids) => {
      const next = new Set(ids)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleAllVisiblePrintRows(checked: boolean) {
    setPrintSelectedIds((ids) => {
      const next = new Set(ids)
      for (const row of printVisibleRows) {
        if (checked) next.add(row.id)
        else next.delete(row.id)
      }
      return next
    })
  }

  async function onExport() {
    const selectedOrderIds = selectedRowKeys.map(Number)
    const exportColumnKeys = visibleExportColumns.map((column) => column.key)
    const resp = batchNumbers.length
      ? await http.post<Blob>(
          '/api/v1/orders/export',
          {
            ...queryParams,
            order_ids: selectedOrderIds,
            columns: exportColumnKeys
          },
          { responseType: 'blob' }
        )
      : await http.get<Blob>('/api/v1/orders/export', {
          params: {
            ...queryParams,
            order_ids: selectedOrderIds.length ? selectedOrderIds.join(',') : undefined,
            columns: exportColumnKeys.length ? exportColumnKeys.join(',') : undefined
          },
          responseType: 'blob'
        })
    downloadBlob(resp.data, `orders_${Date.now()}.xlsx`)
    message.success('已导出')
  }

  function resetFilters() {
    clearFilterSubmitTimer()
    form.resetFields()
    setBatchNumbers([])
    setBatchNumberDraft('')
    setBatchSearchSummary(null)
    setSubmittedFilters({})
    setPage(1)
    setStatus('all')
    if (riskMode) {
      const next = new URLSearchParams(searchParams)
      next.delete('risk')
      next.delete('shop')
      next.delete('shop_ids')
      setSearchParams(next, { replace: true })
    }
    clearSelection()
  }

  function clearRiskShopFilter() {
    const next = new URLSearchParams(searchParams)
    next.delete('shop')
    setSearchParams(next, { replace: true })
    setPage(1)
    clearSelection()
  }

  function clearRiskShopScope() {
    const next = new URLSearchParams(searchParams)
    next.delete('shop_ids')
    setSearchParams(next, { replace: true })
    setPage(1)
    clearSelection()
  }

  const columns: ColumnsType<OrderDto> = [
    { key: 'platform', title: '平台', dataIndex: 'platform', render: (value) => formatPlatformLabel(value) },
    { key: 'shop_name', title: '店铺', dataIndex: 'shop_name', ellipsis: true },
    { key: 'transaction_id', title: '交易号', dataIndex: 'transaction_id', ellipsis: true },
    { key: 'platform_order_no', title: '订单编号', dataIndex: 'platform_order_no', ellipsis: true, render: (_, row) => orderDisplayNumber(row) },
    ...(riskMode
      ? [
          {
            key: 'risk_bucket',
            title: '风险等级',
            dataIndex: 'risk_bucket',
            render: (_: unknown, row: OrderDto) => (
              <Tag color={row.risk_bucket.startsWith('overdue') ? 'error' : 'warning'}>
                {row.risk_bucket.startsWith('overdue') ? '已超时' : '24小时内到期'}
              </Tag>
            )
          },
          {
            key: 'risk_deadline_at',
            title: '风险截止时间',
            dataIndex: 'risk_deadline_at',
            render: (value: string | null) => <TimeText value={value} seconds />
          },
          {
            key: 'risk_handled',
            title: '跟进状态',
            dataIndex: 'risk_handled',
            render: (_: unknown, row: OrderDto) => (
              <Space size={4}>
                <Tag color={row.risk_handled ? 'success' : 'processing'}>{row.risk_handled ? '已处理' : '待跟进'}</Tag>
                {row.risk_handled_by ? <span className="orders-risk-handler">{row.risk_handled_by}</span> : null}
              </Space>
            )
          }
        ]
      : []),
    { key: 'posting_number', title: '交运单号', dataIndex: 'posting_number', ellipsis: true, render: (value) => value || '-' },
    { key: 'tracking_number', title: '货运单号', dataIndex: 'tracking_number', ellipsis: true, render: (_, row) => trackingDisplayText(row) || '-' },
    {
      key: 'status',
      title: '状态',
      dataIndex: 'status',
      render: (_, row) => (
        <Tag color={ORDER_STATUS_COLOR[row.status] || 'default'}>{row.status || '-'}</Tag>
      )
    },
    { key: 'platform_status', title: '平台状态', dataIndex: 'platform_status', ellipsis: true },
    {
      key: 'fulfillment_type',
      title: '履约类型',
      dataIndex: 'fulfillment_type',
      render: (_, row) => (
        <Tag color={fulfillmentTypeColor(row)}>{fulfillmentTypeText(row)}</Tag>
      )
    },
    { key: 'country_name_cn', title: '国家', dataIndex: 'country_name_cn', render: (_, row) => row.country_name_cn || row.country_code || '-' },
    {
      key: 'logistics_channel',
      title: '物流渠道',
      dataIndex: 'logistics_channel',
      ellipsis: true,
      render: (_, row) => <Tag color={logisticsChannelColor(row)}>{logisticsChannelText(row)}</Tag>
    },
    {
      key: 'logistics_match_rule_name',
      title: '物流匹配规则',
      dataIndex: 'logistics_match_rule_name',
      ellipsis: true,
      render: (_, row) => row.logistics_match_rule_name || (row.logistics_match_status === 'unmatched' ? '未匹配' : '-')
    },
    {
      key: 'order_amount',
      title: '订单金额',
      dataIndex: 'order_amount',
      align: 'right',
      render: (value, row) => <MoneyText amount={value} currency={row.currency} />
    },
    {
      key: 'payment_at',
      title: '付款日期',
      dataIndex: 'payment_at',
      render: (value) => <TimeText value={value} seconds />
    },
    {
      key: 'handover_at',
      title: '交运时间',
      dataIndex: 'handover_at',
      render: (value) => <TimeText value={value} seconds />
    },
    ...(showRemainingShippingColumn
      ? [
          {
          key: 'remaining_shipping_time',
            title: riskMode ? '风险剩余时间' : '剩余发货时间',
            dataIndex: 'remaining_shipping_time',
            render: (value, row) =>
              shouldShowRemainingShipping(row.status) ? (
                <span className={remainingShippingClass(row.remaining_shipping_seconds)}>
                  {riskMode ? riskTimeText(row.remaining_shipping_seconds) : value || '-'}
                </span>
              ) : (
                ''
              )
          } as ColumnsType<OrderDto>[number]
        ]
      : []),
    {
      key: 'created_at',
      title: '订单导入时间',
      dataIndex: 'created_at',
      render: (value) => <TimeText value={value} seconds />
    },
    {
      key: 'bsi_order_no',
      title: 'BSI单号',
      dataIndex: 'bsi_order_no',
      ellipsis: true,
      render: (value) => value || '-'
    },
    {
      key: 'actions',
      title: '操作',
      width: riskMode ? 150 : 90,
      fixed: 'right',
      render: (_, row) => (
        <Space size={0}>
          <Button size="small" type="link" onClick={() => openDetail(row)}>
            详情
          </Button>
          {riskMode ? (
            <Button
              size="small"
              type="link"
              disabled={!!riskAction}
              onClick={() => confirmRiskHandling([row.id], !row.risk_handled)}
            >
              {row.risk_handled ? '恢复' : '标记处理'}
            </Button>
          ) : null}
        </Space>
      )
    }
  ]

  const itemColumns: DataTableColumnsType<OrderDetailItemDto> = [
    {
      title: '产品编码',
      dataIndex: 'product_code',
      width: 130,
      minWidth: 120,
      maxWidth: 130,
      ellipsis: true,
      render: (value) => value || '-'
    },
    {
      title: '产品中文名称',
      dataIndex: 'product_name',
      width: 240,
      minWidth: 180,
      maxWidth: 240,
      ellipsis: true,
      render: (value) => value || '-'
    },
    { title: 'SKU', dataIndex: 'sku', width: 160, minWidth: 130, maxWidth: 160, ellipsis: true },
    { title: '商品名称', dataIndex: 'platform_product_name', minWidth: 300, maxWidth: 440, flex: 1, ellipsis: true },
    { title: '数量', dataIndex: 'quantity', width: 72, minWidth: 64, maxWidth: 72, align: 'right' },
    {
      title: '单价',
      dataIndex: 'unit_price',
      width: 110,
      minWidth: 100,
      maxWidth: 110,
      align: 'right',
      render: (value, row) => formatMoney(value, row.currency || detail?.currency)
    }
  ]

  const pagination: TablePaginationConfig = {
    current: page,
    pageSize,
    total,
    showSizeChanger: true,
    showLessItems: true,
    pageSizeOptions: [50, 100, 500],
    showTotal: (value) => `共 ${value} 条`,
    onChange: (nextPage, nextPageSize) => {
      setPage(nextPage)
      setPageSize(nextPageSize)
    }
  }

  return (
    <div className="page-card orders-page">
      <div className="orders-header">
        <div className="orders-title-wrap">
          <h2>{riskMode ? '待发货超时风险' : '订单列表'}</h2>
          {riskMode ? <span className="orders-risk-total">当前 {total} 条</span> : null}
        </div>
        {riskMode ? (
          <Button
            type="link"
            icon={<ArrowLeftOutlined />}
            onClick={() => {
              setStatus('pending')
              navigate('/orders?status=pending')
            }}
          >
            返回订单列表
          </Button>
        ) : null}
      </div>

      {riskMode ? (
        <div className="orders-risk-toolbar">
          <Alert
            className="orders-risk-alert"
            type="warning"
            showIcon
            message="仅显示已超时或24小时内到期的待发货订单"
          />
          <Space wrap>
            <Segmented
              value={riskFilter}
              options={ORDER_RISK_FILTER_OPTIONS}
              onChange={(value) => {
                const next = new URLSearchParams(searchParams)
                next.set('risk', value as OrderRiskFilter)
                next.delete('status')
                setSearchParams(next, { replace: true })
                setPage(1)
                clearSelection()
              }}
            />
            {riskShop ? <Tag closable onClose={clearRiskShopFilter}>店铺：{riskShop}</Tag> : null}
            {riskShopCount ? (
              <Tag closable onClose={clearRiskShopScope}>仪表盘店铺范围：{riskShopCount}家</Tag>
            ) : null}
          </Space>
        </div>
      ) : (
        <Tabs
          className="orders-status-tabs"
          activeKey={status}
          onChange={(key) => {
            setStatus(key)
            setPage(1)
            clearSelection()
          }}
          items={ORDER_STATUSES.filter((item) => item.code !== 'awaiting_pickup').map((item) => ({
            key: item.code,
            label: (
              <span className="orders-status-tab">
                <span className="orders-status-tab__label">{item.label}</span>
                {counts && COUNT_VISIBLE_STATUSES.has(item.code) ? (
                  <span className="orders-status-tab__badge">{counts[item.code] ?? 0}</span>
                ) : null}
              </span>
            )
          }))}
        />
      )}

      <Form
        form={form}
        layout="inline"
        className="orders-filter"
        initialValues={{ platform: initialPlatform }}
        onValuesChange={handleFilterValuesChange}
        onFinish={submitFilters}
      >
        <Form.Item label="平台" name="platform">
          <Select
            allowClear
            placeholder="全部平台"
            style={{ width: 180 }}
            options={platformOptions}
          />
        </Form.Item>
        <Form.Item label="店铺" name="shopIds">
          <ShopMultiSelect platform={selectedPlatform} />
        </Form.Item>
        <Form.Item label="单号">
          <Space.Compact>
            <Form.Item name="number" noStyle>
              <Input
                allowClear
                disabled={batchNumbers.length > 0}
                placeholder={batchNumbers.length ? `已输入 ${batchNumbers.length} 个单号` : '交易号 / 订单编号 / 货运单号'}
                style={{ width: 260 }}
              />
            </Form.Item>
            <Button onClick={() => setBatchNumberModalOpen(true)}>
              {batchNumbers.length ? '编辑' : '批量'}
            </Button>
            {batchNumbers.length ? (
              <Button
                aria-label="清除批量单号"
                title="清除批量单号"
                icon={<CloseOutlined />}
                onClick={clearBatchNumberFilter}
              />
            ) : null}
          </Space.Compact>
        </Form.Item>
        <Form.Item label="商品" name="productKeyword">
          <Input allowClear placeholder="商品名称 / 中文名称 / SKU" style={{ width: 280 }} />
        </Form.Item>
        <Form.Item label="付款时间" name="paymentRange">
          <RangePicker allowClear format="YYYY-MM-DD" />
        </Form.Item>
        <Form.Item>
          <Space>
            <Button type="primary" htmlType="submit">
              查询
            </Button>
            <Button onClick={resetFilters}>重置</Button>
          </Space>
        </Form.Item>
      </Form>

      {batchNumbers.length && batchSearchSummary ? (
        <Alert
          className="orders-batch-summary"
          type={batchSearchSummary.unmatched_numbers.length ? 'warning' : 'success'}
          showIcon
          message={`批量查询匹配 ${batchSearchSummary.matched}/${batchSearchSummary.unique} 个单号，共 ${total} 条订单`}
          description={
            batchSearchSummary.unmatched_numbers.length ? (
              <span className="orders-batch-summary__numbers">
                未匹配：{batchSearchSummary.unmatched_numbers.join('、')}
              </span>
            ) : undefined
          }
        />
      ) : null}

      <div className="toolbar-row">
        {riskMode ? (
          <Space wrap>
            <Button
              type="primary"
              icon={<CheckCircleOutlined />}
              disabled={!hasSelectedOrders || !canMarkRiskHandled || !!riskAction}
              loading={riskAction === 'handled'}
              onClick={() => confirmRiskHandling(selectedRowKeys.map(Number), true)}
            >
              标记已处理
            </Button>
            <Button
              icon={<UndoOutlined />}
              disabled={!hasSelectedOrders || !canReopenRisk || !!riskAction}
              loading={riskAction === 'unhandled'}
              onClick={() => confirmRiskHandling(selectedRowKeys.map(Number), false)}
            >
              恢复待跟进
            </Button>
          </Space>
        ) : null}
        {showToPrinting ? (
          <Button
            disabled={!hasSelectedOrders || !!batchAction}
            loading={batchAction === 'to-printing'}
            onClick={() => runBatch('to-printing')}
          >
            转入待打印
          </Button>
        ) : null}
        {showPrintLabel ? (
          <Button
            disabled={!canPrintPlatformLabel}
            title={
              !hasSelectedOrders
                ? '请选择订单'
                : !canPrintPlatformLabel
                  ? 'Joom 线下物流订单不使用平台在线面单'
                  : '本地无缓存时会尝试从平台拉取面单'
            }
            onClick={openPrintDialog}
          >
            打印面单
          </Button>
        ) : null}
        {showChineseLabel ? (
          <Button
            disabled={!canPrintLabel}
            loading={chineseLabelLoading}
            title={!hasSelectedOrders ? '请选择订单' : '生成 100mm x 20mm 中文标签 PDF'}
            onClick={printChineseLabels}
          >
            打印中文标签
          </Button>
        ) : null}
        {showWaitingPrintActions ? (
          <Button
            disabled={!hasSelectedOrders || !!batchAction}
            loading={batchAction === 'confirm-printed'}
            onClick={() => runBatch('confirm-printed')}
          >
            确认已打印
          </Button>
        ) : null}
        {showWaitingPurchaseActions ? (
          <Button
            disabled={!hasSelectedOrders || !!batchAction}
            loading={batchAction === 'picking'}
            onClick={() => runBatch('picking')}
          >
            转入配货中
          </Button>
        ) : null}
        {showPickingActions ? (
          <Button
            disabled={!hasSelectedOrders || !!batchAction}
            loading={batchAction === 'mark-shipped'}
            onClick={() => runBatch('mark-shipped')}
          >
            标记已发货</Button>
        ) : null}
        <Button icon={<ExportOutlined />} onClick={onExport}>
          导出数据
        </Button>
      </div>

      <DataTable
        rowKey="id"
        tableConfig={riskMode ? ORDER_RISK_TABLE_CONFIG : ORDER_TABLE_CONFIG}
        loading={loading}
        dataSource={orders}
        columns={columns}
        onVisibleColumnsChange={setVisibleExportColumns}
        pagination={pagination}
        rowSelection={{
          selectedRowKeys,
          onChange: (keys, rows) => {
            setSelectedRowKeys(keys)
            setSelectedRows(rows)
          }
        }}
        onRow={(row) => ({
          onDoubleClick: () => openDetail(row)
        })}
      />

      <Modal
        open={batchNumberModalOpen}
        title="批量查询单号（精确匹配）"
        width={620}
        okText="应用并查询"
        cancelText="取消"
        okButtonProps={{
          disabled:
            !batchNumberParseResult.uniqueNumbers.length ||
            batchNumberParseResult.overLimit ||
            batchNumberParseResult.tooLongNumbers.length > 0
        }}
        onOk={applyBatchNumberFilter}
        onCancel={() => setBatchNumberModalOpen(false)}
      >
        <div className="orders-batch-modal">
          <Input.TextArea
            aria-label="批量单号"
            rows={10}
            value={batchNumberDraft}
            placeholder="粘贴单号，支持换行、逗号或分号分隔"
            onChange={(event) => setBatchNumberDraft(event.target.value)}
          />
          <div className="orders-batch-modal__count" aria-live="polite">
            识别 {batchNumberParseResult.tokens.length} 个
            {batchNumberParseResult.duplicateCount ? `，去重 ${batchNumberParseResult.duplicateCount} 个` : ''}
            ，可查询 {batchNumberParseResult.uniqueNumbers.length} 个
          </div>
          {batchNumberParseResult.overLimit ? (
            <Alert type="error" showIcon message={`批量查询最多支持 ${MAX_BATCH_ORDER_NUMBERS} 个不同单号`} />
          ) : null}
          {batchNumberParseResult.tooLongNumbers.length ? (
            <Alert
              type="error"
              showIcon
              message={`有 ${batchNumberParseResult.tooLongNumbers.length} 个单号超过 ${MAX_BATCH_ORDER_NUMBER_LENGTH} 个字符`}
            />
          ) : null}
        </div>
      </Modal>

      <Modal
        open={detailOpen}
        title="订单详情"
        width={ORDER_DETAIL_MODAL_WIDTH}
        className="order-detail-modal"
        centered
        footer={null}
        destroyOnClose
        styles={{ body: { height: ORDER_DETAIL_MODAL_BODY_HEIGHT, overflow: 'hidden' } }}
        onCancel={() => {
          setDetailOpen(false)
          setDetail(null)
        }}
      >
        <div className="order-detail-content">
          <Spin spinning={detailLoading}>
            {detail ? (
              <Tabs
                className="order-detail-tabs"
                items={[
                  {
                    key: 'info',
                    label: '订单信息',
                    children: (
                      <>
                        <h3 className="section-title">订单信息</h3>
                        <Descriptions column={3} bordered size="small">
                          <Descriptions.Item label="平台/站点">
                            {formatPlatformLabel(detail.platform)}
                            {detail.site ? ' / ' + detail.site : ''}
                          </Descriptions.Item>
                          <Descriptions.Item label="店铺">{detail.shop_name || '-'}</Descriptions.Item>
                          <Descriptions.Item label="状态">
                            <Tag color={ORDER_STATUS_COLOR[detail.status] || 'default'}>{detail.status || '-'}</Tag>
                          </Descriptions.Item>
                          <Descriptions.Item label="交易号">{detail.transaction_id || '-'}</Descriptions.Item>
                          <Descriptions.Item label="订单编号">{orderDisplayNumber(detail)}</Descriptions.Item>
                          <Descriptions.Item label="交运单号">{detail.posting_number || '-'}</Descriptions.Item>
                          <Descriptions.Item label="货运单号">{trackingDisplayText(detail) || '-'}</Descriptions.Item>
                          <Descriptions.Item label="平台状态">{detail.platform_status || '-'}</Descriptions.Item>
                          <Descriptions.Item label="履约类型">
                            <Tag color={fulfillmentTypeColor(detail)}>{fulfillmentTypeText(detail)}</Tag>
                          </Descriptions.Item>
                          <Descriptions.Item label="订单金额">{formatMoney(detail.order_amount, detail.currency)}</Descriptions.Item>
                        </Descriptions>

                        <h3 className="section-title">客户与物流</h3>
                        <Descriptions column={3} bordered size="small">
                          <Descriptions.Item label="客户ID">{detail.customer_id || '-'}</Descriptions.Item>
                          <Descriptions.Item label="客户姓名">{detail.customer_name || '-'}</Descriptions.Item>
                          <Descriptions.Item label="国家">{detail.country_name_cn || detail.country_code || '-'}</Descriptions.Item>
                          <Descriptions.Item label="国家二字码">{detail.country_code || '-'}</Descriptions.Item>
                          <Descriptions.Item label="买家自选物流" span={2}>
                            {detail.buyer_selected_logistics || '-'}
                          </Descriptions.Item>
                          <Descriptions.Item label="物流渠道">
                            <Tag color={logisticsChannelColor(detail)}>{logisticsChannelText(detail)}</Tag>
                          </Descriptions.Item>
                          <Descriptions.Item label="BSI物流草稿单号">{detail.bsi_order_no || '-'}</Descriptions.Item>
                          <Descriptions.Item label="BSI提交时间">{formatTime(detail.bsi_submitted_at, true)}</Descriptions.Item>
                          <Descriptions.Item label="物流匹配规则">{detail.logistics_match_rule_name || '-'}</Descriptions.Item>
                          <Descriptions.Item label="匹配时间">{formatTime(detail.logistics_matched_at, true)}</Descriptions.Item>
                          <Descriptions.Item label="内部单号">{detail.internal_order_no || '-'}</Descriptions.Item>
                          <Descriptions.Item label="匹配原因" span={3}>
                            {detail.logistics_match_reason || '-'}
                          </Descriptions.Item>
                        </Descriptions>

                        <h3 className="section-title">时间节点</h3>
                        <Descriptions column={3} bordered size="small">
                          <Descriptions.Item label="付款时间">{formatTime(detail.payment_at, true)}</Descriptions.Item>
                          <Descriptions.Item label="导入时间">{formatTime(detail.created_at, true)}</Descriptions.Item>
                          <Descriptions.Item label="配货时间">{formatTime(detail.picking_at, true)}</Descriptions.Item>
                          <Descriptions.Item label="打印标签时间">{formatTime(detail.label_printed_at, true)}</Descriptions.Item>
                          <Descriptions.Item label="标记发货时间">{formatTime(detail.marked_shipped_at, true)}</Descriptions.Item>
                          <Descriptions.Item label="交运时间">{formatTime(detail.handover_at, true)}</Descriptions.Item>
                          <Descriptions.Item label="最后发货期限">{formatTimeUtc(detail.shipping_deadline_at)}</Descriptions.Item>
                          <Descriptions.Item label="平台指定交运时间">{formatTimeUtc(detail.platform_handover_deadline)}</Descriptions.Item>
                        {shouldShowRemainingShipping(detail.status) ? (
                          <Descriptions.Item label="剩余发货时间">{detail.remaining_shipping_time || '-'}</Descriptions.Item>
                        ) : null}
                      </Descriptions>

                        <h3 className="section-title">商品明细</h3>
                        <DataTable
                          rowKey="id"
                          size="small"
                          dataSource={detail.items || []}
                          columns={itemColumns}
                          pagination={false}
                        />
                      </>
                    )
                  },
                  {
                    key: 'operationLogs',
                    label: '操作日志',
                    children: <OrderOperationLogTable orderId={detail.id} />
                  }
                ]}
              />
            ) : null}
          </Spin>
        </div>
      </Modal>

      <Modal
        open={printOpen}
        title="打印面单"
        width={900}
        footer={null}
        onCancel={() => setPrintOpen(false)}
        destroyOnClose
      >
        <div className="print-modal print-modal--side">
          <aside className="channel-section">
            <div className="section-head">
              <span>选择平台</span>
              <Space size={6}>
                <Button size="small" onClick={selectAllPrintChannels}>
                  全选
                </Button>
                <Button size="small" onClick={clearAllPrintChannels}>
                  全不选
                </Button>
              </Space>
            </div>
            <div className="channel-grid">
              {printChannels.map((channel) => (
                <div
                  key={channel.id}
                  className={`channel-card${channel.selected ? ' selected' : ''}`}
                  role="button"
                  aria-pressed={channel.selected}
                  tabIndex={0}
                  onClick={() => togglePrintChannel(channel.id)}
                  onKeyDown={(event) => {
                    if (event.currentTarget !== event.target) return
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      togglePrintChannel(channel.id)
                    }
                  }}
                >
                  <div className="channel-name">{channel.name}</div>
                  <div className="channel-actions">
                    <button
                      type="button"
                      className={`channel-segment channel-segment--has${channel.showHas ? ' active' : ''}`}
                      aria-pressed={channel.showHas}
                      onClick={(event) => {
                        event.stopPropagation()
                        togglePrintBucket(channel.id, 'has')
                      }}
                    >
                      <span>有面单</span>
                      <strong>{channel.hasCount}</strong>
                    </button>
                    <button
                      type="button"
                      className={`channel-segment channel-segment--no${channel.showNo ? ' active' : ''}`}
                      aria-pressed={channel.showNo}
                      onClick={(event) => {
                        event.stopPropagation()
                        togglePrintBucket(channel.id, 'no')
                      }}
                    >
                      <span>缺面单</span>
                      <strong>{channel.noCount}</strong>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </aside>

          <div className="print-modal__main">
            <section className="orders-section">
              <div className="section-head">
                <span>选择订单</span>
              </div>
              <DataTable<PrintRow>
                rowKey="id"
                size="small"
                dataSource={printVisibleRows}
                pagination={false}
                columns={[
                  {
                    title: (
                      <Checkbox
                        checked={allVisiblePrintSelected}
                        indeterminate={someVisiblePrintSelected}
                        onChange={(event) => toggleAllVisiblePrintRows(event.target.checked)}
                      />
                    ),
                    key: 'check',
                    width: 48,
                    render: (_, record) => (
                      <Checkbox checked={printSelectedIds.has(record.id)} onChange={() => togglePrintRow(record.id)} />
                    )
                  },
                  { title: '平台', dataIndex: 'channelName', width: 120, ellipsis: true },
                  { title: '订单编号', dataIndex: 'orderNo', ellipsis: true },
                  {
                    title: '面单状态',
                    dataIndex: 'labelStatus',
                    width: 120,
                    render: (_, record) => <Tag color={record.hasLabel ? 'success' : 'warning'}>{record.labelStatus}</Tag>
                  },
                  { title: '物流单号', dataIndex: 'trackingNo', width: 220, ellipsis: true }
                ]}
                scroll={{ y: 320 }}
              />
            </section>

            <div className="confirm-bar">
              <span className="summary">{printSummary}</span>
              <Button type="primary" loading={printLoading} disabled={!selectedVisiblePrintIds.length} onClick={confirmPrintLabels}>
                {printLoading ? '拉取并打印中' : '确定打印'}
              </Button>
            </div>
          </div>
        </div>
      </Modal>
    </div>
  )
}
