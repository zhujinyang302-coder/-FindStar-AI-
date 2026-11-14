import { request } from './client'
import type {
  CreateItemPayload,
  ExtractFeaturesResult,
  ItemType,
  MyItemDetail,
  MyItemListResult,
  MyItemOut,
  UploadResult
} from '@/types'

export interface MyItemQuery {
  type?: ItemType
  status?: string
  has_match?: boolean
  page?: number
  page_size?: number
}

export function createLostItem(payload: CreateItemPayload): Promise<MyItemOut> {
  return request<MyItemOut>({ url: '/lost-items', method: 'post', data: payload })
}

export function createFoundItem(payload: CreateItemPayload): Promise<MyItemOut> {
  return request<MyItemOut>({ url: '/found-items', method: 'post', data: payload })
}

export function fetchMyItems(params: MyItemQuery): Promise<MyItemListResult> {
  return request<MyItemListResult>({ url: '/my/items', params })
}

export function fetchMyItem(type: ItemType, id: number): Promise<MyItemDetail> {
  return request<MyItemDetail>({ url: `/my/items/${type}/${id}` })
}

export function updateMyItem(
  type: ItemType,
  id: number,
  payload: Partial<CreateItemPayload>
): Promise<MyItemOut> {
  return request<MyItemOut>({ url: `/my/items/${type}/${id}`, method: 'patch', data: payload })
}

export function withdrawItem(type: ItemType, id: number): Promise<{ item_id: number; status: string }> {
  return request({ url: `/my/items/${type}/${id}/withdraw`, method: 'post' })
}

export function resubmitItem(type: ItemType, id: number): Promise<{ item_id: number; status: string; review_ticket_no: string }> {
  return request({ url: `/my/items/${type}/${id}/resubmit`, method: 'post' })
}

export function requestDelist(
  type: ItemType,
  id: number,
  reason: string
): Promise<{ ticket_no: string; status: string }> {
  return request({ url: `/my/items/${type}/${id}/delist-request`, method: 'post', data: { reason } })
}

export function uploadImage(file: File): Promise<UploadResult> {
  const form = new FormData()
  form.append('file', file)
  return request<UploadResult>({ url: '/uploads', method: 'post', data: form })
}

export function extractFeatures(payload: {
  description?: string
  image_keys?: string[]
  category_hint?: string
}): Promise<ExtractFeaturesResult> {
  return request<ExtractFeaturesResult>({ url: '/ai/extract-features', method: 'post', data: payload })
}