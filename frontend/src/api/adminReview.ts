import { request } from './client'
import type { ReviewDecisionResult, ReviewQueue, ReviewTicketDetail } from '@/types'

export function fetchReviewTickets(params: {
  review_type: 'listing' | 'delisting'
  source?: string
  overdue?: boolean
  page?: number
  page_size?: number
}): Promise<ReviewQueue> {
  return request<ReviewQueue>({ url: '/admin/review/tickets', params })
}

export function fetchReviewTicket(ticketNo: string): Promise<ReviewTicketDetail> {
  return request<ReviewTicketDetail>({ url: `/admin/review/tickets/${ticketNo}` })
}

export function fetchReviewHistory(params: {
  review_type?: 'listing' | 'delisting'
  page?: number
  page_size?: number
}): Promise<ReviewQueue> {
  return request<ReviewQueue>({ url: '/admin/review/history', params })
}

export function decideReview(
  ticketNo: string,
  payload: { decision: 'approve' | 'reject'; opinion?: string }
): Promise<ReviewDecisionResult> {
  return request<ReviewDecisionResult>({
    url: `/admin/review/tickets/${ticketNo}/decide`,
    method: 'post',
    data: payload
  })
}