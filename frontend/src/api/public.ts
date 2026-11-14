import { request } from './client'
import type { PublicStats } from '@/types'

export function fetchPublicStats(): Promise<PublicStats> {
  return request<PublicStats>({ url: '/public/stats' })
}