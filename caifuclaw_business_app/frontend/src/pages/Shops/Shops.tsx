import { useEffect, useMemo, useRef, useState } from 'react'
import { CheckCircleOutlined, EditOutlined, LinkOutlined, PlusOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import {
  App,
  Button,
  Col,
  Divider,
  Form,
  Input,
  Modal,
  Radio,
  Row,
  Select,
  Space,
  Switch,
  Tag,
  Tooltip
} from 'antd'
import { DataTable } from '@/components/DataTable'
import type { ColumnsType } from 'antd/es/table'
import {
  completeShopOAuth,
  createShop,
  getShopCredentials,
  listPlatforms,
  listShops,
  reauthorizeShop,
  startShopOAuth,
  toggleShopEnabled,
  updateShop,
  updateShopCredentials,
  type PlatformOptionDto,
  type ShopDto,
  type ShopListParams
} from '@/api/shops'
import { formatTime } from '@/utils/format'
import { shouldIgnoreTableRowDoubleClick } from '@/utils/tableInteractions'

type DialogMode = 'create' | 'edit' | 'auth'
type ShopSettings = NonNullable<ShopFormValues['settings']>

interface AuthContext {
  platform: string
  accountId: string
  displayName: string
  enabled: boolean
  settings: ShopSettings
}

interface FilterValues {
  display_name?: string
  platform?: string
  enabled?: boolean
}

interface ShopFormValues {
  platform?: string
  shop_id?: string
  display_name?: string
  enabled?: boolean
  credentials?: Record<string, string>
  settings?: Record<string, string | number | boolean | null | undefined>
  authorization_expires_at?: string
}

const platformFallbacks: PlatformOptionDto[] = [
  { platform: 'ozon', display_name: 'Ozon' },
  { platform: 'wildberries', display_name: 'Wildberries' },
  { platform: 'joom_logistics', display_name: 'Joom' },
  { platform: 'allegro', display_name: 'Allegro' },
  { platform: 'mercadolibre', display_name: 'MercadoLibre' },
  { platform: 'amazon', display_name: 'Amazon' },
  { platform: 'shopee', display_name: 'Shopee' },
  { platform: 'tiktok_shop', display_name: 'TikTok Shop' },
  { platform: 'aliexpress', display_name: 'AliExpress' },
  { platform: 'lazada', display_name: 'Lazada' },
  { platform: 'shopify', display_name: 'Shopify' },
  { platform: 'ebay', display_name: 'eBay' },
  { platform: 'walmart', display_name: 'Walmart' },
  { platform: 'temu', display_name: 'Temu' },
  { platform: 'shein', display_name: 'SHEIN' },
  { platform: 'coupang', display_name: 'Coupang' },
  { platform: 'wayfair', display_name: 'Wayfair' },
  { platform: 'dmsmatrix', display_name: 'DMSMatrix' }
]

function defaultSettings(): NonNullable<ShopFormValues['settings']> {
  return {
    sync_interval_seconds: 1200,
    dry_run_fulfillment: false,
    fbo_fbp_download_mode: 'none',
    download_platform_package_orders: true,
    download_full_orders: true,
    mercado_order_pull_status: 'paid',
    mercado_site: 'CBT',
    mercado_store_type: 'cbt',
    download_overseas_warehouse_orders: false,
    auto_cache_labels: false,
    allegro_carrier_id: ''
  }
}

const booleanSettingDefaults: Record<string, boolean> = {
  dry_run_fulfillment: false,
  download_platform_package_orders: true,
  download_full_orders: true,
  download_overseas_warehouse_orders: false,
  auto_cache_labels: false
}

function normalizeBooleanSetting(value: unknown, fallback: boolean) {
  if (typeof value === 'boolean') return value
  if (typeof value === 'number') return value !== 0
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase()
    if (['true', '1', 'yes', 'y', 'on'].includes(normalized)) return true
    if (['false', '0', 'no', 'n', 'off'].includes(normalized)) return false
  }
  return fallback
}

function normalizeSettings(settings?: Record<string, unknown>): ShopSettings {
  const normalized = { ...defaultSettings(), ...(settings || {}) } as ShopSettings
  Object.entries(booleanSettingDefaults).forEach(([key, fallback]) => {
    normalized[key] = normalizeBooleanSetting(normalized[key], fallback)
  })
  return normalized
}

function platformDefaultSettings(platform?: string): Partial<ShopSettings> {
  const current = canonicalPlatform(platform)
  const defaults: Record<string, Partial<ShopSettings>> = {
    shopify: {
      base_url: 'https://{shop_domain}',
      api_version: '2026-04',
      pull_query: 'fulfillment_status:unfulfilled OR fulfillment_status:partial',
      label_mode: 'unsupported'
    },
    ebay: {
      base_url: 'https://api.ebay.com',
      marketplace_id: 'EBAY_US',
      pull_filter: 'orderfulfillmentstatus:{NOT_STARTED|IN_PROGRESS}',
      label_mode: 'unsupported'
    },
    walmart: {
      base_url: 'https://marketplace.walmartapis.com',
      market: 'us',
      released_only: true,
      auto_acknowledge_released_orders: false,
      label_mode: 'ship_with_walmart_optional'
    },
    temu: {
      base_url: 'https://openapi-b-us.temu.com',
      region: 'US',
      label_mode: 'requires_partner_portal_confirmation'
    },
    shein: {
      base_url: 'https://openapi.sheincorp.com',
      region: 'GLOBAL',
      label_mode: 'requires_shein_fulfill_confirmation'
    },
    coupang: {
      base_url: 'https://api-gateway.coupang.com',
      market: 'KR',
      label_mode: 'unsupported',
      search_by_minute: true
    },
    wayfair: {
      base_url: 'https://api.wayfair.com/v1/graphql',
      graphql_url: 'https://api.wayfair.com/v1/graphql',
      token_url: 'https://sso.auth.wayfair.com/oauth/token',
      label_mode: 'registration_label_url'
    },
    dmsmatrix: {
      base_url: 'https://api.dmsmatrix.net/apis',
      orders_path: '/Order/getOrders',
      orders_method: 'POST',
      updated_since_param: 'OrderDateFrom',
      page_size_param: 'PerPage',
      page_param: 'Page',
      label_path: '/shipments/{shipment_id}/label',
      label_method: 'GET',
      label_format: 'pdf',
      auto_cache_labels: true
    },
    amazon: { base_url: 'https://sellingpartnerapi-na.amazon.com' },
    shopee: { base_url: 'https://partner.shopeemobile.com', region: 'SG' },
    tiktok_shop: { base_url: 'https://open-api.tiktokglobalshop.com', region: 'GLOBAL' },
    aliexpress: { base_url: 'https://api-sg.aliexpress.com/sync', region: 'GLOBAL' },
    lazada: { base_url: 'https://api.lazada.com/rest', region: 'SG' },
    allegro: { base_url: 'https://api.allegro.pl', allegro_carrier_id: '' }
  }
  return defaults[current] || {}
}

