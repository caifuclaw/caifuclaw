import { lazy, Suspense, type ReactNode } from 'react'
import { Redirect, Route, Switch } from 'wouter'
import { Spin } from 'antd'
import { BasicLayout } from '@/layouts/BasicLayout'
import { BlankLayout } from '@/layouts/BlankLayout'
import { AuthGuard } from '@/router/AuthGuard'

const Login = lazy(() => import('@/pages/Login/Login').then((module) => ({ default: module.Login })))
const Dashboard = lazy(() => import('@/pages/Dashboard/Dashboard').then((module) => ({ default: module.Dashboard })))
const OperationsDailyReport = lazy(() =>
  import('@/pages/OperationsDailyReport/OperationsDailyReport').then((module) => ({ default: module.OperationsDailyReport }))
)
const AiImageProcessing = lazy(() =>
  import('@/pages/AiImageProcessing/AiImageProcessing').then((module) => ({ default: module.AiImageProcessing }))
)
const TextTranslation = lazy(() =>
  import('@/pages/TextTranslation/TextTranslation').then((module) => ({ default: module.TextTranslation }))
)
const TrafficAnalytics = lazy(() =>
  import('@/pages/TrafficAnalytics/TrafficAnalytics').then((module) => ({ default: module.TrafficAnalytics }))
)
const PlatformProductCatalog = lazy(() =>
  import('@/pages/PlatformProductCatalog/PlatformProductCatalog').then((module) => ({ default: module.PlatformProductCatalog }))
)
const TrafficSyncStatus = lazy(() =>
  import('@/pages/TrafficSyncStatus/TrafficSyncStatus').then((module) => ({ default: module.TrafficSyncStatus }))
)
const Orders = lazy(() => import('@/pages/Orders/Orders').then((module) => ({ default: module.Orders })))
const OrderSummary = lazy(() => import('@/pages/OrderSummary/OrderSummary').then((module) => ({ default: module.OrderSummary })))
const PurchaseOrders = lazy(() => import('@/pages/PurchaseOrders/PurchaseOrders').then((module) => ({ default: module.PurchaseOrders })))
const PurchaseDetails = lazy(() => import('@/pages/PurchaseDetails/PurchaseDetails').then((module) => ({ default: module.PurchaseDetails })))
const ScanOutbound = lazy(() => import('@/pages/ScanOutbound/ScanOutbound').then((module) => ({ default: module.ScanOutbound })))
const OutboundScans = lazy(() => import('@/pages/OutboundScans/OutboundScans').then((module) => ({ default: module.OutboundScans })))
const Inventory = lazy(() => import('@/pages/Inventory/Inventory').then((module) => ({ default: module.Inventory })))
const LogisticsAuthorizations = lazy(() =>
  import('@/pages/LogisticsAuthorizations/LogisticsAuthorizations').then((module) => ({ default: module.LogisticsAuthorizations }))
)
const LogisticsRules = lazy(() =>
  import('@/pages/LogisticsRules/LogisticsRules').then((module) => ({ default: module.LogisticsRules }))
)
const Products = lazy(() => import('@/pages/Products/Products').then((module) => ({ default: module.Products })))
const Shops = lazy(() => import('@/pages/Shops/Shops').then((module) => ({ default: module.Shops })))
const SystemSettings = lazy(() => import('@/pages/SystemSettings/SystemSettings').then((module) => ({ default: module.SystemSettings })))
const ExchangeRates = lazy(() => import('@/pages/ExchangeRates/ExchangeRates').then((module) => ({ default: module.ExchangeRates })))
const ScheduledTaskLogs = lazy(() =>
  import('@/pages/ScheduledTaskLogs/ScheduledTaskLogs').then((module) => ({ default: module.ScheduledTaskLogs }))
)
const Users = lazy(() => import('@/pages/Users/Users').then((module) => ({ default: module.Users })))
const Permissions = lazy(() => import('@/pages/Permissions/Permissions').then((module) => ({ default: module.Permissions })))
const SyncApiLogs = lazy(() => import('@/pages/SyncApiLogs/SyncApiLogs').then((module) => ({ default: module.SyncApiLogs })))
const PrintPreview = lazy(() => import('@/pages/PrintPreview/PrintPreview').then((module) => ({ default: module.PrintPreview })))
const Placeholder = lazy(() => import('@/pages/Placeholder/Placeholder').then((module) => ({ default: module.Placeholder })))

function RouteSuspense({ children }: { children: ReactNode }) {
  return (
    <Suspense
      fallback={
        <div style={{ display: 'grid', minHeight: 240, placeItems: 'center' }}>
          <Spin />
        </div>
      }
    >
      {children}
    </Suspense>
  )
}

function routeElement(children: ReactNode) {
  return <RouteSuspense>{children}</RouteSuspense>
}

const protectedRoutes: Array<[string, ReactNode]> = [
  ['/dashboard', <Dashboard />],
  ['/operations-daily-report', <OperationsDailyReport />],
  ['/ai-image-processing', <AiImageProcessing />],
  ['/text-translation', <TextTranslation />],
  ['/traffic-analytics', <TrafficAnalytics />],
  ['/platform-product-catalog', <PlatformProductCatalog />],
  ['/traffic-sync-status', <TrafficSyncStatus />],
  ['/orders', <Orders />],
  ['/order-summary', <OrderSummary />],
  ['/purchase-orders', <PurchaseOrders />],
  ['/purchase-details', <PurchaseDetails />],
  ['/scan-outbound', <ScanOutbound />],
  ['/outbound-scans', <OutboundScans />],
  ['/inventory', <Inventory />],
  ['/logistics-authorizations', <LogisticsAuthorizations />],
  ['/logistics-rules', <LogisticsRules />],
  ['/products', <Products />],
  ['/shops', <Shops />],
  ['/system-settings', <SystemSettings />],
  ['/exchange-rates', <ExchangeRates />],
  ['/scheduled-task-logs', <ScheduledTaskLogs />],
  ['/users', <Users />],
  ['/permissions', <Permissions />],
  ['/sync-api-logs', <SyncApiLogs />]
]

function ProtectedPage({ children }: { children: ReactNode }) {
  return (
    <AuthGuard>
      <BasicLayout>{routeElement(children)}</BasicLayout>
    </AuthGuard>
  )
}

export function AppRoutes() {
  return (
    <Switch>
      <Route path="/">
        <Redirect to="/dashboard" replace />
      </Route>
      <Route path="/login">
        <BlankLayout>{routeElement(<Login />)}</BlankLayout>
      </Route>
      <Route path="/print-preview">
        <AuthGuard>
          <BlankLayout>{routeElement(<PrintPreview />)}</BlankLayout>
        </AuthGuard>
      </Route>
      <Route path="/logistics-authorizations/:id">
        <Redirect to="/logistics-authorizations" replace />
      </Route>
      {protectedRoutes.map(([path, element]) => (
        <Route key={path} path={path}>
          <ProtectedPage>{element}</ProtectedPage>
        </Route>
      ))}
      <Route>{routeElement(<Placeholder title="页面不存在" />)}</Route>
    </Switch>
  )
}
