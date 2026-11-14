import { request } from './client'
import type {
  DraftCreated,
  DraftDetail,
  DraftPreview,
  MyDraftItem,
  PublishMode,
  PublishResult
} from '@/types/drafts'

export function createLostDraft(data: Record<string, unknown>): Promise<DraftCreated> {
  return request<DraftCreated>({ url: '/lost-item-drafts', method: 'post', data })
}

export function fetchPublishMode(): Promise<PublishMode> {
  return request<PublishMode>({ url: '/config/publish-mode', method: 'get' })
}

export function fetchDraft(draftId: string): Promise<DraftDetail> {
  return request<DraftDetail>({ url: `/lost-item-drafts/${draftId}`, method: 'get' })
}

export function fetchDraftPreview(draftId: string): Promise<DraftPreview> {
  return request<DraftPreview>({
    url: `/lost-item-drafts/${draftId}/preview`,
    method: 'get'
  })
}

export function publishDraft(draftId: string): Promise<PublishResult> {
  return request<PublishResult>({
    url: `/lost-item-drafts/${draftId}/publish`,
    method: 'post'
  })
}

export function abandonDraft(draftId: string): Promise<{ draft_id: string; status: string }> {
  return request<{ draft_id: string; status: string }>({
    url: `/lost-item-drafts/${draftId}/abandon`,
    method: 'post'
  })
}

export function fetchMyDrafts(params?: {
  page?: number
  page_size?: number
}): Promise<{ items: MyDraftItem[]; total: number }> {
  return request<{ items: MyDraftItem[]; total: number }>({
    url: '/my/drafts',
    method: 'get',
    params
  })
}