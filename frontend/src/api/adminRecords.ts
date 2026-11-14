import { request } from './client'

export interface AdminRecordItem {
  item_type: string
  item_id: number
  title: string
  category: string
  color: string | null
  location_text: string
  occurred_at: string | null
  status: string
  created_at: string
  is_removed: boolean
  has_pending_delist: boolean
}

export interface AdminRecordList {
  items: AdminRecordItem[]
  total: number
  page: number
  page_size: number
}

export interface AdminRecordDetail {
  item_type: string
  item_id: number
  title: string
  category: string
  color: string | null
  brand: string | null
  location_text: string
  location_code: string | null
  occurred_at: string | null
  status: string
  created_at: string
  updated_at: string
  info_sufficient: boolean
  review_round: number
  description: string
  images: Array<{
    id: number
    url: string | null
    thumb_url: string | null
    sensitive_masked: boolean
  }>
  history: Array<{
    review_round: number
    status: string
    opinion: string | null
    decided_at: string | null
  }>
}

export interface AdminDelistResult {
  ticket_no: string
  item_status: string
  decided_at: string
  invalidated_batches: number
  affected_requests: number
}

export function fetchAdminRecords(params: {
  type?: string
  status?: string
  keyword?: string
  page?: number
  page_size?: number
}): Promise<AdminRecordList> {
  return request<AdminRecordList>({ url: '/admin/records', method: 'get', params })
}

export function fetchAdminRecord(
  itemType: string,
  itemId: number
): Promise<AdminRecordDetail> {
  return request<AdminRecordDetail>({
    url: `/admin/records/${itemType}/${itemId}`,
    method: 'get'
  })
}

export function delistAdminRecord(
  itemType: string,
  itemId: number,
  reason: string
): Promise<AdminDelistResult> {
  return request<AdminDelistResult>({
    url: `/admin/records/${itemType}/${itemId}/delist`,
    method: 'post',
    data: { reason }
  })
}