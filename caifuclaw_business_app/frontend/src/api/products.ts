/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { get, post, put, del } from './http'
import http from './http'

export interface ProductDto {
  id: number
  product_code: string
  internal_name: string
  english_name: string
  cost: number | null
  weight: number | null
  gross_weight: number | null
  package_length: number | null
  package_width: number | null
  package_height: number | null
  ean: string
  description: string
  main_image_url: string
  is_slow_moving_material: boolean
  safety_stock: number | null
  buyer_user_id: number | null
  buyer_name: string | null
  enabled: boolean
  mappings: Record<string, string[]>
}

export type ProductDetailDto = ProductDto

export interface ShopOptionDto {
  id: number
  display_name: string
  platform: string
}

export interface UserSimpleDto {
  id: number
  username: string
  display_name: string | null
}

export interface ProductListResponse {
  items: ProductDto[]
  shops: ShopOptionDto[]
  users: UserSimpleDto[]
  total: number
  page: number
  page_size: number
}

export interface ProductOptionsResponse {
  shops: ShopOptionDto[]
  users: UserSimpleDto[]
}

export interface ProductListParams {
  keyword?: string
  product_code?: string
  internal_name?: string
  english_name?: string
  ean?: string
  shop_sku?: string
  enabled?: boolean
  is_slow_moving_material?: boolean
  include_options?: boolean
  page?: number
  page_size?: number
}

export interface ProductPayload {
  internal_name: string
  english_name: string
  cost: number | null
  weight: number | null
  gross_weight: number | null
  package_length: number | null
  package_width: number | null
  package_height: number | null
  ean: string
  description: string
  main_image_url: string
  is_slow_moving_material: boolean
  safety_stock: number | null
  buyer_user_id: number | null
  enabled: boolean
  mappings: Record<string, string[]>
}

export interface BatchEnabledResult {
  updated?: number
  message?: string
}

export function listProducts(params: ProductListParams) {
  return get<ProductListResponse>('/api/v1/products', { params, background: true })
}

export function listProductOptions() {
  return get<ProductOptionsResponse>('/api/v1/products/options', { silent: true, background: true })
}

export function getProduct(id: number) {
  return get<ProductDetailDto>(`/api/v1/products/${id}`)
}

export function createProduct(payload: ProductPayload) {
  return post<ProductDto>('/api/v1/products', payload)
}

export function updateProduct(id: number, payload: ProductPayload) {
  return put<ProductDto>(`/api/v1/products/${id}`, payload)
}

export function toggleProductEnabled(id: number) {
  return post<{ enabled: boolean }>(`/api/v1/products/${id}/toggle-enabled`)
}

export function batchSetProductEnabled(productIds: number[], enabled: boolean) {
  return post<BatchEnabledResult>(
    `/api/v1/products/batch/enabled?enabled=${enabled}`,
    { product_ids: productIds }
  )
}

export function deleteProduct(id: number) {
  return del<void>(`/api/v1/products/${id}`)
}

export interface ProductImportResult {
  created: number
  updated: number
  failed: number
  errors?: Array<{ row?: number; message?: string; [k: string]: unknown }>
}

export function importProducts(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return post<ProductImportResult>('/api/v1/products/import', formData)
}

export async function exportProductsBlob(params: ProductListParams): Promise<Blob> {
  const res = await http.get<Blob>('/api/v1/products/export', {
    params,
    responseType: 'blob'
  })
  return res.data
}

export async function downloadProductImportTemplateBlob(): Promise<Blob> {
  const res = await http.get<Blob>('/api/v1/products/import-template', {
    responseType: 'blob'
  })
  return res.data
}