function normalizePlatformSettings(platform?: string, settings?: Record<string, unknown>): ShopSettings {
  return normalizeSettings({ ...platformDefaultSettings(platform), ...(settings || {}) })
}

function canonicalPlatform(value?: string) {
  const normalized = `${value || ''}`.trim().toLowerCase()
  if (['joom', 'joomlogistics', 'joom_logistics'].includes(normalized)) return 'joom_logistics'
  if (normalized === 'mercadolibre') return 'mercadolibre'
  if (normalized === 'allegro') return 'allegro'
  if (['tiktok', 'tiktokshop', 'tiktok_shop'].includes(normalized)) return 'tiktok_shop'
  if (normalized === 'ali_express') return 'aliexpress'
  if (normalized === 'shopify_admin') return 'shopify'
  if (normalized === 'ebay_sell') return 'ebay'
  if (normalized === 'walmart_marketplace') return 'walmart'
  if (normalized === 'shein_open') return 'shein'
  if (normalized === 'coupang_openapi') return 'coupang'
  if (normalized === 'wayfair_partner') return 'wayfair'
  if (['dms_matrix', 'dms-matrix', 'dms_matrix_erp', 'dmsmatrix_erp'].includes(normalized)) return 'dmsmatrix'
  return normalized
}

function isOAuthPlatform(platform?: string) {
  return ['joom_logistics', 'allegro', 'mercadolibre'].includes(canonicalPlatform(platform))
}

function isMercadoLibre(platform?: string) {
  return canonicalPlatform(platform) === 'mercadolibre'
}

function mercadoStoreTypeForSite(site?: string) {
  const normalized = `${site || ''}`.trim().toUpperCase()
  return normalized === 'CBT' ? 'cbt' : 'local'
}

function manualCredentialType(platform?: string) {
  const current = canonicalPlatform(platform)
  if (current === 'amazon') return 'oauth2_sigv4'
  if (['shopee', 'tiktok_shop'].includes(current)) return 'oauth2_hmac'
  if (current === 'temu') return 'oauth2_hmac'
  if (['aliexpress', 'lazada'].includes(current)) return 'oauth2_top'
  if (current === 'ebay') return 'oauth2'
  if (current === 'shopify') return 'oauth2_admin_api'
  if (current === 'walmart') return 'oauth2_client_credentials'
  if (['shein', 'coupang'].includes(current)) return 'hmac_openapi'
  if (current === 'wayfair') return 'oauth2_client_credentials_graphql'
  return isOAuthPlatform(current) ? 'oauth2' : 'api_key'
}

function credentialFields(platform?: string) {
  const current = canonicalPlatform(platform)
  const commonAccessToken = { key: 'access_token', label: 'Access Token', password: true }
  const fields: Record<string, Array<{ key: string; label: string; password?: boolean }>> = {
    ozon: [
      { key: 'client_id', label: 'Client ID' },
      { key: 'api_key', label: 'API Key', password: true }
    ],
    wildberries: [{ key: 'api_key', label: 'API Key', password: true }],
    amazon: [
      { key: 'lwa_client_id', label: 'LWA Client ID' },
      { key: 'lwa_client_secret', label: 'LWA Client Secret', password: true },
      { key: 'refresh_token', label: 'Refresh Token', password: true },
      { key: 'aws_access_key_id', label: 'AWS Access Key ID' },
      { key: 'aws_secret_access_key', label: 'AWS Secret Access Key', password: true },
      { key: 'seller_id', label: 'Seller ID' }
    ],
    shopee: [
      { key: 'partner_id', label: 'Partner ID' },
      { key: 'partner_key', label: 'Partner Key', password: true },
      { key: 'shop_id', label: 'Shop ID' },
      commonAccessToken,
      { key: 'refresh_token', label: 'Refresh Token', password: true }
    ],
    tiktok_shop: [
      { key: 'app_key', label: 'App Key' },
      { key: 'app_secret', label: 'App Secret', password: true },
      { key: 'shop_cipher', label: 'Shop Cipher' },
      commonAccessToken,
      { key: 'refresh_token', label: 'Refresh Token', password: true }
    ],
    aliexpress: [
      { key: 'app_key', label: 'App Key' },
      { key: 'app_secret', label: 'App Secret', password: true },
      commonAccessToken,
      { key: 'refresh_token', label: 'Refresh Token', password: true },
      { key: 'seller_id', label: 'Seller ID' }
    ],
    lazada: [
      { key: 'app_key', label: 'App Key' },
      { key: 'app_secret', label: 'App Secret', password: true },
      commonAccessToken,
      { key: 'refresh_token', label: 'Refresh Token', password: true },
      { key: 'seller_id', label: 'Seller ID' }
    ],
    shopify: [
      { key: 'shop_domain', label: 'Shop Domain' },
      commonAccessToken,
      { key: 'client_id', label: 'Client ID' },
      { key: 'client_secret', label: 'Client Secret', password: true }
    ],
    ebay: [
      { key: 'client_id', label: 'Client ID' },
      { key: 'client_secret', label: 'Client Secret', password: true },
      { key: 'ru_name', label: 'RuName' },
      commonAccessToken,
      { key: 'refresh_token', label: 'Refresh Token', password: true },
      { key: 'seller_id', label: 'Seller ID' }
    ],
    walmart: [
      { key: 'client_id', label: 'Client ID' },
      { key: 'client_secret', label: 'Client Secret', password: true },
      commonAccessToken,
      { key: 'seller_id', label: 'Seller ID' }
    ],
    temu: [
      { key: 'app_key', label: 'App Key' },
      { key: 'app_secret', label: 'App Secret', password: true },
      commonAccessToken,
      { key: 'refresh_token', label: 'Refresh Token', password: true },
      { key: 'seller_id', label: 'Seller ID' },
      { key: 'mall_id', label: 'Mall ID' }
    ],
    shein: [
      { key: 'open_key_id', label: 'Open Key ID' },
      { key: 'secret_key', label: 'Secret Key', password: true },
      { key: 'seller_id', label: 'Seller ID' }
    ],
    coupang: [
      { key: 'access_key', label: 'Access Key' },
      { key: 'secret_key', label: 'Secret Key', password: true },
      { key: 'vendor_id', label: 'Vendor ID' }
    ],
    wayfair: [
      { key: 'client_id', label: 'Client ID' },
      { key: 'client_secret', label: 'Client Secret', password: true },
      commonAccessToken,
      { key: 'supplier_id', label: 'Supplier ID' }
    ],
    dmsmatrix: [
      { key: 'client_name', label: 'Client-Name' },
      { key: 'client_id', label: 'Client-Id' },
      { key: 'client_secret', label: 'Client-Secret', password: true },
      { key: 'channel_code', label: '渠道 code' }
    ]
  }
  return fields[current] || []
}

