/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { useEffect, useMemo, useState } from 'react'
import { ConfigProvider, App as AntApp, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { AppRoutes } from '@/router'
import { onRequestPending } from '@/api/http'
import { modalConfig } from '@/config/modal'
import { useAppStore } from '@/stores/app'

export function App() {
  const componentSize = useAppStore((s) => s.componentSize)
  const [loading, setLoading] = useState(false)

  useEffect(() => onRequestPending(setLoading), [])

  const themeConfig = useMemo(
    () => ({
      algorithm: theme.defaultAlgorithm,
      token: {
        colorPrimary: '#1677ff',
        borderRadius: 6,
        fontSize: 14
      },
      components: {
        Table: { borderColor: 'transparent' }
      }
    }),
    []
  )
  return (
    <ConfigProvider locale={zhCN} theme={themeConfig} componentSize={componentSize} modal={modalConfig}>
      <AntApp>
        <div className={`app-loading-bar${loading ? ' active' : ''}`}>
          <div className="app-loading-bar__track" />
        </div>
        <AppRoutes />
      </AntApp>
    </ConfigProvider>
  )
}
