/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ArrowRightOutlined, ReloadOutlined } from '@ant-design/icons'
import { Alert, Button, Empty, Select, Skeleton, Space, Table, Tag, Tooltip } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  listOrderOperationLogs,
  type OrderOperationLogDto,
  type OrderOperationLogListParams
} from '@/api/orders'
import { formatTime } from '@/utils/format'
import {
  groupConsecutiveOrderOperationLogs,
  type GroupedOrderOperationLog
} from '@/utils/groupOrderOperationLogs'
import './OrderOperationLogTable.less'

interface OrderOperationLogTableProps {
  orderId: number
}

const PAGE_SIZE = 50

const SOURCE_OPTIONS = [
  { value: 'system', label: '系统任务' },
  { value: 'manual', label: '人工操作' },
  { value: 'history', label: '历史补充' }
]

const OPERATION_OPTIONS = [
  { value: 'order_sync', label: '订单同步' },
  { value: 'sync_logistics', label: '同步物流信息' },
  { value: 'print_label', label: '打印面单' },
  { value: 'to_printing', label: '转入待打印' },
  { value: 'to_picking', label: '转入配货中' },
  { value: 'mark_shipped', label: '标记发货' },
  { value: 'outbound_scan', label: '扫码出库' }
]

function sourceText(source: string): string {
  if (source === 'system') return '系统'
  if (source === 'manual') return '人工'
  if (source === 'history') return '历史'
  return source || '-'
}

function resultTag(result: string) {
  if (result === 'failed') return <Tag color="error">失败</Tag>
  if (result === 'warning') return <Tag color="warning">注意</Tag>
  if (result === 'unchanged') return <Tag>无变化</Tag>
  return <Tag color="success">成功</Tag>
}

