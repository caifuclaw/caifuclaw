/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AimOutlined, ProfileOutlined } from '@ant-design/icons'
import { App, Button, Card, Input, Space, Tag, Tooltip } from 'antd'
import type { InputRef } from 'antd'
import { DataTable } from '@/components/DataTable'
import type { DataTableConfig } from '@/components/DataTable'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { useNavigate } from '@/router/navigation'
import {
  createOutboundScan,
  fetchOutboundScanStats,
  listOutboundScans,
  type OutboundScanRecordDto,
  type OutboundScanStatsResponse
} from '@/api/outbound'
import { playDuplicate, playError, playSuccess, preloadScanSounds, unlockAudio } from '@/utils/audio'

const initialStats: OutboundScanStatsResponse = {
  success: 0,
  duplicate: 0,
  not_found: 0,
  invalid: 0,
  error: 0,
  total: 0,
  last_scanned_at: null
}

const SCAN_OUTBOUND_RECORDS_TABLE_CONFIG: DataTableConfig = {
  tableKey: 'scan-outbound.today-records',
  primaryColumnKey: 'tracking_number',
  widthMode: 'adaptive-left',
  columns: [
    { key: 'scanned_at', title: '扫码时间' },
    { key: 'tracking_number', title: '货运单号', required: true, fixed: false },
    { key: 'result', title: '结果' },
    { key: 'platform', title: '平台' },
    { key: 'shop_name', title: '店铺' },
    { key: 'platform_order_no', title: '订单编号' },
    { key: 'order_status', title: '订单状态' },
    { key: 'scanned_by', title: '操作员' },
    { key: 'message', title: '说明' }
  ]
}

function resultLabel(value?: string) {
  return (
    {
      success: '成功',
      duplicate: '重复',
      not_found: '未找到',
      invalid: '无效',
      error: '异常'
    } as Record<string, string>
  )[value || ''] || value || '-'
}

function resultColor(value?: string) {
  if (value === 'success') return 'success'
  if (value === 'duplicate') return 'warning'
  if (value === 'not_found' || value === 'invalid' || value === 'error') return 'error'
  return 'default'
}

function formatStatTime(value: string | null) {
  if (!value) return '-'
  const d = dayjs(value)
  return d.isValid() ? d.format('HH:mm:ss') : '-'
}

function playFeedback(result: string) {
  try {
    if (result === 'success') void playSuccess()
    else if (result === 'duplicate') void playDuplicate()
    else void playError()
  } catch {
    // Audio feedback is best-effort only.
  }
}

