import { request } from './client'
import type {
  ContactRequestDetail,
  ContactRequestList,
  ReceivedContactList
} from '@/types'

export function createContactRequest(payload: {
  batch_id: string
  candidate_public_id: string
  request_type: 'claim' | 'return_clue'
  private_verification?: string
  handover_location_code?: string
  handover_window_start?: string
  handover_window_end?: string
  handover_note?: string
}): Promise<{ id: number; status: string }> {
  return request({ url: '/contact-requests', method: 'post', data: payload })
}

export function fetchMyRequests(): Promise<ContactRequestList> {
  return request<ContactRequestList>({ url: '/contact-requests/me' })
}

export function fetchReceivedRequests(): Promise<ReceivedContactList> {
  return request<ReceivedContactList>({ url: '/contact-requests/received' })
}

export function fetchContactDetail(id: number): Promise<ContactRequestDetail> {
  return request<ContactRequestDetail>({ url: `/contact-requests/${id}` })
}

export function confirmContact(
  id: number,
  payload: {
    handover_location_code: string
    handover_window_start: string
    handover_window_end: string
    handover_note?: string
    sensitive_verified: boolean
  }
): Promise<{
  id: number
  status: string
  target_item_status: string
  initiated_item_status: string
  disclosure_level: string
  invalidated_batches: number
  notified_users: number
}> {
  return request({ url: `/contact-requests/${id}/confirm`, method: 'post', data: payload })
}

export function rejectContact(id: number, decisionNote: string): Promise<{ id: number; status: string }> {
  return request({
    url: `/contact-requests/${id}/reject`,
    method: 'post',
    data: { decision_note: decisionNote }
  })
}