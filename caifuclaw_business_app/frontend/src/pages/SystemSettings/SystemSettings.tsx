/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from '@/router/navigation'
import type { DragEvent } from 'react'
import { CheckCircleOutlined, DeleteOutlined, EditOutlined, HolderOutlined, PauseCircleOutlined, PlayCircleOutlined, PlusOutlined, ApiOutlined } from '@ant-design/icons'
import {
  App,
  Button,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Tabs,
  Tag
} from 'antd'
import { DataTable, type DataTableColumnsType } from '@/components/DataTable'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import {
  createPrintSetting,
  createScheduledTask,
  deletePrintSetting,
  deleteScheduledTask,
  exportRunPdfsBlob,
  getEmailSmtp,
  getRunOrders,
  getRunPlatforms,
  getRunSteps,
  getTranslationProviderSetting,
  listEmailProviders,
  listModelEndpoints,
  listModelSettings,
  listPlatformSettings,
  listPrinters,
  listPrintSettings,
  listScheduledTaskRuns,
  listScheduledTasks,
  listShippingDeadlineSettings,
  listTranslationProviderOptions,
  reprintRunPlatform,
  reprintRunOrder,
  runScheduledTask,
  testEmailSmtp,
  testModelSettingConnection,
  testTranslationProviderSetting,
  getWecomRobotSetting,
  listWecomMentionUsers,
  testWecomRobotSetting,
  toggleScheduledTask,
  createModelEndpoint,
  createModelSetting,
  deleteModelEndpoint,
  deleteModelSetting,
  updateEmailSmtp,
  updateModelEndpoint,
  updateModelSetting,
  updatePlatformSetting,
  updatePrintSetting,
  updateScheduledTask,
  updateShippingDeadlineSettings,
  updateTranslationProviderSetting,
  updateWecomRobotSetting,
  type EmailNotificationRecipientsDto,
  type EmailProviderDto,
  type EmailSmtpDto,
  type ModelEndpointDto,
  type ModelEndpointPayload,
  type ModelSettingDto,
  type ModelSettingPayload,
  type PlatformSettingDto,
  type PrintSettingDto,
  type PrintSettingPayload,
  type PrinterDto,
  type ScheduledTaskSettings,
  type ScheduledTaskDto,
  type ScheduledTaskPayload,
  type ScheduledTaskRunDto,
  type ScheduledTaskRunOrderDto,
  type ScheduledTaskRunPlatformDto,
  type ScheduledTaskRunStepDto,
  type ShippingDeadlineSettingDto,
  type ShippingDeadlineSettingPayload,
  type TranslationProviderOptionDto,
  type TranslationProviderSettingDto,
  type TranslationProviderSettingPayload,
  type WeComRobotSettingDto,
  type WeComRobotSettingPayload,
  type WeComMentionUserOptionDto
} from '@/api/system'
import { formatPlatformLabel, PRINT_ONLY_PLATFORM_OPTIONS } from '@/stores/dict'
import { platformSettingsToOptions } from '@/hooks/useEnabledPlatformOptions'
import { useTranslationLanguageOptions } from '@/hooks/useTranslationLanguageOptions'
import { downloadBlob } from '@/utils/download'
import { formatTime } from '@/utils/format'
import { shouldIgnoreTableRowDoubleClick } from '@/utils/tableInteractions'
import { buildDeadlinePlatformOptions, OTHER_DEADLINE_PLATFORM_OPTION } from './deadlinePlatformOptions'
import './SystemSettings.less'

type ActiveTab = 'platforms' | 'print' | 'deadline' | 'tasks' | 'email' | 'models' | 'wecom' | 'translation' | 'runs'
type ScheduleType = 'interval' | 'daily' | 'weekly' | 'monthly' | 'custom'
type DeadlineBaseDateField = ShippingDeadlineSettingPayload['base_date_field']

interface SystemSettingsProps {
  logsOnly?: boolean
}

interface PrintFormValues extends PrintSettingPayload {}

interface TaskFormValues {
  name?: string
  task_type?: string
  schedule_type?: ScheduleType
  schedule_time?: string
  weekday?: string
  month_day?: string
  cron_expr?: string
  enabled?: boolean
  remark?: string
  retry_count?: number
  retry_interval_minutes?: number
  timeout_minutes?: number
  poll_interval_minutes?: number
  poll_interval_seconds?: number
  failure_email_enabled?: boolean
  failure_email_recipients?: string
}

interface EmailFormValues {
  provider?: string
  enabled?: boolean
  smtp_host?: string
  smtp_port?: number
  use_ssl?: boolean
  sender_email?: string
  sender_name?: string
  notification_recipients?: EmailNotificationRecipientsDto
  auth_code?: string
  test_recipient?: string
}

type ModelFormValues = ModelSettingPayload
type ModelEndpointFormValues = ModelEndpointPayload
type WecomFormValues = WeComRobotSettingPayload
interface TranslationFormValues extends TranslationProviderSettingPayload {
  test_text?: string
  test_target_language?: string
}

interface DeadlineDraftRow extends ShippingDeadlineSettingPayload {
  id: number | string
  platform_name?: string
  updated_at?: string | null
  enabled: boolean
  sort_order: number
  isNew?: boolean
}

const printDocumentTypes = [{ value: 'label', label: '面单打印' }]
const emptyModelFormValues: ModelFormValues = {
  name: '',
  model: '',
  endpoint_id: undefined,
  is_default: false,
  supports_vision: false,
  enabled: true
}
const emptyModelEndpointFormValues: ModelEndpointFormValues = {
  name: '',
  base_url: '',
  api_key: '',
  enabled: true,
  remark: ''
}
const emptyWecomFormValues: WecomFormValues = {
  webhook_url: '',
  timeout_seconds: 30,
  max_retries: 2,
  rate_limit_per_minute: 20,
  default_mentioned_user_ids: [],
  default_mentioned_list: [],
  default_mentioned_mobile_list: [],
  default_prompt: '',
  purchase_order_notify_enabled: false
}
const emptyTranslationFormValues: TranslationFormValues = {
  provider: 'baidu',
  enabled: false,
  app_id: '',
  secret_key: '',
  endpoint: '',
  source_language: 'auto',
  timeout_seconds: 30,
  max_retries: 2,
  batch_size: 80,
  batch_chars: 5000,
  provider_options: {},
  test_text: '测试翻译',
  test_target_language: 'en'
}
const printOrientationOptions = [
  { value: 'auto', label: '自动' },
  { value: 'portrait', label: '纵向' },
  { value: 'landscape', label: '横向' }
] as const
function printPlatformOptions(platformOptions: { value: string; label: string }[]) {
  const map = new Map(platformOptions.map((item) => [item.value, item]))
  for (const item of PRINT_ONLY_PLATFORM_OPTIONS) {
    map.set(item.code, { value: item.code, label: item.label })
  }
  return [...map.values()]
}

function printerSecondaryText(printer: PrinterDto) {
  return printer.device_uri || printer.port_name || printer.driver_name || printer.status || ''
}

function renderPrinterOption(printer: PrinterDto) {
  const secondary = printerSecondaryText(printer)
  return (
    <Space direction="vertical" size={0}>
      <Space size={6} wrap>
        <span>{printer.display_name || printer.name}</span>
        {printer.is_default ? <Tag color="processing">默认</Tag> : null}
        {printer.online === false ? <Tag color="warning">离线</Tag> : null}
      </Space>
      {secondary ? <span className="muted">{secondary}</span> : null}
    </Space>
  )
}
const deadlineBaseDateOptions: { value: DeadlineBaseDateField; label: string }[] = [
  { value: 'payment_at', label: '付款时间' },
  { value: 'platform_created_at', label: '创建时间' },
  { value: 'shipping_deadline_at', label: '最后发货期限' }
]
const taskTypeOptions = [{ value: 'auto_order_pipeline', label: '轮巡打印并转配货' }]
const scheduleTypeOptions = [
  { value: 'interval', label: '间隔时间' },
  { value: 'daily', label: '每天' },
  { value: 'weekly', label: '每周' },
  { value: 'monthly', label: '每月' },
  { value: 'custom', label: 'Cron' }
]
const weekdayOptions = [
  { value: 'mon', label: '周一' },
  { value: 'tue', label: '周二' },
  { value: 'wed', label: '周三' },
  { value: 'thu', label: '周四' },
  { value: 'fri', label: '周五' },
  { value: 'sat', label: '周六' },
  { value: 'sun', label: '周日' }
]
const numericWeekdayToName: Record<string, string> = {
  '1': 'mon',
  '2': 'tue',
  '3': 'wed',
  '4': 'thu',
  '5': 'fri',
  '6': 'sat',
  '0': 'sun',
  '7': 'sun'
}
const weekdayNameToCron: Record<string, string> = {
  mon: '1',
  tue: '2',
  wed: '3',
  thu: '4',
  fri: '5',
  sat: '6',
  sun: '0'
}
const monthDayOptions = Array.from({ length: 31 }, (_, index) => ({
  value: String(index + 1),
  label: `${index + 1}日`
})).concat([{ value: 'last', label: '最后一天' }])

