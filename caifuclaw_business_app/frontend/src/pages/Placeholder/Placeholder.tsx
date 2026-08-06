import { Empty } from 'antd'

export function Placeholder({ title = '页面迁移中' }: { title?: string }) {
  return (
    <div className="page-card">
      <Empty description={title} />
    </div>
  )
}