export function OrderOperationLogTable({ orderId }: OrderOperationLogTableProps) {
  const requestSequence = useRef(0)
  const [logs, setLogs] = useState<OrderOperationLogDto[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState('')
  const [hasMore, setHasMore] = useState(false)
  const [nextBeforeId, setNextBeforeId] = useState<number | null>(null)
  const [source, setSource] = useState<string>()
  const [operationType, setOperationType] = useState<string>()

  const loadLogs = useCallback(
    async (append = false) => {
      const sequence = ++requestSequence.current
      append ? setLoadingMore(true) : setLoading(true)
      setError('')
      try {
        const params: OrderOperationLogListParams = {
          page_size: PAGE_SIZE,
          source,
          operation_type: operationType,
          before_id: append ? nextBeforeId || undefined : undefined
        }
        const response = await listOrderOperationLogs(orderId, params)
        if (sequence !== requestSequence.current) return
        setLogs((current) => (append ? [...current, ...(response.items || [])] : response.items || []))
        setHasMore(Boolean(response.has_more))
        setNextBeforeId(response.next_before_id || null)
      } catch (requestError) {
        if (sequence !== requestSequence.current) return
        setError(requestError instanceof Error ? requestError.message : '操作日志加载失败')
      } finally {
        if (sequence === requestSequence.current) {
          setLoading(false)
          setLoadingMore(false)
        }
      }
    },
    [nextBeforeId, operationType, orderId, source]
  )

  useEffect(() => {
    setLogs([])
    setNextBeforeId(null)
    loadLogs(false)
  }, [operationType, orderId, source])

  const groupedLogs = useMemo(() => groupConsecutiveOrderOperationLogs(logs), [logs])

  const columns: ColumnsType<GroupedOrderOperationLog> = [
    {
      title: '操作',
      dataIndex: 'operation_attribute',
      width: 170,
      render: (value, row) => (
        <div className="order-operation-log__operation">
          <strong>{value || row.operation_type || '-'}</strong>
          <span>
            {sourceText(row.source)}
            {row.repeated_logs.length > 1 ? <Tag>重复 {row.repeated_logs.length} 次</Tag> : null}
          </span>
        </div>
      )
    },
    {
      title: '结果',
      dataIndex: 'result',
      width: 78,
      render: (value) => resultTag(value)
    },
    {
      title: '记录内容',
      dataIndex: 'description',
      render: (value, row) => (
        <div className="order-operation-log__content">
          <div>{value || '-'}</div>
          {row.changes?.length ? (
            <div className="order-operation-log__changes">
              {row.changes.map((change, index) => (
                <span key={`${change.field}-${index}`}>
                  <em>{change.label || change.field}</em>
                  <code>{change.before || '-'}</code>
                  <ArrowRightOutlined aria-hidden="true" />
                  <code>{change.after || '-'}</code>
                </span>
              ))}
            </div>
          ) : null}
          {row.task_run_id || row.sync_job_log_id ? (
            <small>
              {row.task_run_id ? `任务运行 #${row.task_run_id}` : ''}
              {row.task_run_id && row.sync_job_log_id ? ' · ' : ''}
              {row.sync_job_log_id ? `同步任务 #${row.sync_job_log_id}` : ''}
            </small>
          ) : null}
        </div>
      )
    },
    {
      title: '操作员',
      dataIndex: 'operator',
      width: 130,
      render: (value, row) => value || (row.source === 'system' ? '系统任务' : '-')
    },
    {
      title: '操作时间',
      dataIndex: 'operated_at',
      width: 180,
      render: (value) => <span className="order-operation-log__time">{formatTime(value, true)}</span>
    }
  ]

  return (
    <div className="order-operation-log">
      <div className="order-operation-log__toolbar">
        <Space size={8} wrap>
          <Select
            allowClear
            aria-label="筛选日志操作"
            placeholder="全部操作"
            options={OPERATION_OPTIONS}
            value={operationType}
            onChange={setOperationType}
            className="order-operation-log__filter"
          />
          <Select
            allowClear
            aria-label="筛选日志来源"
            placeholder="全部来源"
            options={SOURCE_OPTIONS}
            value={source}
            onChange={setSource}
            className="order-operation-log__filter"
          />
        </Space>
        <Tooltip title="刷新日志">
          <Button
            aria-label="刷新操作日志"
            icon={<ReloadOutlined />}
            loading={loading && logs.length > 0}
            onClick={() => loadLogs(false)}
          />
        </Tooltip>
      </div>

      {error ? <Alert type="error" showIcon message="操作日志加载失败" description={error} /> : null}

      {loading && !logs.length ? (
        <Skeleton active title={false} paragraph={{ rows: 6, width: ['100%', '96%', '100%', '92%', '98%', '88%'] }} />
      ) : (
        <Table
          className="order-operation-log__table"
          rowKey="id"
          size="small"
          dataSource={groupedLogs}
          columns={columns}
          pagination={false}
          scroll={{ x: 900 }}
          tableLayout="fixed"
          expandable={{
            rowExpandable: (row) => row.repeated_logs.length > 1,
            expandedRowRender: (row) => (
              <div className="order-operation-log__repeats" aria-label={`${row.repeated_logs.length} 次操作记录`}>
                {row.repeated_logs.map((repeatedLog, index) => (
                  <div key={repeatedLog.id}>
                    <span>{index === 0 ? '最近' : `第 ${row.repeated_logs.length - index} 次`}</span>
                    <time>{formatTime(repeatedLog.operated_at, true)}</time>
                    <span>{repeatedLog.operator || sourceText(repeatedLog.source)}</span>
                  </div>
                ))}
              </div>
            )
          }}
          locale={{
            emptyText: (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无操作日志">
                <Button onClick={() => loadLogs(false)}>刷新日志</Button>
              </Empty>
            )
          }}
        />
      )}

      {hasMore ? (
        <div className="order-operation-log__footer">
          <Button loading={loadingMore} onClick={() => loadLogs(true)}>
            加载更早日志
          </Button>
        </div>
      ) : null}
      <span className="order-operation-log__count" aria-live="polite">
        已加载 {logs.length} 条{groupedLogs.length !== logs.length ? `，合并显示 ${groupedLogs.length} 项` : ''}
      </span>
    </div>
  )
}
