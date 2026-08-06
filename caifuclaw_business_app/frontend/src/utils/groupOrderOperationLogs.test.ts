/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { describe, expect, it } from 'vitest'
import type { OrderOperationLogDto } from '@/api/orders'
import { groupConsecutiveOrderOperationLogs } from './groupOrderOperationLogs'

function log(id: number, description: string): OrderOperationLogDto {
  return {
    id,
    operation_type: 'print_label',
    operation_attribute: '打印面单',
    description,
    operator: 'admin',
    source: 'manual',
    result: 'success',
    changes: [],
    operated_at: `2026-06-09T13:${id}:00`,
    created_at: `2026-06-09T13:${id}:00`
  }
}

describe('groupConsecutiveOrderOperationLogs', () => {
  it('groups consecutive identical events and preserves every timestamp', () => {
    const grouped = groupConsecutiveOrderOperationLogs([log(3, '已打印'), log(2, '已打印'), log(1, '已打印')])

    expect(grouped).toHaveLength(1)
    expect(grouped[0].repeated_logs.map((item) => item.id)).toEqual([3, 2, 1])
  })

  it('does not merge events separated by another audit event', () => {
    const grouped = groupConsecutiveOrderOperationLogs([log(3, '已打印'), log(2, '状态已更新'), log(1, '已打印')])

    expect(grouped).toHaveLength(3)
  })

  it('does not merge events with different task references', () => {
    const first = { ...log(2, '已打印'), task_run_id: 10 }
    const second = { ...log(1, '已打印'), task_run_id: 11 }

    expect(groupConsecutiveOrderOperationLogs([first, second])).toHaveLength(2)
  })
})
