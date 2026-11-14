import { request } from './client'
import type {
  CandidateDetail,
  CandidateSummaryList,
  ExplanationResult,
  FeedbackType,
  MatchAccepted,
  MatchBatchInfo,
  MyBatchList
} from '@/types'

export function createMatch(payload: {
  lost_item_id?: number
  found_item_id?: number
}): Promise<MatchAccepted> {
  return request<MatchAccepted>({ url: '/matches', method: 'post', data: payload })
}

export function rematch(payload: {
  lost_item_id?: number
  found_item_id?: number
}): Promise<MatchAccepted> {
  return request<MatchAccepted>({ url: '/matches/rematch', method: 'post', data: payload })
}

export function fetchMyBatches(params?: {
  status?: string
  page?: number
  page_size?: number
}): Promise<MyBatchList> {
  return request<MyBatchList>({ url: '/matches/my', params })
}

export function fetchBatch(batchId: string): Promise<MatchBatchInfo> {
  return request<MatchBatchInfo>({ url: `/matches/batches/${batchId}` })
}

export function fetchCandidates(
  batchId: string,
  params?: {
    category?: string
    color?: string
    time_from?: string
    time_to?: string
    area_code?: string
    keyword?: string
  }
): Promise<CandidateSummaryList> {
  return request<CandidateSummaryList>({
    url: `/matches/batches/${batchId}/candidates`,
    params
  })
}

export function fetchCandidateDetail(
  batchId: string,
  candidatePublicId: string
): Promise<CandidateDetail> {
  return request<CandidateDetail>({
    url: `/matches/batches/${batchId}/candidates/${candidatePublicId}`
  })
}

export function fetchExplanation(candidatePublicId: string): Promise<ExplanationResult> {
  return request<ExplanationResult>({
    url: `/matches/candidates/${candidatePublicId}/explanation`
  })
}

export function sendFeedback(
  candidatePublicId: string,
  payload: { feedback_type: FeedbackType; note?: string }
): Promise<{ feedback_id: number; recorded: boolean }> {
  return request({
    url: `/matches/candidates/${candidatePublicId}/feedback`,
    method: 'post',
    data: payload
  })
}