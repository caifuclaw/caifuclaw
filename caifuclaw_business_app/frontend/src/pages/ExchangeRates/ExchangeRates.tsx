/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { useEffect, useMemo, useState } from 'react'
import { DeleteOutlined, PlusOutlined, ReloadOutlined, SyncOutlined } from '@ant-design/icons'
import { App, Button, DatePicker, Form, Modal, Select, Space, Tag, Tooltip } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import type { Dayjs } from 'dayjs'
import { DataTable } from '@/components/DataTable'
import {
  listExchangeRates,
  listExchangeRateCurrencySettings,
  syncExchangeRates,
  updateExchangeRateCurrencySettings,
  type ExchangeRateCurrencySettingDto,
  type ExchangeRateCurrencySettingPayload,
  type ExchangeRateDto,
  type ExchangeRateQueryParams
} from '@/api/system'
import { formatTime } from '@/utils/format'
import { FIXED_CURRENCY_OPTIONS } from './currencyOptions'
import './ExchangeRates.less'

interface FilterValues {
  rate_date?: Dayjs
  currency_code?: string
}

interface SettingRow {
  key: string
  currency_code: string
  currency_name: string
}

function createEmptySettingRow(index: number): SettingRow {
  return {
    key: `new-${Date.now()}-${index}`,
    currency_code: '',
    currency_name: ''
  }
}

function formatRate(value?: string | number | null) {
  if (value == null || value === '') return '-'
  const num = Number(value)
  if (!Number.isFinite(num)) return String(value)
  return num.toLocaleString('zh-CN', {
    minimumFractionDigits: 4,
    maximumFractionDigits: 8
  })
}

