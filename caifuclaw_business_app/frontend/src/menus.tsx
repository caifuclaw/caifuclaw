import type { ReactNode } from 'react'
import {
  AppstoreOutlined,
  AreaChartOutlined,
  BarChartOutlined,
  DatabaseOutlined,
  DashboardOutlined,
  FileTextOutlined,
  PictureOutlined,
  RobotOutlined,
  ScanOutlined,
  SettingOutlined,
  ShoppingCartOutlined,
  TranslationOutlined,
  TruckOutlined
} from '@ant-design/icons'

export interface MenuItem {
  code: string
  path: string
  routeName?: string
  title: string
  icon?: ReactNode
  hideInMenu?: boolean
  children?: MenuItem[]
}

export const menus: MenuItem[] = [
  {
    code: 'dashboard',
    path: '/dashboard',
    routeName: 'Dashboard',
    title: '工作台',
    icon: <DashboardOutlined />
  },
  {
    code: 'traffic-analytics',
    path: '/traffic-analytics',
    routeName: 'TrafficAnalytics',
    title: '流量分析',
    icon: <AreaChartOutlined />
  },
  {
    code: 'group-order-ops',
    path: '/_group/order-ops',
    title: '订单管理',
    icon: <ShoppingCartOutlined />,
    children: [
      { code: 'orders', path: '/orders', routeName: 'Orders', title: '订单列表' },
      { code: 'order-summary', path: '/order-summary', routeName: 'OrderSummary', title: '订单明细' }
    ]
  },
  {
    code: 'group-purchase',
    path: '/_group/purchase',
    title: '采购管理',
    icon: <AppstoreOutlined />,
    children: [
      { code: 'purchase-orders', path: '/purchase-orders', routeName: 'PurchaseOrders', title: '采购单' },
      { code: 'purchase-details', path: '/purchase-details', routeName: 'PurchaseDetails', title: '采购明细' }
    ]
  },
  {
    code: 'group-outbound',
    path: '/_group/outbound',
    title: '库存管理',
    icon: <ScanOutlined />,
    children: [
      { code: 'scan-outbound', path: '/scan-outbound', routeName: 'ScanOutbound', title: '扫码出库' },
      { code: 'outbound-scans', path: '/outbound-scans', routeName: 'OutboundScans', title: '扫码记录' },
      { code: 'inventory', path: '/inventory', routeName: 'Inventory', title: '产品库存' }
    ]
  },
  {
    code: 'group-logistics',
    path: '/_group/logistics',
    title: '物流管理',
    icon: <TruckOutlined />,
    children: [
      { code: 'logistics-rules', path: '/logistics-rules', routeName: 'LogisticsRules', title: '物流规则' },
      { code: 'logistics-authorizations', path: '/logistics-authorizations', routeName: 'LogisticsAuthorizations', title: '物流授权' }
    ]
  },
  {
    code: 'group-operations-analysis',
    path: '/_group/operations-analysis',
    title: '运营分析',
    icon: <BarChartOutlined />,
    children: [
      { code: 'operations-daily-report', path: '/operations-daily-report', routeName: 'OperationsDailyReport', title: '运营日报表' },
      { code: 'platform-product-catalog', path: '/platform-product-catalog', routeName: 'PlatformProductCatalog', title: '平台产品目录' }
    ]
  },
  {
    code: 'group-ai-toolbox',
    path: '/_group/ai-toolbox',
    title: 'AI工具箱',
    icon: <RobotOutlined />,
    children: [
      { code: 'ai-image-processing', path: '/ai-image-processing', routeName: 'AiImageProcessing', title: '图片处理', icon: <PictureOutlined /> },
      { code: 'text-translation', path: '/text-translation', routeName: 'TextTranslation', title: '文字翻译', icon: <TranslationOutlined /> }
    ]
  },
  {
    code: 'group-basic-data',
    path: '/_group/basic-data',
    title: '基础数据',
    icon: <DatabaseOutlined />,
    children: [
      { code: 'products', path: '/products', routeName: 'Products', title: '产品管理' },
      { code: 'exchange-rates', path: '/exchange-rates', routeName: 'ExchangeRates', title: '汇率管理' }
    ]
  },
  {
    code: 'group-config',
    path: '/_group/config',
    title: '系统管理',
    icon: <SettingOutlined />,
    children: [
      { code: 'shops', path: '/shops', routeName: 'Shops', title: '店铺管理' },
      { code: 'users', path: '/users', routeName: 'Users', title: '用户管理' },
      { code: 'permissions', path: '/permissions', routeName: 'Permissions', title: '权限管理' },
      { code: 'system-settings', path: '/system-settings', routeName: 'SystemSettings', title: '系统设置' }
    ]
  },
  {
    code: 'group-logs',
    path: '/_group/logs',
    title: '日志管理',
    icon: <FileTextOutlined />,
    children: [
      {
        code: 'traffic-sync-status',
        path: '/traffic-sync-status',
        routeName: 'TrafficSyncStatus',
        title: '流量同步状态'
      },
      {
        code: 'scheduled-task-logs',
        path: '/scheduled-task-logs',
        routeName: 'ScheduledTaskLogs',
        title: '定时任务日志'
      },
      { code: 'sync-api-logs', path: '/sync-api-logs', routeName: 'SyncApiLogs', title: '平台接口日志' }
    ]
  }
]

export function flattenMenus(items: MenuItem[] = menus, acc: MenuItem[] = []): MenuItem[] {
  for (const item of items) {
    acc.push(item)
    if (item.children?.length) flattenMenus(item.children, acc)
  }
  return acc
}

export function findMenuByPath(path: string): MenuItem | undefined {
  return flattenMenus().find((item) => item.path === path)
}

export function findParentMenuPaths(path: string, items = menus, parents: string[] = []): string[] {
  for (const item of items) {
    if (item.path === path) return parents
    if (item.children?.length) {
      const found = findParentMenuPaths(path, item.children, [...parents, item.path])
      if (found.length) return found
    }
  }
  return []
}
