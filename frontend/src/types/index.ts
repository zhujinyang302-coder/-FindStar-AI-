export interface UserInfo {
  id: number
  nickname: string
  role: 'user' | 'admin'
}

export interface LoginResult {
  access_token: string
  token_type: string
  user: UserInfo
}

export interface ImageOut {
  id: number
  object_key: string
  url: string
  mime_type: string
  size_bytes: number
}

export interface ScorePart {
  score: number
  weight: number
  available: boolean
  note: string | null
}

export interface ScoreBreakdown {
  text: ScorePart
  image: ScorePart
  location: ScorePart
  time: ScorePart
  attribute: ScorePart
}

export interface DifferenceItem {
  field: string
  self_value: string | null
  candidate_value: string | null
  note: string
}

export type ItemType = 'lost' | 'found'

export type ItemStatus =
  | 'pending_listing'
  | 'active'
  | 'listing_rejected'
  | 'delisting_review'
  | 'delisted'
  | 'claimed'
  | 'resolved'
  | 'closed'

export type BatchStatus =
  | 'processing'
  | 'completed'
  | 'no_candidates'
  | 'degraded_completed'
  | 'invalidated'
  | 'expired'
  | 'archived'

export type DisclosureLevel = 'summary' | 'verified' | 'handover'

export type FeedbackType =
  | 'not_mine'
  | 'not_target'
  | 'inaccurate'
  | 'suspected_impersonation'

export interface LatestReview {
  status: string
  opinion: string | null
  decided_at: string | null
}

export interface MatchSummary {
  last_batch_id: string | null
  candidate_count: number
  degraded: boolean
  expires_at: string | null
}

export interface ContactSummary {
  pending_received: number
}

export interface MyItemOut {
  id: number
  type: ItemType
  status: ItemStatus
  info_sufficient: boolean
  review_ticket_no: string | null
  data_version: number
  created_at: string
}

export interface MyItemListItem {
  id: number
  type: ItemType
  title: string
  category: string
  status: ItemStatus
  review_round: number
  latest_review: LatestReview | null
  match_summary: MatchSummary | null
  contact_summary: ContactSummary | null
  cover_image: string | null
  created_at: string
  updated_at: string
}

export interface MyItemListResult {
  items: MyItemListItem[]
  total: number
  page: number
  page_size: number
}

export interface MyItemDetail {
  id: number
  type: ItemType
  title: string
  description: string
  category: string
  color: string | null
  brand: string | null
  location_code: string
  location_text: string
  occurred_at: string | null
  status: ItemStatus
  info_sufficient: boolean
  review_round: number
  can_match: boolean
  can_edit: boolean
  can_withdraw: boolean
  can_request_delist: boolean
  latest_review: LatestReview | null
  images: ImageOut[]
  created_at: string
  updated_at: string
}

export interface CreateItemPayload {
  title: string
  description: string
  category: string
  color?: string | null
  brand?: string | null
  location_code?: string | null
  location_text: string
  occurred_at?: string | null
  image_keys: string[]
  matching_notice_accepted: boolean
}

export interface UploadResult {
  object_key: string
  thumb_key: string | null
  mime_type: string
  size_bytes: number
  url: string
  thumb_url: string | null
}

export interface ItemFeatures {
  category: string
  color: string | null
  brand: string | null
  visible_features: string[]
  description: string
  confidence: number
  unknown_fields: string[]
}

export interface ExtractFeaturesResult {
  features: ItemFeatures
  warnings: string[]
  provider: string
  degraded: boolean
  degraded_reason: string | null
}

export interface CandidateSummary {
  candidate_public_id: string
  item_type: ItemType
  category: string
  color: string | null
  brand: string | null
  area_name: string
  occurred_on: string | null
  title_excerpt: string
  description_excerpt: string
  thumb_url: string | null
  score: number
  score_breakdown: ScoreBreakdown
  differences: DifferenceItem[]
  requires_offline_verification: boolean
  explanation_status: 'ready' | 'unavailable'
  reasons: string[]
}

export interface CandidateSummaryList {
  batch_id: string
  disclosure_level: DisclosureLevel
  candidates: CandidateSummary[]
  filtered_total: number
  total: number
  sort_note: string
  disclaimer: string
}

export interface CandidateDetail extends CandidateSummary {
  occurred_window: string | null
  location_text: string | null
  visible_features: string[]
  handover_location_code?: string | null
  handover_window_start?: string | null
  handover_window_end?: string | null
  handover_note?: string | null
}