function credentialText(value: unknown) {
  return `${value ?? ''}`.trim()
}

function firstCredentialValue(...values: unknown[]) {
  return values.map(credentialText).find(Boolean) || ''
}

function normalizeCredentials(credentials?: Record<string, unknown>): Record<string, string> {
  const normalized: Record<string, string> = {}
  Object.entries(credentials || {}).forEach(([key, value]) => {
    const text = credentialText(value)
    if (text) normalized[key] = text
  })
  const clientId = firstCredentialValue(normalized.client_id, normalized.clientId, normalized.app_id, normalized.application_id)
  const clientSecret = firstCredentialValue(
    normalized.client_secret,
    normalized.clientSecret,
    normalized.api_key,
    normalized.apiKey,
    normalized.secret
  )
  if (clientId) normalized.client_id = clientId
  if (clientSecret) normalized.client_secret = clientSecret
  return normalized
}

function mergeCredentials(base?: Record<string, unknown>, updates?: Record<string, unknown>) {
  return normalizeCredentials({ ...normalizeCredentials(base), ...normalizeCredentials(updates) })
}

function oauthClientSecret(credentials?: Record<string, unknown>) {
  const normalized = normalizeCredentials(credentials)
  return credentialText(normalized.client_secret || normalized.api_key)
}

function hasOAuthClientCredentials(credentials?: Record<string, unknown>) {
  const normalized = normalizeCredentials(credentials)
  return Boolean(credentialText(normalized.client_id) && oauthClientSecret(normalized))
}

function rowAccountId(row: ShopDto) {
  return row.shop_id || row.account_id || ''
}

function buildAuthContext(row: ShopDto, platformOverride?: string): AuthContext {
  const accountId = rowAccountId(row)
  const platform = canonicalPlatform(platformOverride || row.platform)
  return {
    platform,
    accountId,
    displayName: row.display_name || accountId,
    enabled: row.enabled,
    settings: normalizePlatformSettings(platform, row.settings)
  }
}

function buildShopProfilePayload(values: ShopFormValues, settings?: ShopFormValues['settings']) {
  return {
    display_name: values.display_name?.trim() || '',
    enabled: values.enabled !== false,
    settings: normalizePlatformSettings(values.platform, settings || values.settings)
  }
}

function authStatusLabel(value?: string) {
  if (value === 'success') return '成功'
  if (value === 'failed') return '失败'
  return '未授权'
}

function authStatusColor(value?: string) {
  if (value === 'success') return 'success'
  if (value === 'failed') return 'error'
  return 'default'
}

