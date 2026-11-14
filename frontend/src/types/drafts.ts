export interface DraftCreated {
  draft_id: string
  status: string
  preview_batch_id: string | null
  expires_at: string
  created_at: string
  idempotent_replay: boolean
}

export interface DraftCandidate {
  candidate_public_id: string
  item_type: string
  category: string
  color: string | null
  brand: string | null
  area_name: string
  occurred_on: string | null
  title_excerpt: string
  description_excerpt: string
  thumb_url: string | null
  score: number
  score_breakdown: Record<string, unknown>
  differences: unknown[]
  requires_offline_verification: boolean
  explanation_status: string
  reasons: string[]
  low_similar: boolean
  threshold: number
  threshold_source: string
}

export interface DraftPreview {
  draft_id: string
  batch_id: string | null
  status: string
  candidate_count: number
  degraded: boolean
  degraded_reason: string | null
  threshold: number
  threshold_source: string
  sort_note: string
  disclaimer: string
  candidates: DraftCandidate[]
  expires_at: string | null
}

export interface DraftDetail {
  draft_id: string
  title: string
  description: string
  category: string
  color: string | null
  brand: string | null
  location_code: string | null
  location_text: string
  occurred_at: string | null
  status: string
  expires_at: string
  created_at: string
  preview_batch_id: string | null
  candidate_count: number
  can_publish: boolean
}

export interface MyDraftItem {
  draft_id: string
  title: string
  status: string
  created_at: string
  expires_at: string
  remaining_seconds: number
  candidate_count: number
  can_publish: boolean
}

export interface PublishResult {
  item_id: number
  item_type: string
  status: string
  review_ticket_no: string | null
  data_version: number
  batch_id: string | null
  preview_reused: boolean
  publish_flow: string
}

export interface PublishMode {
  publish_mode: 'match_first' | 'direct'
}