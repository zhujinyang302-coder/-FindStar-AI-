import { request } from './client'
import type { MatchConfigVersion, MatchConfigVersionList, QualityMetrics } from '@/types'

export function fetchQualityMetrics(params?: {
  from?: string
  to?: string
  direction?: 'lost_to_found' | 'found_to_lost'
}): Promise<QualityMetrics> {
  return request<QualityMetrics>({ url: '/admin/quality/metrics', params })
}

export function fetchConfigVersions(): Promise<MatchConfigVersionList> {
  return request<MatchConfigVersionList>({ url: '/admin/quality/config-versions' })
}

export function createConfigVersion(payload: {
  threshold: number
  quota: number
  time_window_days: number
  weights?: Record<string, number>
  reason: string
}): Promise<MatchConfigVersion> {
  return request<MatchConfigVersion>({
    url: '/admin/quality/config-versions',
    method: 'post',
    data: payload
  })
}