export interface ExplanationResult {
  candidate_public_id: string
  score: number
  score_breakdown: ScoreBreakdown
  reasons: string[]
  differences: DifferenceItem[]
  explanation_status: 'ready' | 'unavailable'
  disclaimer: string
}

export interface MatchAccepted {
  batch_id: string
  status: BatchStatus
  reused: boolean
  accepted_at: string
}

export interface MatchBatchInfo {
  batch_id: string
  initiated_item_type: ItemType
  initiated_item_id: number
  status: BatchStatus
  candidate_count: number
  degraded: boolean
  degraded_reason: string | null
  recall_channel: string | null
  threshold: number | null
  quota: number | null
  algorithm_version: string | null
  config_version: string | null
  created_at: string | null
  completed_at: string | null
  expires_at: string | null
  message: string | null
}

export interface MyBatchItem {
  batch_id: string
  initiated_item_id: number
  initiated_item_type: ItemType
  status: BatchStatus
  candidate_count: number
  degraded: boolean
  created_at: string
  expires_at: string | null
  can_rematch: boolean
}

export interface MyBatchList {
  items: MyBatchItem[]
  total: number
}

export interface ContactRequestItem {
  id: number
  request_type: 'claim' | 'return_clue'
  batch_id: string
  candidate_public_id: string
  target_item_type: ItemType
  target_item_id: number
  status: 'pending' | 'confirmed' | 'rejected' | 'closed'
  created_at: string
  decided_at: string | null
}

export interface ContactRequestList {
  items: ContactRequestItem[]
  total: number
}

export interface ReceivedContactItem {
  id: number
  request_type: 'claim' | 'return_clue'
  target_item_title: string
  candidate_summary: CandidateSummary | null
  private_verification: string | null
  handover_location_code: string | null
  handover_window_start: string | null
  handover_window_end: string | null
  handover_note: string | null
  status: 'pending' | 'confirmed' | 'rejected' | 'closed'
  sensitive_category: boolean
  created_at: string
}

export interface ReceivedContactList {
  items: ReceivedContactItem[]
  total: number
}

export interface ContactRequestDetail extends ReceivedContactItem {
  batch_id: string
  candidate_public_id: string
  target_item_type: ItemType
  target_item_id: number
  decision_note: string | null
  failure_count: number
  cooldown_until: string | null
  decided_at: string | null
}

export interface NotificationItem {
  id: number
  type: string
  title: string
  body: string
  ref_type: string | null
  ref_id: number | null
  is_read: boolean
  created_at: string
}

export interface NotificationList {
  items: NotificationItem[]
  total: number
  unread_count: number
}

export interface ReviewQueueItem {
  ticket_no: string
  review_type: 'listing' | 'delisting'
  source: string
  item_type: ItemType
  item_id: number
  item_title: string
  status: string
  waiting_minutes: number
  overdue: boolean
  created_at: string
}

export interface ReviewQueue {
  items: ReviewQueueItem[]
  total: number
}

export interface ReviewTicketDetail {
  ticket_no: string
  review_type: 'listing' | 'delisting'
  source: string
  status: string
  item_type: ItemType
  item_id: number
  item_title: string
  item_category: string
  item_description: string
  location_text: string
  occurred_at: string | null
  images: ImageOut[]
  compliance_checks: { key: string; passed: boolean; note: string | null }[]
  history: { review_round: number; status: string; opinion: string | null; decided_at: string | null }[]
  disclaimer: string
}

export interface ReviewDecisionResult {
  ticket_no: string
  status: string
  item_status: ItemStatus
  decided_at: string
  match_task_created: boolean
  impact: Record<string, unknown>
}

export interface QualityMetrics {
  match_requests: number
  no_candidate_rate: number
  top3_hit_rate: number
  user_false_positive_rate: number
  degraded_rate: number
  candidate_p95_ms: number
  period_label: string
  generated_at: string
  note: string
}

export interface MatchConfigVersion {
  version: string
  threshold: number
  quota: number
  time_window_days: number
  weights: Record<string, number> | null
  recall_strategy: string
  changed_by: number | null
  reason: string | null
  active: boolean
  created_at: string
}

export interface MatchConfigVersionList {
  items: MatchConfigVersion[]
}

export interface PublicStats {
  completed_total: number
  generated_at: string
  disclaimer: string
}