function exportTimestamp(date = new Date()) {
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}_${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`
}

function suggestedRunPdfFilename() {
  return `label_print_${exportTimestamp()}.zip`
}

function toDeadlineDraft(row: ShippingDeadlineSettingDto): DeadlineDraftRow {
  return {
    id: row.id,
    platform: row.platform,
    platform_name: row.platform_name,
    base_date_field: row.base_date_field,
    offset_days: Number(row.offset_days) || 0,
    sort_order: Number(row.sort_order) || 0,
    enabled: row.enabled !== false,
    updated_at: row.updated_at
  }
}

function deadlineRowPlatformLabel(row: DeadlineDraftRow, options: { value: string; label: string }[]) {
  if (row.platform === OTHER_DEADLINE_PLATFORM_OPTION.value) return OTHER_DEADLINE_PLATFORM_OPTION.label
  return options.find((item) => item.value === row.platform)?.label || row.platform_name || row.platform
}

function taskStatusColor(status?: string | null) {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'error'
  if (status === 'running' || status === 'waiting_retry' || status === 'retrying') return 'processing'
  if (status === 'partial_success') return 'warning'
  return 'default'
}

function taskStatusLabel(status?: string | null) {
  if (status === 'success') return '成功'
  if (status === 'failed') return '失败'
  if (status === 'running') return '运行中'
  if (status === 'waiting_retry') return '等待重试'
  if (status === 'retrying') return '重试中'
  if (status === 'partial_success') return '部分成功'
  return status || '-'
}

function retryLabel(row?: ScheduledTaskRunDto | null) {
  if (!row) return '-'
  const attempt = row.attempt_no ?? 0
  if (attempt <= 0) return '-'
  const max = row.max_retry_count ?? 0
  return max > 0 ? `${attempt}/${max}` : `${attempt}`
}

function emailRunStatus(row?: ScheduledTaskRunDto | null) {
  if (!row) return '-'
  if (row.email_sent) return '已发送'
  if (row.email_error) return `失败：${row.email_error}`
  return '-'
}

function printSubmitStatus(row: ScheduledTaskRunOrderDto) {
  if (row.print_submitted) return { color: 'success', label: '已提交' }
  if (row.print_message) return { color: row.needs_reprint ? 'error' : 'warning', label: row.print_message }
  return { color: 'default', label: '-' }
}

function pdfStatus(row: ScheduledTaskRunOrderDto) {
  if (row.pdf_generated) return { color: 'success', label: '已生成' }
  if (row.has_label_file) return { color: 'processing', label: '已有面单' }
  if (row.print_message?.includes('无需')) return { color: 'default', label: '无需面单' }
  return { color: 'default', label: '未生成' }
}

function platformPrintStatus(row: ScheduledTaskRunPlatformDto) {
  if (row.needs_reprint) return { color: 'error', label: `失败 ${row.failed_count}` }
  if (row.print_submitted) return { color: 'success', label: '已提交' }
  if (row.pdf_count > 0) return { color: 'processing', label: '已生成PDF' }
  return { color: 'default', label: '-' }
}

function compactTextList(values?: string[], empty = '-') {
  const items = (values || []).filter(Boolean)
  if (!items.length) return empty
  const visible = items.slice(0, 3)
  const suffix = items.length > visible.length ? ` 等 ${items.length} 项` : ''
  return `${visible.join('、')}${suffix}`
}

function platformRunOrders(
  orders: ScheduledTaskRunOrderDto[],
  platform: string,
  selectedRun?: ScheduledTaskRunDto | null
) {
  const filtered = orders.filter((item) => item.platform === platform)
  if (isSuccessfulRun(selectedRun)) return filtered.filter((item) => item.pdf_generated)
  return filtered.filter((item) => item.needs_reprint)
}

function isSuccessfulRun(row?: ScheduledTaskRunDto | null) {
  const summary = row?.summary || ''
  return row?.status === 'success' || row?.status === 'partial_success' || summary.includes('任务完成') || summary.includes('成功')
}

function parseCronSchedule(cronExpr?: string | null): {
  type: ScheduleType
  time: string
  weekday?: string
  day?: string
} | null {
  const parts = String(cronExpr || '').trim().split(/\s+/)
  if (parts.length !== 5) return null
  const [minute, hour, day, month, weekday] = parts
  const minuteNumber = Number(minute)
  const hourNumber = Number(hour)
  if (!Number.isFinite(minuteNumber) || !Number.isFinite(hourNumber) || month !== '*') return null
  const time = `${String(hourNumber).padStart(2, '0')}:${String(minuteNumber).padStart(2, '0')}`
  if (day === '*' && weekday === '*') return { type: 'daily', time }
  if (day === '*' && weekday !== '*') return { type: 'weekly', time, weekday: numericWeekdayToName[weekday] || weekday }
  if (weekday === '*') return { type: 'monthly', time, day: day === 'L' ? 'last' : day }
  return null
}

function buildCronFromValues(values: TaskFormValues) {
  if (values.schedule_type === 'interval') return values.cron_expr?.trim() || '0 9 * * *'
  if (values.schedule_type === 'custom') return values.cron_expr?.trim() || '0 9 * * *'
  const [hour = '09', minute = '00'] = String(values.schedule_time || '09:00').split(':')
  const hourNumber = Math.min(Math.max(Number(hour) || 0, 0), 23)
  const minuteNumber = Math.min(Math.max(Number(minute) || 0, 0), 59)
  if (values.schedule_type === 'weekly') {
    return `${minuteNumber} ${hourNumber} * * ${weekdayNameToCron[values.weekday || 'mon'] || '1'}`
  }
  if (values.schedule_type === 'monthly') {
    const day = values.month_day === 'last' ? 'L' : values.month_day || '1'
    return `${minuteNumber} ${hourNumber} ${day} * *`
  }
  return `${minuteNumber} ${hourNumber} * * *`
}

function intervalMinutesFromSettings(settings?: ScheduledTaskSettings | null) {
  const direct = Number(settings?.interval_minutes)
  if (Number.isFinite(direct) && direct > 0) return Math.round(direct)
  const seconds = Number(settings?.poll_interval_seconds)
  if (Number.isFinite(seconds) && seconds > 0) return Math.max(1, Math.round(seconds / 60))
  return 3
}

function isIntervalSchedule(settings?: ScheduledTaskSettings | null) {
  if (settings?.schedule_mode) return settings.schedule_mode === 'interval'
  return Boolean(settings?.interval_minutes || settings?.poll_interval_seconds)
}

function formatTaskSchedule(row: ScheduledTaskDto) {
  if (isIntervalSchedule(row.settings)) {
    return `间隔 ${intervalMinutesFromSettings(row.settings)} 分钟`
  }
  const cronExpr = row.cron_expr
  const schedule = parseCronSchedule(cronExpr)
  if (!schedule) return cronExpr ? `自定义计划（${cronExpr}）` : '-'
  if (schedule.type === 'weekly') {
    const weekday = weekdayOptions.find((item) => item.value === schedule.weekday)?.label || '周一'
    return `每周${weekday.replace('周', '')} ${schedule.time}`
  }
  if (schedule.type === 'monthly') {
    const dayLabel = schedule.day === 'last' ? '最后一天' : `${Number(schedule.day)}日`
    return `每月${dayLabel} ${schedule.time}`
  }
  return `每天 ${schedule.time}`
}

export function SystemSettings({ logsOnly = false }: SystemSettingsProps) {
  const { message, modal } = App.useApp()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [printForm] = Form.useForm<PrintFormValues>()
  const [taskForm] = Form.useForm<TaskFormValues>()
  const [emailForm] = Form.useForm<EmailFormValues>()
  const [modelForm] = Form.useForm<ModelFormValues>()
  const [modelEndpointForm] = Form.useForm<ModelEndpointFormValues>()
  const [wecomForm] = Form.useForm<WecomFormValues>()
  const [translationForm] = Form.useForm<TranslationFormValues>()
  const { options: translationTargetLanguageOptions, loading: loadingTranslationLanguages } = useTranslationLanguageOptions()
  const [activeTab, setActiveTab] = useState<ActiveTab>(logsOnly ? 'runs' : 'print')
  const [loadingPlatformSettings, setLoadingPlatformSettings] = useState(false)
  const [loadingPrint, setLoadingPrint] = useState(false)
  const [loadingDeadline, setLoadingDeadline] = useState(false)
  const [loadingTasks, setLoadingTasks] = useState(false)
  const [loadingRuns, setLoadingRuns] = useState(false)
  const [loadingEmail, setLoadingEmail] = useState(false)
  const [loadingModels, setLoadingModels] = useState(false)
  const [loadingWecom, setLoadingWecom] = useState(false)
  const [loadingWecomUsers, setLoadingWecomUsers] = useState(false)
  const [loadingTranslation, setLoadingTranslation] = useState(false)
  const [loadingFailedRunOrders, setLoadingFailedRunOrders] = useState(false)
  const [exportingRunId, setExportingRunId] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [savingDeadline, setSavingDeadline] = useState(false)
  const [savingEmail, setSavingEmail] = useState(false)
  const [savingModel, setSavingModel] = useState(false)
  const [savingWecom, setSavingWecom] = useState(false)
  const [savingTranslation, setSavingTranslation] = useState(false)
  const [testingWecom, setTestingWecom] = useState(false)
  const [testingTranslation, setTestingTranslation] = useState(false)
  const [testingModel, setTestingModel] = useState(false)
  const [testingEmail, setTestingEmail] = useState(false)
  const [platformSettings, setPlatformSettings] = useState<PlatformSettingDto[]>([])
  const [updatingPlatform, setUpdatingPlatform] = useState<string | null>(null)
  const [printSettings, setPrintSettings] = useState<PrintSettingDto[]>([])
  const [printers, setPrinters] = useState<PrinterDto[]>([])
  const [loadingPrinters, setLoadingPrinters] = useState(false)
  const [deadlineRows, setDeadlineRows] = useState<DeadlineDraftRow[]>([])
  const [tasks, setTasks] = useState<ScheduledTaskDto[]>([])
  const [modelSettings, setModelSettings] = useState<ModelSettingDto[]>([])
  const [modelEndpoints, setModelEndpoints] = useState<ModelEndpointDto[]>([])
  const [modelTestResult, setModelTestResult] = useState<{ status: 'success' | 'error'; message: string } | null>(null)
  const [taskRuns, setTaskRuns] = useState<ScheduledTaskRunDto[]>([])
  const [runTotal, setRunTotal] = useState(0)
  const [runPage, setRunPage] = useState(1)
  const [runPageSize, setRunPageSize] = useState(50)
  const [emailProviders, setEmailProviders] = useState<EmailProviderDto[]>([])
  const [emailState, setEmailState] = useState<EmailSmtpDto | null>(null)
  const [wecomState, setWecomState] = useState<WeComRobotSettingDto | null>(null)
  const [wecomUsers, setWecomUsers] = useState<WeComMentionUserOptionDto[]>([])
  const [translationProviderOptions, setTranslationProviderOptions] = useState<TranslationProviderOptionDto[]>([])
  const [translationState, setTranslationState] = useState<TranslationProviderSettingDto | null>(null)
  const [translationTestResult, setTranslationTestResult] = useState<{ status: 'success' | 'error'; message: string } | null>(null)
  const [draggingDeadlineId, setDraggingDeadlineId] = useState<DeadlineDraftRow['id'] | null>(null)
  const [printOpen, setPrintOpen] = useState(false)
  const [printMode, setPrintMode] = useState<'create' | 'edit'>('create')
  const [editingPrintId, setEditingPrintId] = useState<number | null>(null)
  const [taskOpen, setTaskOpen] = useState(false)
  const [taskMode, setTaskMode] = useState<'create' | 'edit'>('create')
  const [editingTaskId, setEditingTaskId] = useState<number | null>(null)
  const [modelOpen, setModelOpen] = useState(false)
  const [modelMode, setModelMode] = useState<'create' | 'edit'>('create')
  const [editingModelId, setEditingModelId] = useState<number | null>(null)
  const [modelEndpointSettingsOpen, setModelEndpointSettingsOpen] = useState(false)
  const [modelEndpointOpen, setModelEndpointOpen] = useState(false)
  const [modelEndpointMode, setModelEndpointMode] = useState<'create' | 'edit'>('create')
  const [editingModelEndpointId, setEditingModelEndpointId] = useState<number | null>(null)
  const [runDetailOpen, setRunDetailOpen] = useState(false)
  const [failedReprintOpen, setFailedReprintOpen] = useState(false)
  const [selectedRun, setSelectedRun] = useState<ScheduledTaskRunDto | null>(null)
  const [selectedRunSteps, setSelectedRunSteps] = useState<ScheduledTaskRunStepDto[]>([])
  const [selectedRunOrders, setSelectedRunOrders] = useState<ScheduledTaskRunOrderDto[]>([])
  const [failedRunOrders, setFailedRunOrders] = useState<ScheduledTaskRunOrderDto[]>([])
  const [failedRunPlatforms, setFailedRunPlatforms] = useState<ScheduledTaskRunPlatformDto[]>([])
  const [expandedFailedPlatforms, setExpandedFailedPlatforms] = useState<string[]>([])
  const [reprintingPlatform, setReprintingPlatform] = useState<string | null>(null)
  const scheduleType = Form.useWatch('schedule_type', taskForm)
  const emailProviderCode = Form.useWatch('provider', emailForm)
  const selectedEmailProvider = emailProviders.find((item) => item.code === emailProviderCode)
  const logTaskId = logsOnly ? Number(searchParams.get('task_id')) || undefined : undefined
  const previousLogTaskIdRef = useRef<number | undefined>(logTaskId)

  const emailProviderOptions = useMemo(
    () => emailProviders.map((item) => ({ value: item.code, label: item.name })),
    [emailProviders]
  )
  const translationProviderSelectOptions = useMemo(
    () =>
      (translationProviderOptions.length ? translationProviderOptions : [{ code: 'baidu', name: '百度翻译' }])
        .map((item) => ({ value: item.code, label: item.name })),
    [translationProviderOptions]
  )
  const modelEndpointOptions = useMemo(
    () =>
      modelEndpoints.map((item) => ({
        value: item.id,
        label: `${item.name}${item.enabled ? '' : '（禁用）'}`
      })),
    [modelEndpoints]
  )
  const wecomUserOptions = useMemo(
    () =>
      wecomUsers
        .map((item) => ({
          value: item.id,
          label: item.wecom_mobile
            ? `${item.display_name || item.username}（${item.wecom_mobile}）`
            : `${item.display_name || item.username}（未配置企微手机号）`,
          disabled: !item.wecom_mobile,
          searchText: [item.display_name, item.username, item.wecom_mobile].filter(Boolean).join(' ')
        })),
    [wecomUsers]
  )
  const deadlinePlatformOptions = useMemo(() => {
    return buildDeadlinePlatformOptions(platformSettings)
  }, [platformSettings])
  const enabledPlatformOptions = useMemo(() => platformSettingsToOptions(platformSettings), [platformSettings])
  const printPlatformSelectOptions = useMemo(() => printPlatformOptions(enabledPlatformOptions), [enabledPlatformOptions])
  const activePrintPlatformSelectOptions = useMemo(() => {
    const map = new Map(printPlatformSelectOptions.map((item) => [item.value, item]))
    if (printMode === 'edit' && editingPrintId != null) {
      const current = printSettings.find((item) => item.id === editingPrintId)
      const platform = current?.platform || ''
      if (platform && !map.has(platform)) {
        map.set(platform, { value: platform, label: formatPlatformLabel(platform) })
      }
    }
    return [...map.values()]
  }, [editingPrintId, printMode, printPlatformSelectOptions, printSettings])
  const printerOptions = useMemo(
    () => {
      const options = printers.map((printer) => ({
        value: printer.name,
        label: printer.display_name || printer.name,
        title: printer.name,
        searchText: [
          printer.name,
          printer.display_name,
          printer.device_uri,
          printer.driver_name,
          printer.port_name,
          printer.status
        ].filter(Boolean).join(' ')
      }))
      const seen = new Set(options.map((item) => item.value))
      for (const setting of printSettings) {
        const name = setting.printer_name || ''
        if (!name || seen.has(name)) continue
        options.push({
          value: name,
          label: name,
          title: name,
          searchText: name
        })
      }
      return options
    },
    [printers, printSettings]
  )

  async function loadPlatformSettings() {
    setLoadingPlatformSettings(true)
    try {
      setPlatformSettings((await listPlatformSettings()) || [])
    } finally {
      setLoadingPlatformSettings(false)
    }
  }

  async function loadPrint() {
    setLoadingPrint(true)
    try {
      setPrintSettings((await listPrintSettings()) || [])
    } finally {
      setLoadingPrint(false)
    }
  }

  async function loadPrinters() {
    setLoadingPrinters(true)
    try {
      const data = (await listPrinters()) || []
      setPrinters(data)
      return data
    } finally {
      setLoadingPrinters(false)
    }
  }

  async function loadDeadlineSettings() {
    setLoadingDeadline(true)
    try {
      setDeadlineRows(((await listShippingDeadlineSettings()) || []).map(toDeadlineDraft))
    } finally {
      setLoadingDeadline(false)
    }
  }

  async function loadTasksList() {
    setLoadingTasks(true)
    try {
      setTasks((await listScheduledTasks()) || [])
    } finally {
      setLoadingTasks(false)
    }
  }

  async function loadRuns(taskId?: number, page = runPage, pageSize = runPageSize) {
    setLoadingRuns(true)
    try {
      const data = await listScheduledTaskRuns({ task_id: taskId, page, page_size: pageSize })
      setTaskRuns(data.items || [])
      setRunTotal(data.total || 0)
    } finally {
      setLoadingRuns(false)
    }
  }

  async function loadEmailProviders() {
    const data = (await listEmailProviders()) || []
    setEmailProviders(data)
  }

  async function loadEmail() {
    setLoadingEmail(true)
    try {
      const data = await getEmailSmtp()
      setEmailState(data)
      emailForm.setFieldsValue({
        provider: data.provider,
        enabled: data.enabled,
        smtp_host: data.smtp_host,
        smtp_port: data.smtp_port,
        use_ssl: data.use_ssl,
        sender_email: data.sender_email,
        sender_name: data.sender_name || '',
        notification_recipients: data.notification_recipients,
        auth_code: '',
        test_recipient: data.sender_email || ''
      })
    } finally {
      setLoadingEmail(false)
    }
  }

  async function loadModels() {
    setLoadingModels(true)
    try {
      const [settings, endpoints] = await Promise.all([listModelSettings(), listModelEndpoints()])
      setModelSettings(settings || [])
      setModelEndpoints(endpoints || [])
    } finally {
      setLoadingModels(false)
    }
  }

  async function loadWecomUsers() {
    setLoadingWecomUsers(true)
    try {
      const data = await listWecomMentionUsers()
      setWecomUsers(data || [])
    } finally {
      setLoadingWecomUsers(false)
    }
  }

  async function loadWecom() {
    setLoadingWecom(true)
    try {
      const data = await getWecomRobotSetting()
      setWecomState(data)
      wecomForm.setFieldsValue({
        webhook_url: '',
        timeout_seconds: data.timeout_seconds,
        max_retries: data.max_retries,
        rate_limit_per_minute: data.rate_limit_per_minute,
        default_mentioned_user_ids: data.default_mentioned_user_ids || [],
        default_mentioned_list: data.default_mentioned_list || [],
        default_mentioned_mobile_list: data.default_mentioned_mobile_list || [],
        default_prompt: data.default_prompt || '',
        purchase_order_notify_enabled: Boolean(data.purchase_order_notify_enabled)
      })
    } finally {
      setLoadingWecom(false)
    }
  }

  async function loadTranslationProviderOptions() {
    const data = await listTranslationProviderOptions()
    setTranslationProviderOptions(data || [])
  }

  async function loadTranslation(provider = translationForm.getFieldValue('provider') || 'baidu') {
    setLoadingTranslation(true)
    try {
      const data = await getTranslationProviderSetting(provider)
      setTranslationState(data)
      translationForm.setFieldsValue({
        provider: data.provider || 'baidu',
        enabled: Boolean(data.enabled),
        app_id: data.app_id || '',
        secret_key: '',
        endpoint: data.endpoint || '',
        source_language: data.source_language || 'auto',
        timeout_seconds: data.timeout_seconds,
        max_retries: data.max_retries,
        batch_size: data.batch_size,
        batch_chars: data.batch_chars,
        provider_options: data.provider_options || {},
        test_text: translationForm.getFieldValue('test_text') || '测试翻译',
        test_target_language: translationForm.getFieldValue('test_target_language') || 'en'
      })
      setTranslationTestResult(
        data.last_test_status
          ? {
              status: data.last_test_status === 'success' ? 'success' : 'error',
              message: data.last_test_message || ''
            }
          : null
      )
    } finally {
      setLoadingTranslation(false)
    }
  }

  useEffect(() => {
    if (logsOnly) return
    void Promise.all([
      loadPlatformSettings(),
      loadEmailProviders(),
      loadPrint(),
      loadPrinters(),
      loadDeadlineSettings(),
      loadTasksList(),
      loadRuns(undefined, 1, runPageSize),
      loadEmail(),
      loadModels(),
      loadWecom(),
      loadWecomUsers(),
      loadTranslationProviderOptions(),
      loadTranslation()
    ])
  }, [logsOnly])

  useEffect(() => {
    if (!logsOnly) return
    if (previousLogTaskIdRef.current !== logTaskId) {
      previousLogTaskIdRef.current = logTaskId
      if (runPage !== 1) {
        setRunPage(1)
        return
      }
    }
    void loadRuns(logTaskId, runPage, runPageSize)
  }, [logsOnly, logTaskId, runPage, runPageSize])

  function applyEmailProvider(providerCode?: string) {
    const provider = emailProviders.find((item) => item.code === providerCode)
    if (!provider) return
    emailForm.setFieldsValue({
      smtp_host: provider.smtp_host || '',
      smtp_port: provider.smtp_port || 465,
      use_ssl: provider.use_ssl !== false
    })
  }

  async function ensurePrintersLoaded() {
    if (printers.length) return printers
    return await loadPrinters()
  }

  async function openPrintCreate() {
    const availablePrinters = await ensurePrintersLoaded()
    if (!availablePrinters.length) {
      message.warning('后台服务所在电脑未检测到打印机')
    }
    setPrintMode('create')
    setEditingPrintId(null)
    printForm.resetFields()
    printForm.setFieldsValue({
      platform: printPlatformSelectOptions[0]?.value || 'ozon',
      document_type: 'label',
      printer_name: availablePrinters.find((item) => item.is_default)?.name || availablePrinters[0]?.name || '',
      page_orientation: 'auto',
      enabled: true,
      remark: ''
    })
    setPrintOpen(true)
  }

  async function openPrintEdit(row: PrintSettingDto) {
    const availablePrinters = await ensurePrintersLoaded()
    if (!availablePrinters.length) {
      message.warning('后台服务所在电脑未检测到打印机')
    }
    setPrintMode('edit')
    setEditingPrintId(row.id)
    printForm.setFieldsValue({
      platform: row.platform,
      document_type: row.document_type || 'label',
      printer_name: row.printer_name,
      page_orientation: row.page_orientation || 'auto',
      enabled: row.enabled,
      remark: row.remark || ''
    })
    setPrintOpen(true)
  }

  async function savePrintSetting() {
    const values = await printForm.validateFields()
    setSaving(true)
    try {
      const payload: PrintSettingPayload = {
        platform: values.platform,
        document_type: values.document_type,
        printer_name: values.printer_name,
        page_orientation: values.page_orientation || 'auto',
        enabled: values.enabled,
        remark: values.remark || ''
      }
      if (printMode === 'create') await createPrintSetting(payload)
      else if (editingPrintId != null) await updatePrintSetting(editingPrintId, payload)
      message.success('已保存')
      setPrintOpen(false)
      await loadPrint()
    } finally {
      setSaving(false)
    }
  }

  async function onDeletePrint(row: PrintSettingDto) {
    await deletePrintSetting(row.id)
    message.success('已删除')
    await loadPrint()
  }

  async function togglePrintRow(row: PrintSettingDto) {
    await updatePrintSetting(row.id, {
      platform: row.platform,
      document_type: row.document_type,
      printer_name: row.printer_name,
      page_orientation: row.page_orientation || 'auto',
      enabled: !row.enabled,
      remark: row.remark || ''
    })
    message.success(row.enabled ? '已停用' : '已启用')
    await loadPrint()
  }

  async function togglePlatformRow(row: PlatformSettingDto, enabled: boolean) {
    setUpdatingPlatform(row.platform)
    try {
      const next = await updatePlatformSetting(row.platform, { enabled })
      setPlatformSettings((rows) => rows.map((item) => (item.platform === row.platform ? next : item)))
      message.success(enabled ? '已启用' : '已禁用')
    } finally {
      setUpdatingPlatform(null)
    }
  }

  function updateDeadlineRow(id: DeadlineDraftRow['id'], patch: Partial<DeadlineDraftRow>) {
    setDeadlineRows((rows) => rows.map((row) => (row.id === id ? { ...row, ...patch } : row)))
  }

  function addDeadlineRow() {
    const used = new Set(deadlineRows.map((row) => row.platform))
    const candidate =
      deadlinePlatformOptions.find((item) => !used.has(item.value) && item.value !== OTHER_DEADLINE_PLATFORM_OPTION.value) ||
      deadlinePlatformOptions.find((item) => !used.has(item.value))
    if (!candidate) {
      message.warning('没有可新增的平台')
      return
    }
    setDeadlineRows((rows) => [
      ...rows,
      {
        id: `new-${Date.now()}`,
        platform: candidate.value,
        platform_name: candidate.label,
        base_date_field: 'platform_created_at',
        offset_days: 0,
        sort_order: rows.length,
        enabled: true,
        isNew: true
      }
    ])
  }

  function deleteDeadlineRow(row: DeadlineDraftRow) {
    setDeadlineRows((rows) => rows.filter((item) => item.id !== row.id))
  }

  function moveDeadlineRow(sourceId: DeadlineDraftRow['id'], targetId: DeadlineDraftRow['id']) {
    if (String(sourceId) === String(targetId)) return
    setDeadlineRows((rows) => {
      const sourceIndex = rows.findIndex((item) => String(item.id) === String(sourceId))
      const targetIndex = rows.findIndex((item) => String(item.id) === String(targetId))
      if (sourceIndex < 0 || targetIndex < 0) return rows
      const next = [...rows]
      const [source] = next.splice(sourceIndex, 1)
      next.splice(targetIndex, 0, source)
      return next.map((item, index) => ({ ...item, sort_order: index }))
    })
  }

  function dragDeadlineRow(event: DragEvent<HTMLElement>, row: DeadlineDraftRow) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', String(row.id))
    setDraggingDeadlineId(row.id)
  }

  function dropDeadlineRow(event: DragEvent<HTMLElement>, row: DeadlineDraftRow) {
    event.preventDefault()
    moveDeadlineRow(event.dataTransfer.getData('text/plain'), row.id)
    setDraggingDeadlineId(null)
  }

  async function saveDeadlineSettings() {
    const platforms = new Set<string>()
    const payload: ShippingDeadlineSettingPayload[] = []
    for (const [index, row] of deadlineRows.entries()) {
      if (!row.platform) {
        message.warning('请选择平台')
        return
      }
      if (platforms.has(row.platform)) {
        message.warning(`平台「${deadlineRowPlatformLabel(row, deadlinePlatformOptions)}」规则重复`)
        return
      }
      platforms.add(row.platform)
      payload.push({
        platform: row.platform,
        base_date_field: row.base_date_field,
        offset_days: Number(row.offset_days) || 0,
        sort_order: index,
        enabled: true
      })
    }
    setSavingDeadline(true)
    try {
      const result = await updateShippingDeadlineSettings(payload)
      setDeadlineRows((result.items || []).map(toDeadlineDraft))
      message.success(`已保存，回填 ${result.backfilled || 0} 个订单`)
    } finally {
      setSavingDeadline(false)
    }
  }

  function openTaskCreate() {
    setTaskMode('create')
    setEditingTaskId(null)
    taskForm.resetFields()
    taskForm.setFieldsValue({
      name: '轮巡打印并转配货',
      task_type: 'auto_order_pipeline',
      schedule_type: 'interval',
      schedule_time: '09:00',
      weekday: 'mon',
      month_day: '1',
      cron_expr: '0 9 * * *',
      enabled: true,
      remark: '',
      retry_count: 1,
      retry_interval_minutes: 5,
      timeout_minutes: 10,
      poll_interval_minutes: 3,
      poll_interval_seconds: 180,
      failure_email_enabled: false,
      failure_email_recipients: ''
    })
    setTaskOpen(true)
  }

  function openTaskEdit(row: ScheduledTaskDto) {
    const schedule = parseCronSchedule(row.cron_expr) || parseCronSchedule('0 9 * * *')!
    const isInterval = isIntervalSchedule(row.settings)
    setTaskMode('edit')
    setEditingTaskId(row.id)
    taskForm.setFieldsValue({
      name: row.name,
      task_type: row.task_type,
      schedule_type: isInterval ? 'interval' : schedule.type,
      schedule_time: schedule.time,
      weekday: schedule.weekday || 'mon',
      month_day: schedule.day || '1',
      cron_expr: row.cron_expr,
      enabled: row.enabled,
      remark: row.remark || '',
      retry_count: Number(row.settings?.retry_count) || 0,
      retry_interval_minutes: Number(row.settings?.retry_interval_minutes) || 5,
      timeout_minutes: Number(row.settings?.timeout_minutes) || 10,
      poll_interval_minutes: intervalMinutesFromSettings(row.settings),
      poll_interval_seconds: Number(row.settings?.poll_interval_seconds) || 180,
      failure_email_enabled: row.settings?.failure_email_enabled || false,
      failure_email_recipients: row.settings?.failure_email_recipients || ''
    })
    setTaskOpen(true)
  }

  async function saveTask() {
    const values = await taskForm.validateFields()
    const cronExpr = buildCronFromValues(values)
    const intervalMinutes = Math.max(1, Math.min(1440, Math.round(Number(values.poll_interval_minutes) || 3)))
    const payload: ScheduledTaskPayload = {
      name: values.name?.trim() || '',
      task_type: values.task_type || 'auto_order_pipeline',
      cron_expr: cronExpr,
      enabled: values.enabled !== false,
      remark: values.remark || '',
      settings: {
        schedule_mode: values.schedule_type === 'interval' ? 'interval' : 'cron',
        interval_minutes: intervalMinutes,
        retry_count: Number(values.retry_count) || 0,
        retry_interval_minutes: Number(values.retry_interval_minutes) || 5,
        timeout_minutes: Number(values.timeout_minutes) || 10,
        poll_interval_seconds: intervalMinutes * 60,
        failure_email_enabled: values.failure_email_enabled || false,
        failure_email_recipients: values.failure_email_recipients || ''
      }
    }
    setSaving(true)
    try {
      if (taskMode === 'create') await createScheduledTask(payload)
      else if (editingTaskId != null) await updateScheduledTask(editingTaskId, payload)
      message.success('已保存')
      setTaskOpen(false)
      setRunPage(1)
      await Promise.all([loadTasksList(), loadRuns(undefined, 1, runPageSize)])
    } finally {
      setSaving(false)
    }
  }

  async function toggleTaskRow(row: ScheduledTaskDto) {
    await toggleScheduledTask(row.id)
    message.success(row.enabled ? '已停用' : '已启用')
    await loadTasksList()
  }

  async function runTaskRow(row: ScheduledTaskDto) {
    await runScheduledTask(row.id)
    message.success('已触发任务')
    setRunPage(1)
    await Promise.all([loadTasksList(), loadRuns(undefined, 1, runPageSize)])
    navigate(`/scheduled-task-logs?task_id=${row.id}`)
  }

  function viewTaskRunsRow(row: ScheduledTaskDto) {
    navigate(`/scheduled-task-logs?task_id=${row.id}`)
  }

  function deleteTaskRow(row: ScheduledTaskDto) {
    modal.confirm({
      title: '删除定时任务',
      content: `确认删除任务「${row.name}」？`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        await deleteScheduledTask(row.id)
        message.success('已删除')
        setRunPage(1)
        await Promise.all([loadTasksList(), loadRuns(undefined, 1, runPageSize)])
      }
    })
  }

  async function onSaveEmailSetting(opts?: { silent?: boolean }) {
    const values = await emailForm.validateFields()
    setSavingEmail(true)
    try {
      const data = await updateEmailSmtp({
        provider: values.provider || 'custom',
        enabled: values.enabled !== false,
        smtp_host: values.smtp_host || '',
        smtp_port: Number(values.smtp_port) || 465,
        use_ssl: values.use_ssl !== false,
        sender_email: values.sender_email || '',
        sender_name: values.sender_name || '',
        notification_recipients: {
          wanbang_tracking_failure: values.notification_recipients?.wanbang_tracking_failure || '',
          bsi_address_anomaly: values.notification_recipients?.bsi_address_anomaly || ''
        },
        auth_code: values.auth_code || null
      })
      setEmailState(data)
      emailForm.setFieldValue('auth_code', '')
      if (!opts?.silent) message.success('邮件设置已保存')
      return true
    } finally {
      setSavingEmail(false)
    }
  }

  async function onTestEmailSetting() {
    const recipient = emailForm.getFieldValue('test_recipient')?.trim()
    if (!recipient) {
      message.warning('请输入测试收件人')
      return
    }
    setTestingEmail(true)
    try {
      await onSaveEmailSetting({ silent: true })
      const data = await testEmailSmtp(recipient)
      setEmailState(data)
      message.success('测试邮件已发送')
      await loadEmail()
    } finally {
      setTestingEmail(false)
    }
  }

  function openModelCreate() {
    if (!modelEndpoints.length) {
      message.warning('请先新增接口配置')
      setModelEndpointSettingsOpen(true)
      return
    }
    setModelMode('create')
    setEditingModelId(null)
    setModelTestResult(null)
    modelForm.setFieldsValue({
      ...emptyModelFormValues,
      endpoint_id: modelEndpoints.find((item) => item.enabled)?.id ?? modelEndpoints[0]?.id
    })
    setModelOpen(true)
  }

  function openModelEdit(row: ModelSettingDto) {
    setModelMode('edit')
    setEditingModelId(row.id)
    setModelTestResult(null)
    modelForm.setFieldsValue({
      name: row.name,
      model: row.model,
      endpoint_id: row.endpoint_id ?? undefined,
      is_default: row.is_default,
      supports_vision: row.supports_vision,
      enabled: row.enabled
    })
    setModelOpen(true)
  }

  function closeModelModal() {
    setModelOpen(false)
    setEditingModelId(null)
    setModelTestResult(null)
    modelForm.resetFields()
  }

  function openModelEndpointCreate() {
    setModelEndpointMode('create')
    setEditingModelEndpointId(null)
    modelEndpointForm.setFieldsValue(emptyModelEndpointFormValues)
    setModelEndpointOpen(true)
  }

  function openModelEndpointEdit(row: ModelEndpointDto) {
    setModelEndpointMode('edit')
    setEditingModelEndpointId(row.id)
    modelEndpointForm.setFieldsValue({
      name: row.name,
      base_url: row.base_url,
      api_key: '',
      enabled: row.enabled,
      remark: row.remark || ''
    })
    setModelEndpointOpen(true)
  }

  function closeModelEndpointModal() {
    setModelEndpointOpen(false)
    setEditingModelEndpointId(null)
    modelEndpointForm.resetFields()
  }

  async function submitModel() {
    const values = await modelForm.validateFields()
    setSavingModel(true)
    try {
      if (modelMode === 'edit' && editingModelId) {
        await updateModelSetting(editingModelId, values)
        message.success('模型设置已更新')
      } else {
        await createModelSetting(values)
        message.success('模型设置已创建')
      }
      closeModelModal()
      await loadModels()
    } finally {
      setSavingModel(false)
    }
  }

  async function submitModelEndpoint() {
    const values = await modelEndpointForm.validateFields()
    const payload: ModelEndpointPayload = {
      ...values,
      api_key: modelEndpointMode === 'edit' && !values.api_key ? null : values.api_key
    }
    setSavingModel(true)
    try {
      if (modelEndpointMode === 'edit' && editingModelEndpointId) {
        await updateModelEndpoint(editingModelEndpointId, payload)
        message.success('接口配置已更新')
      } else {
        await createModelEndpoint(payload)
        message.success('接口配置已创建')
      }
      closeModelEndpointModal()
      await loadModels()
    } finally {
      setSavingModel(false)
    }
  }

  async function deleteModelRow(row: ModelSettingDto) {
    await deleteModelSetting(row.id)
    message.success('模型设置已删除')
    await loadModels()
  }

  async function onSaveWecomSetting() {
    const values = await wecomForm.validateFields()
    setSavingWecom(true)
    try {
      const data = await updateWecomRobotSetting({
        webhook_url: String(values.webhook_url || '').trim(),
        timeout_seconds: Number(values.timeout_seconds),
        max_retries: Number(values.max_retries),
        rate_limit_per_minute: Number(values.rate_limit_per_minute),
        default_mentioned_user_ids: values.default_mentioned_user_ids || [],
        default_mentioned_list: [],
        default_mentioned_mobile_list: [],
        default_prompt: values.default_prompt?.trim() || '',
        purchase_order_notify_enabled: Boolean(values.purchase_order_notify_enabled)
      })
      setWecomState(data)
      wecomForm.setFieldsValue({
        webhook_url: '',
        timeout_seconds: data.timeout_seconds,
        max_retries: data.max_retries,
        rate_limit_per_minute: data.rate_limit_per_minute,
        default_mentioned_user_ids: data.default_mentioned_user_ids || [],
        default_mentioned_list: data.default_mentioned_list || [],
        default_mentioned_mobile_list: data.default_mentioned_mobile_list || [],
        default_prompt: data.default_prompt || '',
        purchase_order_notify_enabled: Boolean(data.purchase_order_notify_enabled)
      })
      message.success('企业微信设置已保存')
      return data
    } finally {
      setSavingWecom(false)
    }
  }

  async function onTestWecomSetting() {
    setTestingWecom(true)
    try {
      await onSaveWecomSetting()
      const data = await testWecomRobotSetting(wecomForm.getFieldValue('default_prompt')?.trim() ?? '')
      if (data.status === 'skipped') {
        message.info(data.message || '默认提示语为空，未发送企业微信测试消息')
      } else {
        message.success(data.message || '企业微信测试消息已发送')
      }
      await loadWecom()
    } finally {
      setTestingWecom(false)
    }
  }

  async function onTranslationProviderChange(provider: string) {
    translationForm.setFieldValue('provider', provider)
    await loadTranslation(provider)
  }

  async function onSaveTranslationSetting() {
    const values = await translationForm.validateFields()
    setSavingTranslation(true)
    try {
      const data = await updateTranslationProviderSetting({
        provider: values.provider || 'baidu',
        enabled: Boolean(values.enabled),
        app_id: String(values.app_id || '').trim(),
        secret_key: String(values.secret_key || '').trim() || null,
        endpoint: String(values.endpoint || '').trim(),
        source_language: String(values.source_language || 'auto').trim() || 'auto',
        timeout_seconds: Number(values.timeout_seconds),
        max_retries: Number(values.max_retries),
        batch_size: Number(values.batch_size),
        batch_chars: Number(values.batch_chars),
        provider_options: values.provider_options || {}
      })
      setTranslationState(data)
      translationForm.setFieldsValue({
        provider: data.provider || 'baidu',
        enabled: Boolean(data.enabled),
        app_id: data.app_id || '',
        secret_key: '',
        endpoint: data.endpoint || '',
        source_language: data.source_language || 'auto',
        timeout_seconds: data.timeout_seconds,
        max_retries: data.max_retries,
        batch_size: data.batch_size,
        batch_chars: data.batch_chars,
        provider_options: data.provider_options || {}
      })
      message.success('翻译设置已保存')
      return data
    } finally {
      setSavingTranslation(false)
    }
  }

  async function onTestTranslationSetting() {
    setTestingTranslation(true)
    try {
      const saved = await onSaveTranslationSetting()
      const values = translationForm.getFieldsValue()
      const data = await testTranslationProviderSetting({
        provider: saved.provider || values.provider || 'baidu',
        text: String(values.test_text || '测试翻译').trim(),
        target_language: String(values.test_target_language || 'en').trim()
      })
      const resultText = data.translated_text || data.message || '翻译测试成功'
      setTranslationTestResult({ status: 'success', message: resultText })
      message.success(data.message || '翻译测试成功')
      await loadTranslation(saved.provider)
    } catch (error) {
      const detail = error instanceof Error ? error.message : '翻译测试失败'
      setTranslationTestResult({ status: 'error', message: detail })
      message.error(detail)
    } finally {
      setTestingTranslation(false)
    }
  }

  async function deleteModelEndpointRow(row: ModelEndpointDto) {
    await deleteModelEndpoint(row.id)
    message.success('接口配置已删除')
    await loadModels()
  }

  async function setDefaultModel(row: ModelSettingDto) {
    await updateModelSetting(row.id, {
      name: row.name,
      model: row.model,
      endpoint_id: row.endpoint_id,
      is_default: true,
      supports_vision: row.supports_vision,
      enabled: true
    })
    message.success('默认模型已更新')
    await loadModels()
  }

  async function toggleModelEnabled(row: ModelSettingDto) {
    const nextEnabled = !row.enabled
    await updateModelSetting(row.id, {
      name: row.name,
      model: row.model,
      endpoint_id: row.endpoint_id,
      is_default: nextEnabled ? row.is_default : false,
      supports_vision: row.supports_vision,
      enabled: nextEnabled
    })
    message.success(nextEnabled ? '模型已启用' : '模型已禁用')
    await loadModels()
  }

  async function toggleModelEndpointEnabled(row: ModelEndpointDto) {
    const nextEnabled = !row.enabled
    await updateModelEndpoint(row.id, {
      name: row.name,
      base_url: row.base_url,
      enabled: nextEnabled,
      remark: row.remark || ''
    })
    message.success(nextEnabled ? '接口配置已启用' : '接口配置已禁用')
    await loadModels()
  }

  async function testCurrentModel() {
    const values = await modelForm.validateFields()
    setTestingModel(true)
    setModelTestResult(null)
    try {
      const saved =
        modelMode === 'edit' && editingModelId
          ? await updateModelSetting(editingModelId, values)
          : await createModelSetting(values)
      if (modelMode === 'create') {
        setModelMode('edit')
        setEditingModelId(saved.id)
      }
      const result = await testModelSettingConnection(saved.id)
      setModelTestResult({ status: 'success', message: `${result.message || '连接正常'}，耗时 ${result.duration_ms}ms` })
      message.success('模型连接正常')
      await loadModels()
    } catch (error) {
      const fallback = (error as Error)?.message || '连接失败，请检查接口配置、模型标识和 api key'
      setModelTestResult({ status: 'error', message: fallback })
    } finally {
      setTestingModel(false)
    }
  }

  async function viewRunDetail(row: ScheduledTaskRunDto) {
    setSelectedRun(row)
    setRunDetailOpen(true)
    const [steps, orders] = await Promise.all([getRunSteps(row.id), getRunOrders(row.id)])
    setSelectedRunSteps(steps || [])
    setSelectedRunOrders(orders || [])
  }

  async function openFailedReprints(row: ScheduledTaskRunDto) {
    setSelectedRun(row)
    setFailedReprintOpen(true)
    setLoadingFailedRunOrders(true)
    setExpandedFailedPlatforms([])
    try {
      const successRun = isSuccessfulRun(row)
      const [platforms, orders] = await Promise.all([
        getRunPlatforms(row.id, successRun ? undefined : { needs_reprint: true }),
        successRun ? getRunOrders(row.id) : getRunOrders(row.id, { needs_reprint: true })
      ])
      const visiblePlatforms = successRun ? platforms.filter((item) => item.pdf_count > 0) : platforms
      setFailedRunOrders((orders || []).filter((item) => (isSuccessfulRun(row) ? item.pdf_generated : true)))
      setFailedRunPlatforms(visiblePlatforms || [])
    } finally {
      setLoadingFailedRunOrders(false)
    }
  }

  async function onExportRunPdfs(row: ScheduledTaskRunDto) {
    setExportingRunId(row.id)
    try {
      const exported = await exportRunPdfsBlob(row.id)
      downloadBlob(exported.blob, exported.filename || suggestedRunPdfFilename())
      message.success('已导出')
    } catch (error) {
      message.error((error as Error)?.message || '导出PDF失败')
    } finally {
      setExportingRunId(null)
    }
  }

  async function onReprintOrder(row: ScheduledTaskRunOrderDto) {
    await reprintRunOrder(row.id)
    message.success(isSuccessfulRun(selectedRun) ? '已提交重新打印' : '已提交重打')
    if (selectedRun) {
      const [orders, failedOrders] = await Promise.all([
        getRunOrders(selectedRun.id),
        isSuccessfulRun(selectedRun) ? getRunOrders(selectedRun.id) : getRunOrders(selectedRun.id, { needs_reprint: true })
      ])
      setSelectedRunOrders(orders || [])
      setFailedRunOrders((failedOrders || []).filter((item) => (isSuccessfulRun(selectedRun) ? item.pdf_generated : true)))
    }
  }

  async function onReprintPlatform(row: ScheduledTaskRunPlatformDto) {
    if (!selectedRun) return
    setReprintingPlatform(row.platform)
    try {
      await reprintRunPlatform(selectedRun.id, row.platform)
      message.success(`${formatPlatformLabel(row.platform)} ${isSuccessfulRun(selectedRun) ? '已提交重新打印' : '已提交重打'}`)
      const successRun = isSuccessfulRun(selectedRun)
      const [platforms, orders, detailOrders] = await Promise.all([
        getRunPlatforms(selectedRun.id, successRun ? undefined : { needs_reprint: true }),
        successRun ? getRunOrders(selectedRun.id) : getRunOrders(selectedRun.id, { needs_reprint: true }),
        getRunOrders(selectedRun.id)
      ])
      setFailedRunPlatforms((successRun ? platforms.filter((item) => item.pdf_count > 0) : platforms) || [])
      setFailedRunOrders((orders || []).filter((item) => (successRun ? item.pdf_generated : true)))
      setSelectedRunOrders(detailOrders || [])
    } catch (error) {
      message.error((error as Error)?.message || '平台重打失败')
    } finally {
      setReprintingPlatform(null)
    }
  }

  const printColumns: ColumnsType<PrintSettingDto> = [
    { title: '平台', dataIndex: 'platform', width: 140, render: (value) => formatPlatformLabel(value) },
    { title: '单据类型', dataIndex: 'document_type_name', width: 140, render: (value, row) => value || row.document_type },
    { title: '打印机', dataIndex: 'printer_name', width: 220 },
    {
      title: '打印方向',
      dataIndex: 'page_orientation_name',
      width: 110,
      render: (value, row) => value || printOrientationOptions.find((item) => item.value === (row.page_orientation || 'auto'))?.label || '自动'
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      width: 90,
      render: (value) => <Tag color={value ? 'success' : 'default'}>{value ? '启用' : '停用'}</Tag>
    },
    { title: '备注', dataIndex: 'remark', ellipsis: true, render: (value) => value || '-' },
    { title: '更新时间', dataIndex: 'updated_at', width: 170, render: (value) => formatTime(value, true) },
    {
      title: '操作',
      width: 200,
      fixed: 'right',
      render: (_, row) => (
        <Space size={4}>
          <Button size="small" icon={<EditOutlined />} onClick={() => void openPrintEdit(row)}>
            编辑
          </Button>
          <Button size="small" type={row.enabled ? 'default' : 'primary'} onClick={() => togglePrintRow(row)}>
            {row.enabled ? '停用' : '启用'}
          </Button>
          <Popconfirm title="确认删除该打印设置？" onConfirm={() => onDeletePrint(row)}>
            <Button danger size="small" icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      )
    }
  ]

  const platformColumns: ColumnsType<PlatformSettingDto> = [
    {
      title: '平台名称',
      dataIndex: 'platform_name',
      render: (value, row) => value || formatPlatformLabel(row.platform)
    },
    {
      title: '是否启用',
      dataIndex: 'enabled',
      width: 140,
      render: (value, row) => (
        <Switch
          checked={value}
          loading={updatingPlatform === row.platform}
          checkedChildren="启用"
          unCheckedChildren="禁用"
          aria-label={`${row.platform_name || formatPlatformLabel(row.platform)}是否启用`}
          onChange={(checked) => void togglePlatformRow(row, checked)}
        />
      )
    },
    { title: '更新时间', dataIndex: 'updated_at', width: 170, render: (value) => formatTime(value, true) }
  ]

  const deadlineColumns: ColumnsType<DeadlineDraftRow> = [
    {
      title: '',
      dataIndex: 'sort_order',
      width: 48,
      render: (_, row) => (
        <span className="deadline-drag-handle" title="拖拽调整顺序" draggable onDragStart={(event) => dragDeadlineRow(event, row)} onDragEnd={() => setDraggingDeadlineId(null)}>
          <HolderOutlined />
        </span>
      )
    },
    {
      title: '平台名字',
      dataIndex: 'platform',
      width: 190,
      render: (_, row) => (
        <Select
          value={row.platform}
          options={buildDeadlinePlatformOptions(platformSettings, row.platform, row.platform_name)}
          onChange={(value, option) => {
            const label = Array.isArray(option) ? value : option?.label
            updateDeadlineRow(row.id, { platform: value, platform_name: typeof label === 'string' ? label : value })
          }}
        />
      )
    },
    {
      title: '基准日期',
      dataIndex: 'base_date_field',
      width: 180,
      render: (_, row) => (
        <Select
          value={row.base_date_field}
          options={deadlineBaseDateOptions}
          onChange={(value) => updateDeadlineRow(row.id, { base_date_field: value })}
        />
      )
    },
    {
      title: '偏移天数',
      dataIndex: 'offset_days',
      width: 140,
      render: (_, row) => (
        <InputNumber
          value={row.offset_days}
          min={-365}
          max={365}
          step={1}
          precision={0}
          onChange={(value) => updateDeadlineRow(row.id, { offset_days: Number(value) || 0 })}
        />
      )
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 170,
      render: (_, row) => formatTime(row.updated_at, true)
    },
    {
      title: '操作',
      width: 100,
      fixed: 'right',
      render: (_, row) => (
        <Button danger size="small" icon={<DeleteOutlined />} onClick={() => deleteDeadlineRow(row)}>
          删除
        </Button>
      )
    }
  ]

  const modelEndpointColumns: DataTableColumnsType<ModelEndpointDto> = [
    {
      title: '接口配置',
      dataIndex: 'name',
      minWidth: 160,
      flex: 0.8,
      maxWidth: 260,
      ellipsis: true
    },
    {
      title: 'base url',
      dataIndex: 'base_url',
      minWidth: 260,
      flex: 1.3,
      maxWidth: 460,
      ellipsis: true,
      render: (value) => value || '-'
    },
    {
      title: 'api key',
      dataIndex: 'api_key_masked',
      minWidth: 130,
      maxWidth: 180,
      render: (value) => value || '-'
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      width: 90,
      align: 'center',
      render: (value) => <Tag color={value ? 'success' : 'default'}>{value ? '启用' : '禁用'}</Tag>
    },
    {
      title: '备注',
      dataIndex: 'remark',
      minWidth: 160,
      flex: 0.8,
      maxWidth: 300,
      ellipsis: true,
      render: (value) => value || '-'
    },
    {
      title: '操作',
      width: 232,
      fixed: 'right',
      render: (_, row) => (
        <Space size={4} className="model-settings-actions">
          <Button size="small" icon={row.enabled ? <PauseCircleOutlined /> : <PlayCircleOutlined />} onClick={() => toggleModelEndpointEnabled(row)}>
            {row.enabled ? '禁用' : '启用'}
          </Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openModelEndpointEdit(row)}>
            编辑
          </Button>
          <Popconfirm title="确认删除该接口配置？" description="已被模型使用的接口配置不能删除。" onConfirm={() => deleteModelEndpointRow(row)}>
            <Button size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      )
    }
  ]

  const modelColumns: DataTableColumnsType<ModelSettingDto> = [
    {
      title: '模型名称',
      dataIndex: 'name',
      minWidth: 150,
      flex: 0.7,
      maxWidth: 240,
      ellipsis: true
    },
    {
      title: '模型',
      dataIndex: 'model',
      minWidth: 150,
      flex: 0.7,
      maxWidth: 240,
      ellipsis: true,
      render: (value) => value || '-'
    },
    {
      title: '接口配置',
      dataIndex: 'endpoint_name',
      minWidth: 160,
      flex: 0.8,
      maxWidth: 260,
      ellipsis: true,
      render: (value, row) => (
        <Space size={6}>
          <span>{value || '-'}</span>
          {row.endpoint_enabled === false ? <Tag>禁用</Tag> : null}
        </Space>
      )
    },
    {
      title: 'url地址',
      dataIndex: 'url',
      minWidth: 240,
      flex: 1.2,
      maxWidth: 460,
      ellipsis: true,
      render: (value) => value || '-'
    },
    {
      title: '默认',
      dataIndex: 'is_default',
      width: 92,
      align: 'center',
      render: (value) =>
        value ? (
          <Tag color="processing" icon={<CheckCircleOutlined />}>
            默认
          </Tag>
        ) : (
          <span className="muted">-</span>
        )
    },
    {
      title: '视觉',
      dataIndex: 'supports_vision',
      width: 90,
      align: 'center',
      render: (value) => <Tag color={value ? 'blue' : 'default'}>{value ? '支持' : '-'}</Tag>
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      width: 90,
      align: 'center',
      render: (value) => <Tag color={value ? 'success' : 'default'}>{value ? '启用' : '禁用'}</Tag>
    },
    {
      title: '操作',
      width: 330,
      fixed: 'right',
      render: (_, row) => (
        <Space size={4} className="model-settings-actions">
          <Button size="small" icon={<CheckCircleOutlined />} disabled={row.is_default && row.enabled} onClick={() => setDefaultModel(row)}>
            设默认
          </Button>
          <Button size="small" icon={row.enabled ? <PauseCircleOutlined /> : <PlayCircleOutlined />} onClick={() => toggleModelEnabled(row)}>
            {row.enabled ? '禁用' : '启用'}
          </Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openModelEdit(row)}>
            编辑
          </Button>
          <Popconfirm title="确认删除该模型设置？" onConfirm={() => deleteModelRow(row)}>
            <Button size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      )
    }
  ]

  const taskColumns: ColumnsType<ScheduledTaskDto> = [
    { title: '任务名称', dataIndex: 'name', width: 200 },
    { title: '任务类型', dataIndex: 'task_type', width: 190 },
    { title: '执行计划', width: 180, render: (_, row) => formatTaskSchedule(row) },
    {
      title: '状态',
      dataIndex: 'enabled',
      width: 90,
      render: (value) => <Tag color={value ? 'success' : 'default'}>{value ? '启用' : '停用'}</Tag>
    },
    { title: '上次执行时间', dataIndex: 'last_run_at', width: 170, render: (value) => formatTime(value, true) },
    {
      title: '上次结果',
      dataIndex: 'last_status',
      width: 110,
      render: (value) => <Tag color={taskStatusColor(value)}>{taskStatusLabel(value)}</Tag>
    },
    { title: '备注', dataIndex: 'remark', ellipsis: true, render: (value) => value || '-' },
    {
      title: '操作',
      width: 330,
      fixed: 'right',
      render: (_, row) => (
        <Space size={4}>
          <Button size="small" onClick={() => openTaskEdit(row)}>
            编辑
          </Button>
          <Button size="small" type={row.enabled ? 'default' : 'primary'} onClick={() => toggleTaskRow(row)}>
            {row.enabled ? '停用' : '启用'}
          </Button>
          <Button size="small" onClick={() => runTaskRow(row)}>
            手动触发
          </Button>
          <Button size="small" onClick={() => viewTaskRunsRow(row)}>
            日志
          </Button>
          <Button size="small" danger onClick={() => deleteTaskRow(row)}>
            删除
          </Button>
        </Space>
      )
    }
  ]

  const runColumns: ColumnsType<ScheduledTaskRunDto> = [
    { title: 'ID', dataIndex: 'id', width: 80 },
    { title: '任务类型', dataIndex: 'task_type', width: 190 },
    { title: '触发方式', dataIndex: 'trigger_mode', width: 110 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (value) => <Tag color={taskStatusColor(value)}>{taskStatusLabel(value)}</Tag>
    },
    { title: '重试', width: 90, render: (_, row) => retryLabel(row) },
    { title: '开始时间', dataIndex: 'started_at', width: 160, render: (value) => formatTime(value, true) },
    { title: '结束时间', dataIndex: 'ended_at', width: 160, render: (value) => formatTime(value, true) },
    { title: '摘要', dataIndex: 'summary', ellipsis: true, render: (value) => value || '-' },
    { title: '邮件', width: 150, render: (_, row) => emailRunStatus(row) },
    {
      title: '操作',
      width: 220,
      fixed: 'right',
      render: (_, row) => (
        <Space size={4}>
          <Button type="link" size="small" onClick={() => viewRunDetail(row)}>
            详情
          </Button>
          <Button type="link" size="small" loading={exportingRunId === row.id} onClick={() => onExportRunPdfs(row)}>
            导出PDF
          </Button>
          <Button type="link" size="small" onClick={() => openFailedReprints(row)}>
            {isSuccessfulRun(row) ? '重新打印' : '失败重打'}
          </Button>
        </Space>
      )
    }
  ]

  const stepColumns: ColumnsType<ScheduledTaskRunStepDto> = [
    { title: '步骤', dataIndex: 'step_name', width: 180 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value) => <Tag color={taskStatusColor(value)}>{taskStatusLabel(value)}</Tag>
    },
    { title: '说明', dataIndex: 'message', ellipsis: true, render: (value) => value || '-' },
    { title: '开始时间', dataIndex: 'started_at', width: 170, render: (value) => formatTime(value, true) },
    { title: '结束时间', dataIndex: 'ended_at', width: 170, render: (value) => formatTime(value, true) }
  ]

  const runPlatformColumns: ColumnsType<ScheduledTaskRunPlatformDto> = [
    { title: '平台', dataIndex: 'platform', width: 140, render: (value) => formatPlatformLabel(value) },
    { title: '单据', dataIndex: 'document_type_name', width: 100, render: (value) => value || '面单' },
    {
      title: '数量',
      width: 170,
      render: (_, row) => (
        <Space size={4} wrap>
          <Tag>订单 {row.total_count}</Tag>
          <Tag color="processing">PDF {row.pdf_count}</Tag>
          {row.failed_count ? <Tag color="error">失败 {row.failed_count}</Tag> : null}
        </Space>
      )
    },
    {
      title: '打印状态',
      width: 120,
      render: (_, row) => {
        const status = platformPrintStatus(row)
        return <Tag color={status.color}>{status.label}</Tag>
      }
    },
    { title: '打印机', width: 150, ellipsis: true, render: (_, row) => compactTextList(row.printer_names) },
    { title: '涉及订单', width: 220, ellipsis: true, render: (_, row) => compactTextList(row.order_nos) },
    { title: '处理说明', ellipsis: true, render: (_, row) => compactTextList(row.messages) },
    {
      title: '操作',
      width: 130,
      fixed: 'right',
      render: (_, row) => {
        const canReprint = row.needs_reprint || (isSuccessfulRun(selectedRun) && row.pdf_count > 0)
        if (!canReprint) return null
        return (
          <Button
            type="link"
            size="small"
            loading={reprintingPlatform === row.platform}
            onClick={() => onReprintPlatform(row)}
          >
            {isSuccessfulRun(selectedRun) ? '重新打印平台' : '重打平台'}
          </Button>
        )
      }
    }
  ]

  const orderColumns: ColumnsType<ScheduledTaskRunOrderDto> = [
    { title: '单据', dataIndex: 'document_type_name', width: 90, render: (value) => value || '面单' },
    { title: '订单编号', dataIndex: 'platform_order_no', width: 150, ellipsis: true, render: (value, row) => value || (row.order_id && row.order_id !== 0 ? row.order_id : '-') },
    { title: '平台', dataIndex: 'platform', width: 120, render: (value) => formatPlatformLabel(value) },
    { title: '前状态', dataIndex: 'status_before', width: 120 },
    { title: '后状态', dataIndex: 'status_after', width: 120 },
    {
      title: 'PDF',
      dataIndex: 'pdf_generated',
      width: 90,
      render: (_, row) => {
        const status = pdfStatus(row)
        return <Tag color={status.color}>{status.label}</Tag>
      }
    },
    { title: '打印机', dataIndex: 'printer_name', width: 150, render: (value) => value || '-' },
    { title: '打印任务', dataIndex: 'print_job_name', width: 180, ellipsis: true, render: (value) => value || '-' },
    {
      title: '打印提交',
      width: 180,
      render: (_, row) => {
        const status = printSubmitStatus(row)
        return <Tag color={status.color}>{status.label}</Tag>
      }
    },
    { title: '采购单', dataIndex: 'purchase_order_id', width: 120, render: (value) => value || '-' },
    {
      title: '处理说明',
      width: 240,
      ellipsis: true,
      render: (_, row) => row.error_message || row.print_message || '-'
    },
    {
      key: 'actions',
      title: '操作',
      width: 110,
      fixed: 'right',
      render: (_, row) => {
        const canReprint = row.needs_reprint || (isSuccessfulRun(selectedRun) && row.pdf_generated)
        if (!canReprint) return null
        return (
          <Button type="link" size="small" onClick={() => onReprintOrder(row)}>
            {isSuccessfulRun(selectedRun) ? '重新打印' : '重打'}
          </Button>
        )
      }
    }
  ]

  const failedRunOrderColumns = orderColumns.filter((column) => String(column.key || '') !== 'actions')

  const runPagination: TablePaginationConfig = {
    current: runPage,
    pageSize: runPageSize,
    total: runTotal,
    showSizeChanger: true,
    showLessItems: true,
    pageSizeOptions: [50, 100, 500],
    showTotal: (value) => `共 ${value} 条`,
    onChange: (nextPage, nextPageSize) => {
      setRunPage(nextPage)
      setRunPageSize(nextPageSize)
    }
  }

  const platformTab = (
    <DataTable
      rowKey="platform"
      loading={loadingPlatformSettings}
      dataSource={platformSettings}
      columns={platformColumns}
      pagination={false}
    />
  )

  const printTab = (
    <>
      <div className="toolbar-row" style={{ justifyContent: 'space-between' }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => void openPrintCreate()}>
          新增打印设置
        </Button>
      </div>
      <DataTable
        rowKey="id"
        loading={loadingPrint}
        dataSource={printSettings}
        columns={printColumns}
        pagination={false}
        onRow={(row) => ({
          onDoubleClick: (event) => {
            if (shouldIgnoreTableRowDoubleClick(event.target)) return
            void openPrintEdit(row)
          }
        })}
      />
    </>
  )

  const deadlineTab = (
    <>
      <div className="toolbar-row" style={{ justifyContent: 'space-between' }}>
        <Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={addDeadlineRow}>
            新增规则
          </Button>
          <Button loading={loadingDeadline} onClick={loadDeadlineSettings}>
            刷新
          </Button>
        </Space>
        <Button type="primary" loading={savingDeadline} onClick={saveDeadlineSettings}>
          保存并回填
        </Button>
      </div>
      <DataTable
        rowKey="id"
        loading={loadingDeadline}
        dataSource={deadlineRows}
        columns={deadlineColumns}
        pagination={false}
        className="deadline-settings-table"
        rowClassName={(row) =>
          ['deadline-settings-table__row', String(row.id) === String(draggingDeadlineId) ? 'deadline-settings-table__row--dragging' : '']
            .filter(Boolean)
            .join(' ')
        }
        onRow={(row) => ({
          onDragOver: (event) => {
            event.preventDefault()
            event.dataTransfer.dropEffect = 'move'
          },
          onDrop: (event) => dropDeadlineRow(event, row)
        })}
      />
    </>
  )

  const taskTab = (
    <>
      <div className="toolbar-row" style={{ justifyContent: 'space-between' }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={openTaskCreate}>
          新增定时任务
        </Button>
      </div>
      <DataTable
        rowKey="id"
        loading={loadingTasks}
        dataSource={tasks}
        columns={taskColumns}
        pagination={false}
        onRow={(row) => ({
          onDoubleClick: (event) => {
            if (shouldIgnoreTableRowDoubleClick(event.target)) return
            openTaskEdit(row)
          }
        })}
      />
    </>
  )

  const emailTab = (
    <Form form={emailForm} layout="vertical" className="system-email-form">
      <div className="system-email-header">
        <div>
          <div className="system-email-title">邮件通知</div>
          <div className="muted">配置 SMTP 发件账号，用于定时任务失败提醒和测试邮件。</div>
        </div>
        <div className="system-email-header__actions">
          <Tag color={emailState?.enabled ? 'success' : 'default'}>{emailState?.enabled ? '已启用' : '未启用'}</Tag>
          <Button type="primary" loading={savingEmail} onClick={() => onSaveEmailSetting()}>
            保存设置
          </Button>
        </div>
      </div>

      <div className="system-email-layout">
        <section className="system-email-panel system-email-panel--main">
          <div className="system-email-panel__head">
            <div className="system-email-panel__title">基础配置</div>
            <div className="muted">选择服务商后会自动填充主机、端口和 SSL。</div>
          </div>
          <div className="system-email-grid system-email-grid--basic">
            <Form.Item label="服务商" name="provider" rules={[{ required: true, message: '请选择服务商' }]}>
              <Select options={emailProviderOptions} onChange={(value) => applyEmailProvider(value)} />
            </Form.Item>
            <Form.Item label="启用邮件通知" name="enabled" valuePropName="checked">
              <Switch checkedChildren="启用" unCheckedChildren="停用" />
            </Form.Item>
            <Form.Item label="SMTP Host" name="smtp_host" rules={[{ required: true, message: '请输入 SMTP Host' }]}>
              <Input />
            </Form.Item>
            <Form.Item label="SMTP Port" name="smtp_port" rules={[{ required: true, message: '请输入端口' }]}>
              <InputNumber min={1} max={65535} />
            </Form.Item>
            <Form.Item label="SSL" name="use_ssl" valuePropName="checked">
              <Switch checkedChildren="SSL" unCheckedChildren="非 SSL" />
            </Form.Item>
            <Form.Item label="发件人名称" name="sender_name">
              <Input placeholder="CaifuClaw 系统" />
            </Form.Item>
          </div>
        </section>

        <section className="system-email-panel">
          <div className="system-email-panel__head">
            <div className="system-email-panel__title">账号与测试</div>
            <div className="muted">授权码留空时不会覆盖已保存的密码。</div>
          </div>
          <div className="system-email-stack">
            <Form.Item label="发件邮箱" name="sender_email" rules={[{ required: true, message: '请输入发件邮箱' }]}>
              <Input placeholder={selectedEmailProvider?.sender_hint || 'demo@example.invalid'} />
            </Form.Item>
            <Form.Item label="授权码/密码" name="auth_code">
              <Input.Password
                placeholder={
                  emailState?.has_auth_code
                    ? '已保存，留空表示不修改'
                    : selectedEmailProvider?.auth_code_hint || '请输入 SMTP 授权码或密码'
                }
              />
            </Form.Item>
            <div className="system-email-test-card">
              <Form.Item label="测试收件人" name="test_recipient">
                <Input />
              </Form.Item>
              <Button loading={testingEmail} onClick={onTestEmailSetting}>
                发送测试
              </Button>
              <div className="system-email-test__result">
                <span className="muted">最近测试</span>
                <strong>{emailState?.last_test_at ? formatTime(emailState.last_test_at, true) : '-'}</strong>
                <span>
                  {emailState?.last_test_status ? `结果：${emailState.last_test_status === 'success' ? '成功' : '失败'}` : '暂无结果'}
                  {emailState?.last_test_message ? `，${emailState.last_test_message}` : ''}
                </span>
              </div>
            </div>
          </div>
        </section>
      </div>

      <section className="system-email-panel system-email-panel--recipients">
        <div className="system-email-panel__head">
          <div className="system-email-panel__title">异常收件人</div>
          <div className="muted">按异常类型配置收件人。多个邮箱请用分号隔开；留空则不发送该类型的邮件。</div>
        </div>
        <div className="system-email-recipient-grid">
          <Form.Item label="万邦接口 / 运单回填异常" name={['notification_recipients', 'wanbang_tracking_failure']}>
            <Input inputMode="email" placeholder="demo@example.invalid; demo@example.invalid" />
          </Form.Item>
          <Form.Item label="BSI 收货地址异常" name={['notification_recipients', 'bsi_address_anomaly']}>
            <Input inputMode="email" placeholder="demo@example.invalid; demo@example.invalid" />
          </Form.Item>
        </div>
      </section>
    </Form>
  )

  const modelSettingsTab = (
    <div className="system-model-settings">
      <div className="system-model-header">
        <div>
          <div className="system-model-title">模型设置</div>
          <div className="muted">先维护可复用的 OpenAI-compatible 接口配置，再将模型绑定到接口。</div>
        </div>
        <Space wrap>
          <Button icon={<ApiOutlined />} onClick={() => setModelEndpointSettingsOpen(true)}>
            接口设置
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openModelCreate}>
            新建模型
          </Button>
        </Space>
      </div>
      <DataTable<ModelSettingDto>
        rowKey="id"
        loading={loadingModels}
        dataSource={modelSettings}
        columns={modelColumns}
        pagination={false}
        className="system-model-table"
      />
    </div>
  )

  const wecomTab = (
    <Form
      form={wecomForm}
      layout="vertical"
      className="system-wecom-form"
      initialValues={emptyWecomFormValues}
      disabled={loadingWecom}
    >
      <div className="system-wecom-header">
        <div>
          <div className="system-wecom-title">企业微信设置</div>
          <div className="muted">配置群聊机器人 webhook、默认提醒对象和发送节流策略。</div>
        </div>
        <div className="system-wecom-header__actions">
          <Tag color={wecomState?.has_webhook_url ? 'success' : 'default'}>
            {wecomState?.has_webhook_url ? '已配置' : '未配置'}
          </Tag>
          <Button loading={testingWecom} onClick={onTestWecomSetting}>
            发送测试
          </Button>
          <Button type="primary" loading={savingWecom} onClick={() => onSaveWecomSetting()}>
            保存设置
          </Button>
        </div>
      </div>

      <div className="system-wecom-layout">
        <section className="system-wecom-panel system-wecom-panel--main">
          <div className="system-wecom-panel__head">
            <div className="system-wecom-panel__title">机器人凭据与节流</div>
            <div className="muted">Webhook URL 会加密存储；已配置时留空表示保留当前地址。</div>
          </div>
          <div className="system-wecom-grid system-wecom-grid--basic">
            <Form.Item
              label="Webhook URL"
              name="webhook_url"
              rules={[
                {
                  validator: async (_, value) => {
                    const current = String(value || '').trim()
                    if (!current && wecomState?.has_webhook_url) return
                    if (!current) throw new Error('请输入企业微信群机器人 webhook 地址')
                    return
                  }
                }
              ]}
              extra={wecomState?.webhook_url_masked ? `当前已保存：${wecomState.webhook_url_masked}` : '示例：https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=***'}
            >
              <Input.Password
                placeholder={
                  wecomState?.has_webhook_url
                    ? '已保存，留空表示不修改'
                    : '请输入企业微信群机器人 webhook 地址'
                }
              />
            </Form.Item>
            <Form.Item
              label="超时（秒）"
              name="timeout_seconds"
              rules={[{ required: true, message: '请输入超时时间' }]}
            >
              <InputNumber min={1} max={300} />
            </Form.Item>
            <Form.Item
              label="重试次数"
              name="max_retries"
              rules={[{ required: true, message: '请输入重试次数' }]}
            >
              <InputNumber min={0} max={10} />
            </Form.Item>
            <Form.Item
              label="每分钟上限"
              name="rate_limit_per_minute"
              rules={[{ required: true, message: '请输入每分钟发送上限' }]}
            >
              <InputNumber min={1} max={20} />
            </Form.Item>
          </div>
        </section>

        <section className="system-wecom-panel">
          <div className="system-wecom-panel__head">
            <div className="system-wecom-panel__title">默认提醒</div>
            <div className="muted">选择用户后，系统会使用用户资料里的企微手机号进行提醒；不选则不 @ 人。</div>
          </div>
          <div className="system-wecom-stack">
            <Form.Item label="默认提示语" name="default_prompt">
              <Input.TextArea rows={4} maxLength={512} showCount placeholder="可为空，发送时可按业务覆盖" />
            </Form.Item>
            <Form.Item
              label="采购单通知"
              name="purchase_order_notify_enabled"
              valuePropName="checked"
              extra="开启后，生成采购单成功时会异步发送采购单表格图片到该群。"
            >
              <Switch checkedChildren="开启" unCheckedChildren="关闭" />
            </Form.Item>
            <Form.Item label="默认提醒用户" name="default_mentioned_user_ids" extra="来自用户表；未配置企微手机号的用户会显示但不可选择，可为空。">
              <Select
                mode="multiple"
                allowClear
                loading={loadingWecomUsers}
                optionFilterProp="searchText"
                options={wecomUserOptions}
                notFoundContent={loadingWecomUsers ? '加载中...' : '暂无启用用户'}
                placeholder="请选择需要默认提醒的用户"
              />
            </Form.Item>
            <div className="system-wecom-meta">
              <span className="muted">最近更新</span>
              <strong>{wecomState?.updated_at ? formatTime(wecomState.updated_at, true) : '-'}</strong>
            </div>
          </div>
        </section>
      </div>
    </Form>
  )

  const translationTab = (
    <Form
      form={translationForm}
      layout="vertical"
      className="system-translation-form"
      initialValues={emptyTranslationFormValues}
      disabled={loadingTranslation}
    >
      <div className="system-translation-header">
        <div>
          <div className="system-translation-title">翻译设置</div>
          <div className="muted">维护文本翻译功能使用的服务参数。</div>
        </div>
        <div className="system-translation-header__actions">
          <Tag color={translationState?.enabled ? 'success' : 'default'}>
            {translationState?.enabled ? '已启用' : '未启用'}
          </Tag>
          <Tag color={translationState?.has_secret_key ? 'processing' : 'default'}>
            {translationState?.has_secret_key ? '密钥已保存' : '未配置密钥'}
          </Tag>
          <Button type="primary" loading={savingTranslation} onClick={() => onSaveTranslationSetting()}>
            保存设置
          </Button>
        </div>
      </div>

      <div className="system-translation-layout">
        <section className="system-translation-panel system-translation-panel--main">
          <div className="system-translation-panel__head">
            <div className="system-translation-panel__title">服务商与凭据</div>
            <div className="muted">密钥会加密存储；已配置时留空表示保留当前密钥。</div>
          </div>
          <div className="system-translation-grid system-translation-grid--credentials">
            <Form.Item label="翻译服务商" name="provider" rules={[{ required: true, message: '请选择翻译服务商' }]}>
              <Select
                options={translationProviderSelectOptions}
                onChange={(value) => void onTranslationProviderChange(value)}
              />
            </Form.Item>
            <Form.Item label="启用" name="enabled" valuePropName="checked">
              <Switch checkedChildren="开启" unCheckedChildren="关闭" />
            </Form.Item>
            <Form.Item
              label="App ID"
              name="app_id"
              rules={[
                {
                  validator: async (_, value) => {
                    if (translationForm.getFieldValue('enabled') && !String(value || '').trim()) {
                      throw new Error('请输入 App ID')
                    }
                  }
                }
              ]}
            >
              <Input placeholder="请输入翻译服务商 App ID" />
            </Form.Item>
            <Form.Item
              label="Secret Key"
              name="secret_key"
              extra={translationState?.secret_key_masked ? `当前已保存：${translationState.secret_key_masked}` : '用于调用翻译服务的密钥'}
              rules={[
                {
                  validator: async (_, value) => {
                    if (
                      translationForm.getFieldValue('enabled') &&
                      !String(value || '').trim() &&
                      !translationState?.has_secret_key
                    ) {
                      throw new Error('请输入 Secret Key')
                    }
                  }
                }
              ]}
            >
              <Input.Password placeholder={translationState?.has_secret_key ? '已保存，留空表示不修改' : '请输入 Secret Key'} />
            </Form.Item>
            <Form.Item
              label="接口地址"
              name="endpoint"
              rules={[{ required: true, type: 'url', message: '请输入有效的接口地址' }]}
            >
              <Input placeholder="https://fanyi-api.baidu.com/api/trans/vip/translate" />
            </Form.Item>
          </div>
        </section>

        <section className="system-translation-panel">
          <div className="system-translation-panel__head">
            <div className="system-translation-panel__title">调用策略与测试</div>
            <div className="muted">目标语言由产品类目的平台映射决定，这里只维护调用参数和测试样例。</div>
          </div>
          <div className="system-translation-grid system-translation-grid--runtime">
            <Form.Item label="源语言" name="source_language" rules={[{ required: true, message: '请输入源语言' }]}>
              <Input placeholder="auto" />
            </Form.Item>
            <Form.Item label="超时（秒）" name="timeout_seconds" rules={[{ required: true, message: '请输入超时时间' }]}>
              <InputNumber min={1} max={300} />
            </Form.Item>
            <Form.Item label="重试次数" name="max_retries" rules={[{ required: true, message: '请输入重试次数' }]}>
              <InputNumber min={0} max={10} />
            </Form.Item>
            <Form.Item label="单批文本数" name="batch_size" rules={[{ required: true, message: '请输入单批文本数' }]}>
              <InputNumber min={1} max={200} />
            </Form.Item>
            <Form.Item label="单批字符数" name="batch_chars" rules={[{ required: true, message: '请输入单批字符数' }]}>
              <InputNumber min={100} max={20000} step={100} />
            </Form.Item>
          </div>
          <div className="system-translation-test-card">
            <Form.Item label="测试文本" name="test_text">
              <Input.TextArea rows={3} maxLength={300} showCount placeholder="输入一段文本进行测试" />
            </Form.Item>
            <Form.Item label="测试目标语言" name="test_target_language">
              <Select
                showSearch
                loading={loadingTranslationLanguages}
                optionFilterProp="label"
                options={translationTargetLanguageOptions}
                popupMatchSelectWidth={260}
              />
            </Form.Item>
            <Button loading={testingTranslation} onClick={onTestTranslationSetting}>
              测试翻译
            </Button>
            {translationTestResult ? (
              <div className={`system-translation-test__result system-translation-test__result--${translationTestResult.status}`}>
                <strong>{translationTestResult.status === 'success' ? '测试结果' : '测试失败'}</strong>
                <span>{translationTestResult.message || '-'}</span>
              </div>
            ) : null}
            <div className="system-translation-meta">
              <span className="muted">最近测试</span>
              <strong>{translationState?.last_test_at ? formatTime(translationState.last_test_at, true) : '-'}</strong>
            </div>
          </div>
        </section>
      </div>
    </Form>
  )

  const runTab = (
    <>
      <div className="orders-header">
        <h2>定时任务日志</h2>
      </div>
      {!logsOnly ? null : <div className="muted" style={{ marginBottom: 16 }}>查看定时任务执行记录、失败明细和失败重打。</div>}
      <DataTable
        rowKey="id"
        loading={loadingRuns}
        dataSource={taskRuns}
        columns={runColumns}
        className="task-log-table"
        pagination={runPagination}
        onRow={(row) => ({
          onDoubleClick: (event) => {
            if (shouldIgnoreTableRowDoubleClick(event.target)) return
            void viewRunDetail(row)
          }
        })}
      />
    </>
  )

  return (
    <div className="page-card">
      {logsOnly ? (
        runTab
      ) : (
        <Tabs
          activeKey={activeTab}
          onChange={(key) => setActiveTab(key as ActiveTab)}
          items={[
            { key: 'platforms', label: '平台列表', children: platformTab },
            { key: 'print', label: '打印设置', children: printTab },
            { key: 'deadline', label: '发货截止时间设置', children: deadlineTab },
            { key: 'tasks', label: '定时任务', children: taskTab },
            { key: 'email', label: '邮件通知', children: emailTab },
            { key: 'models', label: '模型设置', children: modelSettingsTab },
            { key: 'wecom', label: '企业微信设置', children: wecomTab },
            { key: 'translation', label: '翻译设置', children: translationTab, forceRender: true }
          ]}
        />
      )}

      <Modal
        open={modelEndpointSettingsOpen}
        title="接口设置"
        width="min(1280px, calc(100vw - 48px))"
        footer={null}
        destroyOnClose
        onCancel={() => setModelEndpointSettingsOpen(false)}
        className="model-endpoint-settings-modal"
      >
        <div className="model-endpoint-settings-toolbar">
          <span className="muted">统一管理可复用的 OpenAI-compatible 接口配置。</span>
          <Button type="primary" icon={<PlusOutlined />} onClick={openModelEndpointCreate}>
            新建接口配置
          </Button>
        </div>
        <DataTable<ModelEndpointDto>
          rowKey="id"
          loading={loadingModels}
          dataSource={modelEndpoints}
          columns={modelEndpointColumns}
          pagination={{ pageSize: 8 }}
          scroll={{ y: 'calc(100vh - 360px)' }}
        />
      </Modal>

      <Modal
        open={modelEndpointOpen}
        title={modelEndpointMode === 'create' ? '新建接口配置' : '编辑接口配置'}
        width={680}
        confirmLoading={savingModel}
        maskClosable={false}
        destroyOnClose
        onOk={submitModelEndpoint}
        onCancel={closeModelEndpointModal}
      >
        <Form form={modelEndpointForm} layout="vertical" initialValues={emptyModelEndpointFormValues} preserve={false}>
          <Form.Item label="接口配置名称" name="name" rules={[{ required: true, message: '请输入接口配置名称' }]}>
            <Input autoFocus placeholder="例如：公司共享网关" maxLength={160} />
          </Form.Item>
          <Form.Item label="base url" name="base_url" rules={[{ required: true, message: '请输入接口地址' }]}>
            <Input placeholder="例如：https://api.example.com" />
          </Form.Item>
          <Form.Item
            label="api key"
            name="api_key"
            rules={modelEndpointMode === 'create' ? [{ required: true, message: '请输入api key' }] : []}
            extra={modelEndpointMode === 'edit' ? '留空则保留原 api key；输入新值才会替换。' : undefined}
          >
            <Input.Password placeholder={modelEndpointMode === 'edit' ? '留空则保留原 api key' : '请输入api key'} autoComplete="off" />
          </Form.Item>
          <Form.Item label="备注" name="remark">
            <Input placeholder="例如：公司共享代理、官方账号、备用线路" maxLength={500} />
          </Form.Item>
          <Form.Item label="启用状态" name="enabled" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="禁用" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={modelOpen}
        title={modelMode === 'create' ? '新建模型设置' : '编辑模型设置'}
        width={680}
        confirmLoading={savingModel}
        maskClosable={false}
        destroyOnClose
        onOk={submitModel}
        onCancel={closeModelModal}
        footer={(_, { CancelBtn, OkBtn }) => (
          <div className="model-setting-modal-footer">
            <div className="model-setting-test-zone" aria-live="polite">
              <Button onClick={testCurrentModel} loading={testingModel}>
                测试连接
              </Button>
              {modelTestResult ? (
                <span className={modelTestResult.status === 'success' ? 'model-test-result--success' : 'model-test-result--error'}>
                  {modelTestResult.message}
                </span>
              ) : null}
            </div>
            <Space>
              <CancelBtn />
              <OkBtn />
            </Space>
          </div>
        )}
      >
        <Form form={modelForm} layout="vertical" initialValues={emptyModelFormValues} preserve={false}>
          <Form.Item label="模型名称" name="name" rules={[{ required: true, message: '请输入模型名称' }]}>
            <Input autoFocus placeholder="例如：默认写作模型" maxLength={160} />
          </Form.Item>
          <Form.Item label="模型" name="model" rules={[{ required: true, message: '请输入模型标识' }]}>
            <Input placeholder="例如：gpt-4.1-mini" maxLength={160} />
          </Form.Item>
          <Form.Item label="接口配置" name="endpoint_id" rules={[{ required: true, message: '请选择接口配置' }]}>
            <Select placeholder="请选择共享的 url 和 api key" options={modelEndpointOptions} showSearch optionFilterProp="label" />
          </Form.Item>
          <Form.Item name="is_default" label="默认模型" valuePropName="checked" extra="设为默认后，业务界面会优先使用该模型。">
            <Switch checkedChildren="默认" unCheckedChildren="普通" />
          </Form.Item>
          <Form.Item name="supports_vision" label="图片理解" valuePropName="checked" extra="启用后，产品 AI 导入和智能图片拆分可以调用该模型识别图片。">
            <Switch checkedChildren="支持" unCheckedChildren="不支持" />
          </Form.Item>
          <Form.Item
            name="enabled"
            label="启用状态"
            valuePropName="checked"
            extra="禁用后，该模型不会出现在业务界面的可用模型列表中。"
          >
            <Switch checkedChildren="启用" unCheckedChildren="禁用" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={printOpen}
        title={printMode === 'create' ? '新增打印设置' : '编辑打印设置'}
        confirmLoading={saving}
        maskClosable={false}
        width={520}
        onOk={savePrintSetting}
        onCancel={() => setPrintOpen(false)}
        destroyOnClose
      >
        <Form form={printForm} labelCol={{ span: 6 }} wrapperCol={{ span: 16 }} preserve={false}>
          <Form.Item label="平台" name="platform" rules={[{ required: true, message: '请选择平台' }]}>
            <Select options={activePrintPlatformSelectOptions} />
          </Form.Item>
          <Form.Item label="单据类型" name="document_type" rules={[{ required: true, message: '请选择单据类型' }]}>
            <Select options={printDocumentTypes} />
          </Form.Item>
          <Form.Item label="打印机" name="printer_name" rules={[{ required: true, message: '请选择打印机' }]}>
            <Select
              loading={loadingPrinters}
              optionRender={(option) => {
                const value = String(option.value || '')
                const printer = printers.find((item) => item.name === value)
                if (printer) return renderPrinterOption(printer)
                return (
                  <Space size={6} wrap>
                    <span>{value}</span>
                    <Tag color="error">未检测到</Tag>
                  </Space>
                )
              }}
              options={printerOptions}
              optionFilterProp="searchText"
              placeholder="请选择打印机"
              showSearch
            />
          </Form.Item>
          <Form.Item label="打印方向" name="page_orientation" rules={[{ required: true, message: '请选择打印方向' }]}>
            <Select options={[...printOrientationOptions]} />
          </Form.Item>
          <Form.Item label="启用" name="enabled" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item label="备注" name="remark">
            <Input />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={taskOpen}
        title={taskMode === 'create' ? '新增定时任务' : '编辑定时任务'}
        confirmLoading={saving}
        maskClosable={false}
        width={720}
        onOk={saveTask}
        onCancel={() => setTaskOpen(false)}
        destroyOnClose
      >
        <Form form={taskForm} layout="vertical" preserve={false}>
          <Form.Item label="任务名称" name="name" rules={[{ required: true, message: '请输入任务名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item label="任务类型" name="task_type" rules={[{ required: true, message: '请选择任务类型' }]}>
            <Select options={taskTypeOptions} />
          </Form.Item>
          <Space size={16} align="start" wrap>
            <Form.Item label="计划类型" name="schedule_type">
              <Select style={{ width: 140 }} options={scheduleTypeOptions} />
            </Form.Item>
            {scheduleType === 'interval' ? (
              <Form.Item label="间隔时间(分钟)" name="poll_interval_minutes" rules={[{ required: true, message: '请输入间隔时间' }]}>
                <InputNumber min={1} max={1440} style={{ width: 150 }} />
              </Form.Item>
            ) : null}
            {scheduleType !== 'custom' && scheduleType !== 'interval' ? (
              <Form.Item label="执行时间" name="schedule_time" rules={[{ required: true, message: '请输入执行时间' }]}>
                <Input placeholder="HH:mm" style={{ width: 120 }} />
              </Form.Item>
            ) : null}
            {scheduleType === 'weekly' ? (
              <Form.Item label="执行星期" name="weekday">
                <Select style={{ width: 140 }} options={weekdayOptions} />
              </Form.Item>
            ) : null}
            {scheduleType === 'monthly' ? (
              <Form.Item label="执行日期" name="month_day">
                <Select style={{ width: 140 }} options={monthDayOptions} />
              </Form.Item>
            ) : null}
          </Space>
          {scheduleType === 'custom' ? (
            <Form.Item label="Cron 表达式" name="cron_expr" rules={[{ required: true, message: '请输入 Cron 表达式' }]}>
              <Input />
            </Form.Item>
          ) : null}
          <Form.Item label="启用" name="enabled" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Space size={16} align="start" wrap>
            <Form.Item label="重试次数" name="retry_count">
              <InputNumber min={0} max={10} />
            </Form.Item>
            <Form.Item label="重试间隔(分钟)" name="retry_interval_minutes">
              <InputNumber min={1} max={120} />
            </Form.Item>
            <Form.Item label="超时(分钟)" name="timeout_minutes">
              <InputNumber min={1} max={240} />
            </Form.Item>
          </Space>
          <Form.Item label="失败邮件通知" name="failure_email_enabled" valuePropName="checked">
            <Switch checkedChildren="开启" unCheckedChildren="关闭" />
          </Form.Item>
          <Form.Item label="失败收件人" name="failure_email_recipients">
            <Input placeholder="多个邮箱用英文逗号分隔" />
          </Form.Item>
          <Form.Item label="备注" name="remark">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={runDetailOpen}
        title={`任务执行详情 #${selectedRun?.id || ''}`}
        width="min(1000px, calc(100vw - 32px))"
        footer={null}
        onCancel={() => setRunDetailOpen(false)}
        destroyOnClose
      >
        {selectedRun ? (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="状态">
                <Tag color={taskStatusColor(selectedRun.status)}>{taskStatusLabel(selectedRun.status)}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="触发方式">{selectedRun.trigger_mode || '-'}</Descriptions.Item>
              <Descriptions.Item label="任务类型">{selectedRun.task_type || '-'}</Descriptions.Item>
              <Descriptions.Item label="重试">{retryLabel(selectedRun)}</Descriptions.Item>
              <Descriptions.Item label="开始时间">{formatTime(selectedRun.started_at, true)}</Descriptions.Item>
              <Descriptions.Item label="结束时间">{formatTime(selectedRun.ended_at, true)}</Descriptions.Item>
              <Descriptions.Item label="邮件" span={2}>
                {emailRunStatus(selectedRun)}
              </Descriptions.Item>
              <Descriptions.Item label="摘要" span={2}>
                {selectedRun.summary || '-'}
              </Descriptions.Item>
            </Descriptions>
            <h3>执行步骤</h3>
            <DataTable rowKey="id" size="small" dataSource={selectedRunSteps} columns={stepColumns} pagination={false} />
            <h3>订单处理</h3>
            <DataTable
              rowKey="id"
              size="small"
              dataSource={selectedRunOrders}
              columns={orderColumns}
              className="task-log-table"
              pagination={false}
            />
          </Space>
        ) : null}
      </Modal>

      <Modal
        open={failedReprintOpen}
        title={`${isSuccessfulRun(selectedRun) ? '重新打印' : '失败重打'} #${selectedRun?.id || ''}`}
        width="min(1080px, calc(100vw - 32px))"
        footer={null}
        onCancel={() => {
          setFailedReprintOpen(false)
          setExpandedFailedPlatforms([])
        }}
        destroyOnClose
      >
        <DataTable
          rowKey="platform"
          size="small"
          loading={loadingFailedRunOrders}
          dataSource={failedRunPlatforms}
          columns={runPlatformColumns}
          className="task-log-table"
          pagination={false}
          expandable={{
            expandedRowKeys: expandedFailedPlatforms,
            onExpandedRowsChange: (keys) => setExpandedFailedPlatforms(keys.map((key) => String(key))),
            expandedRowRender: (row) => {
              const orders = platformRunOrders(failedRunOrders, row.platform, selectedRun)
              return (
                <DataTable
                  rowKey="id"
                  size="small"
                  dataSource={orders}
                  columns={failedRunOrderColumns}
                  className="task-log-table task-log-table--nested"
                  pagination={false}
                />
              )
            }
          }}
        />
      </Modal>
    </div>
  )
}