export function ScanOutbound() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const inputRef = useRef<InputRef | null>(null)
  const focusTimerRef = useRef<number | null>(null)
  const queueRef = useRef<{ tracking_number: string; raw_input: string }[]>([])
  const processingRef = useRef(false)
  const [scanValue, setScanValue] = useState('')
  const scanValueRef = useRef('')
  const [scanStarted, setScanStarted] = useState(false)
  const [loading, setLoading] = useState(false)
  const [processing, setProcessing] = useState(false)
  const [queueSize, setQueueSize] = useState(0)
  const [recentRecords, setRecentRecords] = useState<OutboundScanRecordDto[]>([])
  const [stats, setStats] = useState<OutboundScanStatsResponse>(initialStats)
  const [lastResult, setLastResult] = useState({ result: 'idle', tracking_number: '' })

  const pendingCount = queueSize + (processing ? 1 : 0)
  const failedCount = stats.not_found + stats.invalid + stats.error

  const focusScanInput = useCallback(() => {
    window.setTimeout(() => inputRef.current?.focus({ cursor: 'end' }), 0)
  }, [])

  async function loadStats() {
    try {
      setStats(await fetchOutboundScanStats())
    } catch {
      // Keep current values when stats refresh fails.
    }
  }

  async function loadRecent() {
    setLoading(true)
    try {
      const data = await listOutboundScans({ page: 1, page_size: 100, today_only: true })
      setRecentRecords(data.items || [])
    } finally {
      setLoading(false)
    }
  }

  const processQueue = useCallback(async () => {
    if (processingRef.current) return
    processingRef.current = true
    setProcessing(true)
    while (queueRef.current.length) {
      const item = queueRef.current.shift()!
      setQueueSize(queueRef.current.length)
      try {
        const data = await createOutboundScan(item)
        const record = data.record
        setLastResult({ result: record.result || 'error', tracking_number: record.tracking_number || '' })
        playFeedback(record.result)
        setRecentRecords((records) => [record, ...records].slice(0, 200))
        await loadStats()
      } catch (e) {
        const error = e as { response?: { data?: { detail?: string } }; message?: string }
        const fallback: OutboundScanRecordDto = {
          id: -Date.now(),
          tracking_number: item.tracking_number,
          raw_input: item.raw_input,
          order_id: null,
          platform: '',
          shop_name: '',
          platform_order_no: '',
          posting_number: '',
          order_status: '',
          platform_status: '',
          result: 'error',
          message: error.response?.data?.detail || error.message || '扫码记录失败',
          scanned_by: '',
          scanned_at: new Date().toISOString(),
          created_at: new Date().toISOString()
        }
        setLastResult({ result: fallback.result, tracking_number: fallback.tracking_number })
        setRecentRecords((records) => [fallback, ...records].slice(0, 200))
        playFeedback('error')
        message.error(fallback.message)
      } finally {
        focusScanInput()
      }
    }
    processingRef.current = false
    setProcessing(false)
  }, [focusScanInput, message])

  const enqueueScan = useCallback(
    (rawValue?: string) => {
      const raw = String(rawValue ?? scanValueRef.current)
      const tracking = raw.trim()
      setScanValue('')
      scanValueRef.current = ''
      if (!tracking) {
        focusScanInput()
        return
      }
      setScanStarted(true)
      unlockAudio()
      queueRef.current.push({ tracking_number: tracking, raw_input: raw })
      setQueueSize(queueRef.current.length)
      focusScanInput()
      void processQueue()
    },
    [focusScanInput, processQueue]
  )

  function startScan() {
    setScanStarted(true)
    unlockAudio()
    focusScanInput()
  }

  function handleInputBlur() {
    if (!scanStarted) return
    if (focusTimerRef.current) window.clearTimeout(focusTimerRef.current)
    focusTimerRef.current = window.setTimeout(focusScanInput, 80)
  }

  function isScanInputActive() {
    const input = inputRef.current?.input
    return !!input && document.activeElement === input
  }

  function shouldIgnoreGlobalKey(event: KeyboardEvent) {
    return event.ctrlKey || event.altKey || event.metaKey || event.isComposing
  }

  useEffect(() => {
    function handleGlobalKeydown(event: KeyboardEvent) {
      if (isScanInputActive() || shouldIgnoreGlobalKey(event)) return
      if (!scanStarted) {
        setScanStarted(true)
        unlockAudio()
      }
      if (event.key === 'Enter') {
        event.preventDefault()
        enqueueScan()
        return
      }
      if (event.key === 'Backspace') {
        event.preventDefault()
        const next = scanValueRef.current.slice(0, -1)
        scanValueRef.current = next
        setScanValue(next)
        focusScanInput()
        return
      }
      if (event.key.length === 1) {
        event.preventDefault()
        const next = scanValueRef.current + event.key
        scanValueRef.current = next
        setScanValue(next)
        focusScanInput()
      }
    }
    window.addEventListener('keydown', handleGlobalKeydown, true)
    return () => window.removeEventListener('keydown', handleGlobalKeydown, true)
  }, [enqueueScan, focusScanInput, scanStarted])

  useEffect(() => {
    preloadScanSounds()
    void Promise.all([loadStats(), loadRecent()])
    focusScanInput()
    return () => {
      if (focusTimerRef.current) window.clearTimeout(focusTimerRef.current)
    }
  }, [focusScanInput])

  const columns = useMemo<ColumnsType<OutboundScanRecordDto>>(
    () => [
      {
        title: '扫码时间',
        dataIndex: 'scanned_at',
        width: 92,
        render: (value) => (value ? dayjs(value).format('HH:mm:ss') : '-')
      },
      { title: '货运单号', dataIndex: 'tracking_number', width: 160, ellipsis: true },
      {
        title: '结果',
        dataIndex: 'result',
        width: 82,
        render: (value) => <Tag color={resultColor(value)}>{resultLabel(value)}</Tag>
      },
      { title: '平台', dataIndex: 'platform', width: 90 },
      { title: '店铺', dataIndex: 'shop_name', width: 130, ellipsis: true },
      { title: '订单编号', dataIndex: 'platform_order_no', width: 150, ellipsis: true },
      { title: '订单状态', dataIndex: 'order_status', width: 96 },
      { title: '操作员', dataIndex: 'scanned_by', width: 90 },
      { title: '说明', dataIndex: 'message', width: 170, ellipsis: true }
    ],
    []
  )

  return (
    <div className="scan-page">
      <Card styles={{ body: { padding: '12px 16px' } }}>
        <div className="scan-page__head">
          <h2>扫码出库</h2>
          <Space>
            <Button icon={<ProfileOutlined />} onClick={() => navigate('/outbound-scans')}>
              扫码记录
            </Button>
            <Tooltip title="聚焦扫码输入">
              <Button type="primary" shape="circle" icon={<AimOutlined />} onClick={startScan} />
            </Tooltip>
          </Space>
        </div>

        <section className={`scan-console is-${lastResult.result}`}>
          <div className="scan-input-panel">
            <h3>请扫描货运单号</h3>
            <Input
              ref={inputRef}
              className="scan-input"
              size="large"
              value={scanValue}
              placeholder="扫码枪输入后自动提交"
              autoComplete="off"
              onChange={(event) => {
                scanValueRef.current = event.target.value
                setScanValue(event.target.value)
              }}
              onPressEnter={() => enqueueScan()}
              onBlur={handleInputBlur}
            />
            <div className="scan-meta">
              <span>最近货运单号：{lastResult.tracking_number || '-'}</span>
              <span>等待处理：{pendingCount}</span>
            </div>
          </div>

          <div className="scan-stats-grid">
            <div className="scan-stat-tile success">
              <span>今日成功</span>
              <strong>{stats.success}</strong>
            </div>
            <div className="scan-stat-tile warning">
              <span>今日重复</span>
              <strong>{stats.duplicate}</strong>
            </div>
            <div className="scan-stat-tile danger">
              <span>今日失败</span>
              <strong>{failedCount}</strong>
            </div>
            <div className="scan-stat-tile neutral">
              <span>最后扫码</span>
              <strong>{formatStatTime(stats.last_scanned_at)}</strong>
            </div>
          </div>
        </section>
      </Card>

      <Card styles={{ body: { padding: '12px 16px' } }}>
        <div className="scan-records-head">
          <h3>今日扫码记录</h3>
          <span className="muted">仅显示当天数据</span>
        </div>
        <DataTable
          rowKey="id"
          size="small"
          loading={loading}
          dataSource={recentRecords}
          columns={columns}
          tableConfig={SCAN_OUTBOUND_RECORDS_TABLE_CONFIG}
          pagination={false}
          scroll={{ y: 300  }}
        />
      </Card>
    </div>
  )
}
