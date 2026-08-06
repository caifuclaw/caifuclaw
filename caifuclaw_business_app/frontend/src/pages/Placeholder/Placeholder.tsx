/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { Empty } from 'antd'

export function Placeholder({ title = '页面迁移中' }: { title?: string }) {
  return (
    <div className="page-card">
      <Empty description={title} />
    </div>
  )
}