export function Shops() {
  const { message, modal } = App.useApp()
  const [filterForm] = Form.useForm<FilterValues>()
  const [form] = Form.useForm<ShopFormValues>()
  const [platforms, setPlatforms] = useState<PlatformOptionDto[]>([])
  const [shops, setShops] = useState<ShopDto[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [oauthStarting, setOauthStarting] = useState(false)
  const [oauthCompleting, setOauthCompleting] = useState(false)
  const initialLoadStarted = useRef(false)
  const formCredentialsRef = useRef<Record<string, string>>({})
  const oauthWindowRef = useRef<Window | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [dialogMode, setDialogMode] = useState<DialogMode>('create')
  const [currentRow, setCurrentRow] = useState<ShopDto | null>(null)
  const [authContext, setAuthContext] = useState<AuthContext | null>(null)
  const [oauthStep, setOauthStep] = useState<1 | 2>(1)
  const [oauthState, setOauthState] = useState('')
  const [oauthCode, setOauthCode] = useState('')
  const platform = Form.useWatch('platform', form)
  const settings = Form.useWatch('settings', form) || {}
  const activePlatform =
    dialogMode === 'auth'
      ? canonicalPlatform(authContext?.platform || resolveRowPlatform(currentRow) || platform)
      : canonicalPlatform(platform || form.getFieldValue('platform') || resolveRowPlatform(currentRow))
  const activeSettings = dialogMode === 'auth' ? authContext?.settings || normalizePlatformSettings(activePlatform, currentRow?.settings) : normalizePlatformSettings(activePlatform, settings)

  const platformOptions = useMemo(
    () => platforms.filter((item) => item.enabled !== false).map((item) => ({ value: item.platform, label: platformDisplayName(item.platform) })),
    [platforms]
  )

  function platformDisplayName(value?: string) {
    const map: Record<string, string> = {
      joom_logistics: 'Joom',
      wildberries: 'Wildberries',
      mercadolibre: 'MercadoLibre',
      dmsmatrix: 'DMSMatrix'
    }
    return map[value || ''] || platforms.find((item) => item.platform === value)?.display_name || value || '-'
  }

  function resolveRowPlatform(row?: ShopDto | null) {
    const explicit = canonicalPlatform(row?.platform)
    if (explicit) return explicit
    const accountId = row ? rowAccountId(row) : ''
    const matched = row
      ? shops.find((item) => {
          if (row.id && item.id === row.id) return true
          if (accountId && rowAccountId(item) === accountId) return true
          return Boolean(row.display_name && item.display_name === row.display_name)
        })
      : undefined
    return canonicalPlatform(matched?.platform || form.getFieldValue('platform') || filterForm.getFieldValue('platform') || platform)
  }

  function buildListParams(): ShopListParams {
    const values = filterForm.getFieldsValue()
    return {
      display_name: values.display_name?.trim() || undefined,
      platform: values.platform || undefined,
      enabled: values.enabled
    }
  }

  async function loadPlatforms() {
    try {
      const data = await listPlatforms({ background: true })
      setPlatforms(data || [])
    } catch {
      setPlatforms([])
    }
  }

  async function load() {
    setLoading(true)
    try {
      setShops(await listShops(buildListParams()))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (initialLoadStarted.current) return
    initialLoadStarted.current = true
    void loadPlatforms()
    void load()
  }, [])

  function resetForm() {
    formCredentialsRef.current = {}
    form.setFieldsValue({
      platform: platforms[0]?.platform || 'ozon',
      shop_id: '',
      display_name: '',
      enabled: true,
      credentials: {},
      settings: normalizePlatformSettings(platforms[0]?.platform || 'ozon'),
      authorization_expires_at: ''
    })
  }

  function fillFormFromRow(row: ShopDto, credentials: Record<string, string> = {}, platformOverride?: string) {
    const resolvedPlatform = canonicalPlatform(platformOverride || row.platform)
    const accountId = rowAccountId(row)
    const normalizedCredentials = normalizeCredentials(credentials)
    formCredentialsRef.current = normalizedCredentials
    form.setFieldsValue({
      platform: resolvedPlatform,
      shop_id: accountId,
      display_name: row.display_name || accountId,
      enabled: row.enabled,
      credentials: normalizedCredentials,
      settings: normalizePlatformSettings(resolvedPlatform, row.settings),
      authorization_expires_at: row.authorization_expires_at ? row.authorization_expires_at.slice(0, 19) : ''
    })
  }

  function hydrateFormAfterModalOpen(open: boolean) {
    if (!open || dialogMode === 'auth') return
    if (dialogMode === 'create') {
      resetForm()
      return
    }
    if (currentRow) {
      fillFormFromRow(currentRow, formCredentialsRef.current, resolveRowPlatform(currentRow))
    }
  }

  function effectiveFormValues(): ShopFormValues {
    const values = form.getFieldsValue(true) as ShopFormValues
    const accountId = values.shop_id || authContext?.accountId || rowAccountId(currentRow || ({} as ShopDto))
    return {
      ...values,
      platform: canonicalPlatform(values.platform || authContext?.platform || currentRow?.platform || ''),
      shop_id: accountId,
      display_name: values.display_name || authContext?.displayName || currentRow?.display_name || accountId,
      enabled: values.enabled ?? authContext?.enabled ?? currentRow?.enabled ?? true,
      credentials: normalizeCredentials(values.credentials),
      settings: normalizePlatformSettings(values.platform || authContext?.platform || currentRow?.platform, values.settings || authContext?.settings || currentRow?.settings),
      authorization_expires_at: values.authorization_expires_at || ''
    }
  }

  async function loadMergedCredentials(platformValue: string, accountId: string, formCredentials?: Record<string, unknown>) {
    let storedCredentials: Record<string, string> = {}
    try {
      storedCredentials = normalizeCredentials(await getShopCredentials(platformValue, accountId))
    } catch {
      storedCredentials = {}
    }
    return mergeCredentials(storedCredentials, formCredentials)
  }

  async function persistCredentials(values: ShopFormValues, credentialsOverride?: Record<string, unknown>) {
    const targetPlatform = canonicalPlatform(values.platform)
    const targetAccountId = values.shop_id || ''
    if (!targetPlatform || !targetAccountId) return normalizeCredentials(credentialsOverride || values.credentials)
    const credentials = await loadMergedCredentials(targetPlatform, targetAccountId, credentialsOverride || values.credentials)
    if (Object.keys(credentials).length || values.authorization_expires_at) {
      await updateShopCredentials(targetPlatform, targetAccountId, {
        credentials,
        authorization_expires_at: values.authorization_expires_at || null
      })
      form.setFieldValue('credentials', credentials)
    }
    return credentials
  }

  function openCreate() {
    setDialogMode('create')
    setCurrentRow(null)
    setAuthContext(null)
    setOauthState('')
    setOauthCode('')
    setOauthStep(1)
    resetForm()
    setDialogOpen(true)
  }

  async function openEdit(row: ShopDto) {
    const rowPlatform = resolveRowPlatform(row)
    setDialogMode('edit')
    setCurrentRow(row)
    setAuthContext(null)
    setOauthState('')
    setOauthCode('')
    setOauthStep(1)
    fillFormFromRow(row, {}, rowPlatform)
    setDialogOpen(true)
    try {
      const creds = await getShopCredentials(rowPlatform, rowAccountId(row))
      const normalizedCredentials = normalizeCredentials(creds)
      formCredentialsRef.current = normalizedCredentials
      form.setFieldValue('credentials', normalizedCredentials)
    } catch {
      formCredentialsRef.current = {}
      form.setFieldValue('credentials', {})
    }
  }

  async function openAuthorize(row: ShopDto) {
    const rowPlatform = resolveRowPlatform(row)
    const nextAuthContext = buildAuthContext(row, rowPlatform)
    if (!nextAuthContext.platform || !nextAuthContext.accountId) {
      message.error('无法识别店铺平台或店铺编码，不能重新授权')
      return
    }
    setCurrentRow(row)
    setAuthContext(nextAuthContext)
    fillFormFromRow(row, {}, rowPlatform)
    let credentials: Record<string, string> = {}
    try {
      credentials = normalizeCredentials(await getShopCredentials(nextAuthContext.platform, nextAuthContext.accountId))
      formCredentialsRef.current = credentials
      form.setFieldValue('credentials', credentials)
    } catch {
      formCredentialsRef.current = {}
      form.setFieldValue('credentials', {})
    }
    if (isOAuthPlatform(nextAuthContext.platform) && !hasOAuthClientCredentials(credentials)) {
      setDialogMode('edit')
      setDialogOpen(true)
      message.warning('请先维护客户端 ID 和客户端密钥')
      return
    }
    setDialogMode('auth')
    setOauthState('')
    setOauthCode('')
    setOauthStep(1)
    setDialogOpen(true)
  }

  async function saveBeforeOAuth(credentialsOverride?: Record<string, unknown>) {
    const values = dialogMode === 'auth' ? effectiveFormValues() : await form.validateFields()
    const currentSettings = form.getFieldValue('settings')
    setSaving(true)
    try {
      if (dialogMode === 'create') {
        const credentials = normalizeCredentials(credentialsOverride || values.credentials)
        const data = await createShop({
          platform: values.platform || 'ozon',
          display_name: values.display_name?.trim() || '',
          enabled: values.enabled !== false,
          credential_type: manualCredentialType(values.platform),
          credentials,
          settings: normalizePlatformSettings(values.platform, values.settings),
          authorization_expires_at: values.authorization_expires_at || null
        })
        setCurrentRow(data)
        setAuthContext(buildAuthContext(data))
        fillFormFromRow(data, credentials)
        setDialogMode('edit')
        await load()
        return true
      }

      const data = await updateShop(values.platform || '', values.shop_id || '', buildShopProfilePayload(values, currentSettings || values.settings))
      const credentials = await persistCredentials(values, credentialsOverride)
      setCurrentRow(data)
      setAuthContext(buildAuthContext(data))
      fillFormFromRow(data, credentials)
      await load()
      return true
    } catch {
      return false
    } finally {
      setSaving(false)
    }
  }

  async function save() {
    const values = await form.validateFields()
    const currentSettings = form.getFieldValue('settings')
    setSaving(true)
    try {
      if (dialogMode === 'create') {
        await createShop({
          platform: values.platform || 'ozon',
          display_name: values.display_name?.trim() || '',
          enabled: values.enabled !== false,
          credential_type: manualCredentialType(values.platform),
          credentials: values.credentials || {},
          settings: normalizePlatformSettings(values.platform, values.settings),
          authorization_expires_at: values.authorization_expires_at || null
        })
        message.success('店铺已创建')
      } else if (dialogMode === 'edit') {
        const data = await updateShop(values.platform || '', values.shop_id || '', buildShopProfilePayload(values, currentSettings))
        const credentials = await persistCredentials(values)
        setCurrentRow(data)
        fillFormFromRow(data, credentials)
        message.success('店铺已更新')
      } else {
        const nextValues = effectiveFormValues()
        const credentials = await loadMergedCredentials(
          authContext?.platform || nextValues.platform || '',
          authContext?.accountId || nextValues.shop_id || '',
          nextValues.credentials
        )
        await reauthorizeShop(authContext?.platform || nextValues.platform || '', authContext?.accountId || nextValues.shop_id || '', {
          credentials,
          authorization_expires_at: values.authorization_expires_at || null
        })
        message.success('授权已提交')
      }
      setDialogOpen(false)
      await load()
    } finally {
      setSaving(false)
    }
  }

  async function switchToAuthorize() {
    if (!(await saveBeforeOAuth())) return
    setDialogMode('auth')
    setOauthStep(1)
    setOauthState('')
    setOauthCode('')
  }

  async function startOAuth() {
    const values = effectiveFormValues()
    const targetPlatform = authContext?.platform || values.platform || ''
    const targetAccountId = authContext?.accountId || values.shop_id || ''
    const credentials = await loadMergedCredentials(targetPlatform, targetAccountId, values.credentials)
    form.setFieldValue('credentials', credentials)
    if (!hasOAuthClientCredentials(credentials)) {
      message.warning('请先维护 Client ID 和 Client Secret')
      return
    }
    if (!(await saveBeforeOAuth(credentials))) return
    const nextValues = effectiveFormValues()
    const authWindow = window.open('about:blank', '_blank')
    oauthWindowRef.current = authWindow
    setOauthStarting(true)
    try {
      const data = await startShopOAuth(targetPlatform || nextValues.platform || '', targetAccountId || nextValues.shop_id || '', { credentials })
      setOauthState(data.state || '')
      if (authWindow && data.authorize_url) {
        authWindow.location.href = data.authorize_url
      } else if (data.authorize_url) {
        window.open(data.authorize_url, '_blank', 'noopener,noreferrer')
      } else if (authWindow) {
        authWindow.close()
        oauthWindowRef.current = null
      }
      message.success(`已创建授权链接，请在新窗口完成 ${platformDisplayName(targetPlatform || nextValues.platform)} 授权`)
      setOauthStep(2)
      await load()
    } catch {
      authWindow?.close()
      oauthWindowRef.current = null
    } finally {
      setOauthStarting(false)
    }
  }

  async function completeOAuth(codeOverride = '', stateOverride = '') {
    const values = form.getFieldsValue()
    const targetPlatform = authContext?.platform || values.platform || ''
    const targetAccountId = authContext?.accountId || values.shop_id || ''
    const authorizationCode = codeOverride.trim() || oauthCode.trim()
    const authorizationState = stateOverride.trim() || oauthState
    if (!authorizationCode) {
      message.warning('请输入验证码')
      return
    }
    if (!authorizationState) {
      message.error('授权会话已失效，请重新发起授权')
      return
    }
    setOauthCompleting(true)
    try {
      const data = await completeShopOAuth(targetPlatform, targetAccountId, {
        state: authorizationState,
        code: authorizationCode
      })
      if (data.status === 'pending') {
        message.warning(data.message || '授权尚未完成')
        return
      }
      message.success(`${platformDisplayName(targetPlatform)} 授权结果已同步`)
      if (data.shop) {
        setCurrentRow(data.shop)
        setAuthContext(buildAuthContext(data.shop))
        fillFormFromRow(data.shop, normalizeCredentials(values.credentials))
      }
      try {
        const creds = await getShopCredentials(targetPlatform, targetAccountId)
        form.setFieldValue('credentials', normalizeCredentials(creds))
      } catch {
        // keep existing credentials
      }
      await load()
      setDialogOpen(false)
      setOauthState('')
      setOauthStep(1)
      setOauthCode('')
      oauthWindowRef.current?.close()
      oauthWindowRef.current = null
    } finally {
      setOauthCompleting(false)
    }
  }

  useEffect(() => {
    function handleOAuthCallback(event: MessageEvent) {
      const data = event.data as {
        type?: string
        platform?: string
        code?: string
        state?: string
        error?: string
      }
      if (data?.type !== 'caifuclaw-oauth-callback' || dialogMode !== 'auth') return
      if (oauthWindowRef.current && event.source !== oauthWindowRef.current) return
      const targetPlatform = canonicalPlatform(authContext?.platform || form.getFieldValue('platform'))
      if (canonicalPlatform(data.platform) !== targetPlatform) return
      if (data.state && oauthState && data.state !== oauthState) {
        message.error('授权状态校验失败，请重新发起授权')
        return
      }
      if (data.error) {
        message.error(data.error)
        return
      }
      const code = String(data.code || '').trim()
      if (!code) {
        message.error('平台回调未返回授权码')
        return
      }
      setOauthCode(code)
      void completeOAuth(code, data.state || oauthState)
    }
    window.addEventListener('message', handleOAuthCallback)
    return () => window.removeEventListener('message', handleOAuthCallback)
  }, [authContext?.platform, dialogMode, message, oauthState])

  async function onToggleEnabled(row: ShopDto) {
    const action = row.enabled ? '停用' : '启用'
    modal.confirm({
      title: '状态切换',
      content: `确认${action}店铺「${row.display_name || rowAccountId(row)}」吗？`,
      okText: action,
      cancelText: '取消',
      onOk: async () => {
        await toggleShopEnabled(row.platform, rowAccountId(row))
        message.success(`店铺已${action}`)
        await load()
      }
    })
  }

  const dialogTitle = (() => {
    if (dialogMode === 'create') return '新增店铺'
    if (dialogMode === 'auth') {
      const platformName = platformDisplayName(authContext?.platform || currentRow?.platform || platform)
      const name = authContext?.displayName || currentRow?.display_name || form.getFieldValue('display_name') || rowAccountId(currentRow || ({} as ShopDto))
      return name ? `店铺授权-${platformName}-${name}` : `店铺授权-${platformName}`
    }
    return '编辑店铺'
  })()

  const columns: ColumnsType<ShopDto> = [
    { title: '店铺名称', dataIndex: 'display_name', width: 180, ellipsis: true },
    { title: '平台', dataIndex: 'platform', width: 130, render: platformDisplayName },
    {
      title: '状态',
      dataIndex: 'enabled',
      width: 90,
      render: (value) => <Tag color={value ? 'success' : 'default'}>{value ? '启用' : '停用'}</Tag>
    },
    {
      title: '授权状态',
      dataIndex: 'authorization_status',
      width: 110,
      render: (value) => <Tag color={authStatusColor(value)}>{authStatusLabel(value)}</Tag>
    },
    {
      title: 'Token 验证',
      dataIndex: 'token_message',
      width: 220,
      ellipsis: true,
      render: (value, row) =>
        value ? (
          <Tooltip title={value}>
            <span className={row.token_valid === false ? 'token-msg danger' : 'token-msg'}>{value}</span>
          </Tooltip>
        ) : (
          <span className="token-msg">未验证</span>
        )
    },
    { title: '最后授权时间', dataIndex: 'last_authorized_at', width: 170, render: (value) => formatTime(value, true) },
    { title: '授权到期时间', dataIndex: 'authorization_expires_at', width: 170, render: (value) => formatTime(value, true) },
    { title: '创建人', dataIndex: 'created_by', width: 110, render: (value) => value || '-' },
    { title: '创建时间', dataIndex: 'created_at', width: 170, render: (value) => formatTime(value, true) },
    {
      title: '操作',
      key: 'action',
      width: 210,
      fixed: 'right',
      render: (_, row) => (
        <Space size={4}>
          <Button type="link" size="small" onClick={() => openEdit(row)}>
            编辑
          </Button>
          <Button type="link" size="small" onClick={() => openAuthorize(row)}>
            {row.authorization_status === 'success' ? '重新授权' : '授权'}
          </Button>
          <Button type="link" size="small" onClick={() => onToggleEnabled(row)}>
            {row.enabled ? '停用' : '启用'}
          </Button>
        </Space>
      )
    }
  ]

  return (
    <div className="page-card">
      <div className="orders-header">
        <h2>店铺管理</h2>
        <Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新增店铺
          </Button>
        </Space>
      </div>

      <Form
        form={filterForm}
        layout="inline"
        className="orders-filter"
        onFinish={load}
      >
        <Form.Item label="店铺名称" name="display_name">
          <Input allowClear placeholder="输入店铺名称" style={{ width: 180 }} />
        </Form.Item>
        <Form.Item label="平台" name="platform">
          <Select allowClear placeholder="全部平台" style={{ width: 180 }} options={platformOptions} />
        </Form.Item>
        <Form.Item label="状态" name="enabled">
          <Select
            allowClear
            placeholder="全部状态"
            style={{ width: 140 }}
            options={[
              { value: true, label: '启用' },
              { value: false, label: '停用' }
            ]}
          />
        </Form.Item>
        <Form.Item>
          <Space>
            <Button type="primary" htmlType="submit">
              查询
            </Button>
            <Button
              onClick={() => {
                filterForm.resetFields()
                void load()
              }}
            >
              重置
            </Button>
          </Space>
        </Form.Item>
      </Form>

      <DataTable
        rowKey={(row) => row.id || `${row.platform}-${rowAccountId(row)}`}
        loading={loading}
        dataSource={shops}
        columns={columns}
        pagination={false}
        onRow={(row) => ({
          onDoubleClick: (event) => {
            if (shouldIgnoreTableRowDoubleClick(event.target)) return
            void openEdit(row)
          }
        })}
      />

      <Modal
        open={dialogOpen}
        title={dialogTitle}
        centered
        wrapClassName="shop-auth-modal-wrap"
        className="shop-auth-modal"
        width="min(1060px, calc(100vw - 32px))"
        confirmLoading={saving}
        maskClosable={false}
        keyboard={false}
        forceRender
        afterOpenChange={hydrateFormAfterModalOpen}
        okText={dialogMode === 'auth' ? '提交授权' : '保存'}
        footer={
          dialogMode === 'auth' && isOAuthPlatform(activePlatform)
            ? null
            : (_, { OkBtn, CancelBtn }) => (
                <div className="shop-modal-footer">
                  {dialogMode !== 'create' && isOAuthPlatform(activePlatform) ? (
                    <div className="shop-modal-footer-auth">
                      <Button type="primary" ghost onClick={switchToAuthorize}>
                        授权
                      </Button>
                    </div>
                  ) : null}
                  <div className="shop-modal-footer-actions">
                    <CancelBtn />
                    <OkBtn />
                  </div>
                </div>
              )
        }
        onOk={save}
        onCancel={() => setDialogOpen(false)}
      >
        {dialogMode === 'auth' && isOAuthPlatform(activePlatform) ? (
          <section className="oauth-guide">
            <div className="oauth-hero">
              <div className="oauth-hero-mark">
                <SafetyCertificateOutlined />
              </div>
              <div className="oauth-hero-copy">
                <span>{platformDisplayName(activePlatform)} 授权向导</span>
                <h3>{authContext?.displayName || currentRow?.display_name || form.getFieldValue('display_name') || '店铺授权'}</h3>
              </div>
              <div className="oauth-progress-pill">第 {oauthStep}/2 步</div>
            </div>

            <div className="oauth-stepper" aria-label="授权进度">
              <div className={`oauth-step ${oauthStep === 1 ? 'active' : 'done'}`}>
                <div className="oauth-step-icon">{oauthStep === 2 ? <CheckCircleOutlined /> : <EditOutlined />}</div>
                <div className="oauth-step-label">
                  <strong>开始授权</strong>
                  <span>生成平台授权链接</span>
                </div>
              </div>
              <div className="oauth-step-line" />
              <div className={`oauth-step ${oauthStep === 2 ? 'active' : ''}`}>
                <div className="oauth-step-icon">{oauthStep === 2 ? <EditOutlined /> : '2'}</div>
                <div className="oauth-step-label">
                  <strong>在线鉴权</strong>
                  <span>回填验证码完成授权</span>
                </div>
              </div>
            </div>

            {oauthStep === 1 ? (
              <div className="oauth-panel">
                <div className="oauth-panel-copy">
                  <span className="oauth-panel-kicker">Step 01</span>
                  <h3>开始平台授权</h3>
                  <p>点击申请后，将在新窗口打开平台授权页。完成授权后回到当前页面填写验证码。</p>
                </div>
                <div className="oauth-panel-actions">
                  {isMercadoLibre(activePlatform) ? (
                    <div className="oauth-site-row">
                      <span>站点</span>
                      <Select
                        value={activeSettings.mercado_site as string}
                        className="oauth-site-select"
                        options={[
                          { value: 'CBT', label: '跨境CBT' },
                          { value: 'MLA', label: '阿根廷（本土）' },
                          { value: 'MLB', label: '巴西（本土）' },
                          { value: 'MLC', label: '智利（本土）' },
                          { value: 'MCO', label: '哥伦比亚（本土）' },
                          { value: 'MEC', label: '厄瓜多尔（本土）' },
                          { value: 'MLM', label: '墨西哥（本土）' },
                          { value: 'MPE', label: '秘鲁（本土）' },
                          { value: 'MLU', label: '乌拉圭（本土）' }
                        ]}
                        onChange={(value) => {
                          form.setFieldValue(['settings', 'mercado_site'], value)
                          form.setFieldValue(['settings', 'mercado_store_type'], mercadoStoreTypeForSite(value))
                        }}
                      />
                    </div>
                  ) : null}
                  <Button className="oauth-primary-action" type="primary" icon={<LinkOutlined />} loading={oauthStarting} onClick={startOAuth}>
                    点击申请
                  </Button>
                </div>
              </div>
            ) : (
              <div className="oauth-panel">
                <div className="oauth-panel-copy">
                  <span className="oauth-panel-kicker">Step 02</span>
                  <h3>获取授权结果</h3>
                  <p>授权完成后系统会自动回签；如未自动完成，可粘贴平台返回的验证码。</p>
                </div>
                <div className="oauth-code-row">
                  <label>
                    <span className="required">*</span>
                    验证码
                  </label>
                  <Input className="oauth-code-input" value={oauthCode} allowClear onChange={(event) => setOauthCode(event.target.value)} />
                  <Button className="oauth-primary-action" type="primary" loading={oauthCompleting} onClick={() => void completeOAuth()}>
                    获取授权
                  </Button>
                </div>
              </div>
            )}
          </section>
        ) : (
          <Form form={form} layout="vertical" preserve={false}>
            <Row gutter={12}>
              <Col span={12}>
                <Form.Item label="平台" name="platform" rules={[{ required: true, message: '请选择平台' }]}>
                  <Select disabled={dialogMode !== 'create'} placeholder="选择平台" options={platformOptions} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item label="店铺编码" name="shop_id">
                  <Input disabled placeholder={dialogMode === 'create' ? '保存后自动生成' : '保存后不可修改'} />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item label="店铺名称" name="display_name" rules={[{ required: true, message: '请输入店铺名称' }]}>
              <Input />
            </Form.Item>
            <Form.Item label="启用状态" name="enabled" valuePropName="checked">
              <Switch checkedChildren="启用" unCheckedChildren="停用" />
            </Form.Item>

            <Divider>授权信息</Divider>
            {isOAuthPlatform(activePlatform) ? (
              <Row gutter={12}>
                <Col span={12}>
                  <Form.Item label="客户端 ID" name={['credentials', 'client_id']}>
                    <Input placeholder="请输入客户端 ID" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="客户端密钥" name={['credentials', 'client_secret']}>
                    <Input.Password placeholder="请输入客户端密钥" />
                  </Form.Item>
                </Col>
              </Row>
            ) : (
              <Row gutter={12}>
                {credentialFields(activePlatform).map((field) => (
                  <Col key={field.key} span={12}>
                    <Form.Item key={field.key} label={field.label} name={['credentials', field.key]}>
                      {field.password ? <Input.Password /> : <Input />}
                    </Form.Item>
                  </Col>
                ))}
                <Col span={12}>
                  <Form.Item label="授权到期时间" name="authorization_expires_at">
                    <Input placeholder="YYYY-MM-DDTHH:mm:ss" />
                  </Form.Item>
                </Col>
              </Row>
            )}

            {activePlatform === 'ozon' ? (
              <Form.Item label="FBO/FBP 订单" name={['settings', 'fbo_fbp_download_mode']}>
                <Radio.Group>
                  <Radio value="to_unshipped">下载到未发货</Radio>
                  <Radio value="to_completed">下载到已完成</Radio>
                  <Radio value="none">不下载</Radio>
                </Radio.Group>
              </Form.Item>
            ) : null}
            {activePlatform === 'allegro' ? (
              <>
                <Form.Item label="下载平台包订单" name={['settings', 'download_platform_package_orders']}>
                  <Radio.Group>
                    <Radio value={true}>下载</Radio>
                    <Radio value={false}>不下载</Radio>
                  </Radio.Group>
                </Form.Item>
                <Form.Item label="物流商 carrierId" name={['settings', 'allegro_carrier_id']}>
                  <Input placeholder="Allegro carrier UUID，例如 0c0ffe5b-1d12-41b2-9176-f9906416c8ff" />
                </Form.Item>
              </>
            ) : null}
            {isMercadoLibre(activePlatform) ? (
              <>
                <Form.Item label="下载 Full 包订单" name={['settings', 'download_full_orders']}>
                  <Radio.Group>
                    <Radio value={true}>下载</Radio>
                    <Radio value={false}>不下载</Radio>
                  </Radio.Group>
                </Form.Item>
                <Form.Item label="起始拉取状态" name={['settings', 'mercado_order_pull_status']}>
                  <Radio.Group>
                    <Radio value="paid">付款后拉取</Radio>
                    <Radio value="after_shipped">发货后拉取</Radio>
                  </Radio.Group>
                </Form.Item>
              </>
            ) : null}
            {activePlatform === 'joom_logistics' ? (
              <Form.Item
                label="下载海外仓订单"
                name={['settings', 'download_overseas_warehouse_orders']}
                extra={
                  <div className="setting-warning">
                    开启下载海外仓订单后，默认仅拉取发货后状态的订单，避免缺货转自发货导致漏单风险。
                  </div>
                }
              >
                <Radio.Group>
                  <Radio value={false}>不下载</Radio>
                  <Radio value={true}>下载</Radio>
                </Radio.Group>
              </Form.Item>
            ) : null}
            {activePlatform === 'dmsmatrix' ? (
              <>
                <Form.Item label="Auto cache labels" name={['settings', 'auto_cache_labels']} valuePropName="checked">
                  <Switch checkedChildren="On" unCheckedChildren="Off" />
                </Form.Item>
                <Row gutter={12}>
                  <Col span={12}>
                    <Form.Item label="Orders path" name={['settings', 'orders_path']}>
                      <Input placeholder="/Order/getOrders" />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item label="Label path" name={['settings', 'label_path']}>
                      <Input placeholder="/shipments/{shipment_id}/label" />
                    </Form.Item>
                  </Col>
                </Row>
              </>
            ) : null}
          </Form>
        )}
      </Modal>
    </div>
  )
}
