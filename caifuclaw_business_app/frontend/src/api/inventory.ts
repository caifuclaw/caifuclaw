import { get, post, put } from './http'
import http from './http'

export interface InventoryDto {
  id: number
  product_id: number
  product_code: string
  product_name: string
  stock_qty: number
  last_count_qty: number
  safety_stock: number | null
  stock_status: string
  remark: string
  updated_at: string | null
}

export interface InventoryListResponse {
  items: InventoryDto[]
  total: number
  page: number
  page_size: number
}

export interface InventoryListParams {
  product_code?: string
  product_name?: string
  stock_status?: string
  hide_zero_safety_stock?: boolean
  page?: number
  page_size?: number
  columns?: string
}

export interface InventoryPayload {
  product_id: number
  stock_qty: number
  last_count_qty: number
  safety_stock: number
  remark: string
}

export interface InventoryImportResult {
  created: number
  updated: number
  failed: number
  errors?: Array<{ row?: number; message?: string; [k: string]: unknown }>
}

export function listInventory(params: InventoryListParams) {
  return get<InventoryListResponse>('/api/v1/inventory', { params, background: true })
}

export function createInventory(payload: InventoryPayload) {
  return post<InventoryDto>('/api/v1/inventory', payload)
}

export function updateInventory(id: number, payload: InventoryPayload) {
  return put<InventoryDto>(`/api/v1/inventory/${id}`, payload)
}

export function importInventory(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return post<InventoryImportResult>('/api/v1/inventory/import', formData)
}

export async function exportInventoryBlob(params: InventoryListParams): Promise<Blob> {
  const res = await http.get<Blob>('/api/v1/inventory/export', {
    params,
    responseType: 'blob'
  })
  return res.data
}

export async function downloadInventoryImportTemplateBlob(): Promise<Blob> {
  const res = await http.get<Blob>('/api/v1/inventory/import-template', {
    responseType: 'blob'
  })
  return res.data
}

// ===== Product search (lightweight, used by Inventory drawer) =====
export interface ProductSearchDto {
  id: number
  product_code: string
  internal_name: string
  safety_stock: number | null
}

export async function searchProductsForInventory(keyword: string): Promise<ProductSearchDto[]> {
  const baseParams = { page: 1, page_size: 50, include_options: false }
  if (!keyword) {
    const resp = await get<{ items: ProductSearchDto[] }>('/api/v1/products', { params: baseParams, background: true })
    return resp.items || []
  }
  const [byName, byCode] = await Promise.all([
    get<{ items: ProductSearchDto[] }>('/api/v1/products', {
      params: { ...baseParams, internal_name: keyword },
      background: true
    }),
    get<{ items: ProductSearchDto[] }>('/api/v1/products', {
      params: { ...baseParams, product_code: keyword },
      background: true
    })
  ])
  const merged = [...(byName.items || []), ...(byCode.items || [])]
  return [...new Map(merged.map((item) => [item.id, item])).values()]
}