export function ExchangeRates() {
  const { message } = App.useApp()
  const [form] = Form.useForm<FilterValues>()
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [rows, setRows] = useState<ExchangeRateDto[]>([])
  const [currencies, setCurrencies] = useState<string[]>([])
  const [settingOpen, setSettingOpen] = useState(false)
  const [savingSettings, setSavingSettings] = useState(false)
  const [settingRows, setSettingRows] = useState<SettingRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const filters = Form.useWatch([], form)

  const queryParams = useMemo<ExchangeRateQueryParams>(() => {
    const values = form.getFieldsValue()
    return {
      rate_date: values.rate_date?.format('YYYY-MM-DD'),
      currency_code: values.currency_code || undefined,
      page,
      page_size: pageSize
    }
  }, [form, filters, page, pageSize])

  const fixedCurrencySelectOptions = useMemo(
    () =>
      FIXED_CURRENCY_OPTIONS.map((item) => ({
        value: item.code,
        label: `${item.code} ${item.name}`,
        searchText: `${item.code} ${item.name}`.toLowerCase()
      })),
    []
  )

  const fixedCurrencyNameMap = useMemo(
    () => new Map(FIXED_CURRENCY_OPTIONS.map((item) => [item.code, item.name])),
    []
  )

  async function load() {
    setLoading(true)
    try {
      const data = await listExchangeRates(queryParams)
      setRows(data.items || [])
      setTotal(data.total || 0)
      setCurrencies(data.currencies || [])
    } finally {
      setLoading(false)
    }
  }

  async function loadSettings() {
    const data = await listExchangeRateCurrencySettings()
    setSettingRows(
      (data || [])
        .filter((item) => item.enabled)
        .map((item, index) => ({
          key: `${item.currency_code}-${index}`,
          currency_code: item.currency_code,
          currency_name: item.currency_name || ''
        }))
    )
  }

  useEffect(() => {
    load()
  }, [queryParams])

  useEffect(() => {
    loadSettings()
  }, [])

  async function runSync() {
    setSyncing(true)
    try {
      const result = await syncExchangeRates()
      message.success(result.message || `已同步 ${result.synced || 0} 条汇率`)
      setPage(1)
      await load()
    } finally {
      setSyncing(false)
    }
  }

  const currencyOptions = currencies.map((currency) => ({ value: currency, label: currency }))

  async function openSettings() {
    await loadSettings()
    setSettingOpen(true)
  }

  function addSettingRow() {
    setSettingRows((prev) => [...prev, createEmptySettingRow(prev.length)])
  }

  function updateSettingRow(key: string, patch: Partial<SettingRow>) {
    setSettingRows((prev) =>
      prev.map((row) => (row.key === key ? { ...row, ...patch } : row))
    )
  }

  function removeSettingRow(key: string) {
    setSettingRows((prev) => prev.filter((row) => row.key !== key))
  }

  function selectSettingCurrency(key: string, code?: string) {
    const currencyCode = code || ''
    setSettingRows((prev) => {
      const rowIndex = prev.findIndex((row) => row.key === key)
      const next = prev.map((row) =>
        row.key === key
          ? {
              ...row,
              currency_code: currencyCode,
              currency_name: currencyCode ? fixedCurrencyNameMap.get(currencyCode) || '' : ''
            }
          : row
      )

      if (currencyCode && rowIndex === prev.length - 1) {
        next.push(createEmptySettingRow(next.length))
      }

      return next
    })
  }

  async function saveSettings() {
    const normalized: ExchangeRateCurrencySettingPayload[] = []
    const seen = new Set<string>()
    for (const row of settingRows) {
      const code = row.currency_code.trim().toUpperCase()
      const name = (fixedCurrencyNameMap.get(code) || row.currency_name).trim()
      if (!code && !name) continue
      if (!code) {
        message.warning('请填写货币代码')
        return
      }
      if (code === 'CNY') {
        message.warning('本位币 CNY 不需要设置')
        return
      }
      if (seen.has(code)) {
        message.warning(`货币代码 ${code} 重复`)
        return
      }
      seen.add(code)
      normalized.push({ currency_code: code, currency_name: name })
    }

    setSavingSettings(true)
    try {
      const data = await updateExchangeRateCurrencySettings(normalized)
      setSettingRows(
        (data || []).map((item, index) => ({
          key: `${item.currency_code}-${index}`,
          currency_code: item.currency_code,
          currency_name: item.currency_name || ''
        }))
      )
      setSettingOpen(false)
      message.success(normalized.length ? '币别设置已保存' : '已清空设置，将同步全部币别')
    } finally {
      setSavingSettings(false)
    }
  }

  const columns: ColumnsType<ExchangeRateDto> = [
    { title: '日期', dataIndex: 'rate_date', width: 120 },
    {
      title: '货币代码',
      dataIndex: 'currency_code',
      width: 120,
      render: (value) => <span className="exchange-rate-code">{value || '-'}</span>
    },
    { title: '货币名称', dataIndex: 'currency_name', width: 180, render: (value) => value || '-' },
    {
      title: '汇率',
      dataIndex: 'rate',
      width: 160,
      align: 'right',
      render: (value) => <span className="exchange-rate-value">{formatRate(value)}</span>
    },
    { title: '源更新时间', dataIndex: 'source_updated_at', width: 180, render: (value) => formatTime(value, true) },
    { title: '同步时间', dataIndex: 'synced_at', width: 180, render: (value) => formatTime(value, true) },
    { title: '本地更新时间', dataIndex: 'updated_at', width: 180, render: (value) => formatTime(value, true) }
  ]

  const settingColumns: ColumnsType<SettingRow> = [
    {
      title: '货币代码',
      dataIndex: 'currency_code',
      width: 180,
      render: (_, row) => (
        <Select
          allowClear
          showSearch
          value={row.currency_code || undefined}
          placeholder="请选择币别"
          options={fixedCurrencySelectOptions}
          optionFilterProp="searchText"
          filterOption={(input, option) => String(option?.searchText || '').includes(input.trim().toLowerCase())}
          onChange={(value) => selectSettingCurrency(row.key, value)}
          style={{ width: '100%' }}
        />
      )
    },
    {
      title: '货币名称',
      dataIndex: 'currency_name',
      render: (_, row) => (
        <div className="exchange-rate-setting-name-cell">
          <span className="exchange-rate-setting-name-text">{row.currency_name || '-'}</span>
          <Tooltip title="删除">
            <Button
              aria-label="删除币别"
              danger
              type="text"
              icon={<DeleteOutlined />}
              onClick={() => removeSettingRow(row.key)}
            />
          </Tooltip>
        </div>
      )
    }
  ]

  const pagination: TablePaginationConfig = {
    current: page,
    pageSize,
    total,
    pageSizeOptions: [50, 100, 200],
    showSizeChanger: true,
    showTotal: (value) => `共 ${value} 条`,
    onChange: (nextPage, nextPageSize) => {
      setPage(nextPage)
      setPageSize(nextPageSize)
    }
  }

  return (
    <div className="page-card">
      <div className="orders-header">
        <h2>汇率管理</h2>
      </div>

      <div className="exchange-rate-toolbar">
        <Form
          form={form}
          layout="inline"
          className="orders-filter exchange-rate-toolbar__filters"
          onFinish={() => {
            setPage(1)
            load()
          }}
        >
          <Form.Item label="日期" name="rate_date">
            <DatePicker allowClear format="YYYY-MM-DD" style={{ width: 160 }} />
          </Form.Item>
          <Form.Item label="币别" name="currency_code">
            <Select allowClear showSearch placeholder="全部" style={{ width: 140 }} options={currencyOptions} />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                查询
              </Button>
              <Button
                onClick={() => {
                  form.resetFields()
                  setPage(1)
                }}
              >
                重置
              </Button>
            </Space>
          </Form.Item>
        </Form>

        <Space className="exchange-rate-toolbar__actions">
          <Button icon={<ReloadOutlined />} onClick={load}>
            刷新
          </Button>
          <Button onClick={openSettings}>
            币别设置
          </Button>
          <Button type="primary" icon={<SyncOutlined />} loading={syncing} onClick={runSync}>
            同步
          </Button>
        </Space>
      </div>

      <div className="exchange-rate-summary">
        <Tag color="blue">CNY</Tag>
        <span>汇率口径：1 外币 = N 人民币</span>
      </div>

      <DataTable rowKey="id" loading={loading} dataSource={rows} columns={columns} pagination={pagination} />

      <Modal
        open={settingOpen}
        title="币别设置"
        okText="保存"
        cancelText="取消"
        width={680}
        confirmLoading={savingSettings}
        onOk={saveSettings}
        onCancel={() => setSettingOpen(false)}
        destroyOnClose
      >
        <div className="exchange-rate-setting-note">
          未选择任何币别时，同步全部币别；选择后只同步所选币别。
        </div>
        <div className="exchange-rate-setting-toolbar">
          <Button icon={<PlusOutlined />} onClick={addSettingRow}>
            新增币别
          </Button>
        </div>
        <DataTable
          className="exchange-rate-setting-table"
          rowKey="key"
          size="small"
          pagination={false}
          dataSource={settingRows}
          columns={settingColumns}
          locale={{ emptyText: '未设置时同步全部币别' }}
        />
      </Modal>
    </div>
  )
}
