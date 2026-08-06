/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import type { OrderOperationLogDto } from '@/api/orders'

export interface GroupedOrderOperationLog extends OrderOperationLogDto {
  repeated_logs: OrderOperationLogDto[]
}

function operationLogSignature(log: OrderOperationLogDto): string {
  return JSON.stringify([
    log.operation_type,
    log.operation_attribute,
    log.description,
    log.operator,
    log.source,
    log.result,
    log.changes || [],
    log.task_run_id || null,
    log.sync_job_log_id || null
  ])
}

export function groupConsecutiveOrderOperationLogs(logs: OrderOperationLogDto[]): GroupedOrderOperationLog[] {
  const grouped: GroupedOrderOperationLog[] = []

  for (const log of logs) {
    const previous = grouped[grouped.length - 1]
    if (previous && operationLogSignature(previous) === operationLogSignature(log)) {
      previous.repeated_logs.push(log)
      continue
    }
    grouped.push({ ...log, repeated_logs: [log] })
  }

  return grouped
}
