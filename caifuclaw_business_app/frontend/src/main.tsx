import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider } from 'antd'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import { App } from './App'
import { modalConfig } from './config/modal'
import { startVersionUpdateChecker } from './utils/versionUpdate'
import './styles/global.less'

dayjs.locale('zh-cn')
startVersionUpdateChecker()
ConfigProvider.config({
  holderRender: (children) => <ConfigProvider modal={modalConfig}>{children}</ConfigProvider>
})

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
