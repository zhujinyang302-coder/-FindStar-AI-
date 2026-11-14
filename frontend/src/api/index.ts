import { request } from './client'
import client from './client'
import type { LoginResult } from '@/types'

export function login(email: string, password: string): Promise<LoginResult> {
  return request<LoginResult>({ url: '/auth/login', method: 'post', data: { email, password } })
}

export { client }
export * from './public'
export * from './items'
export * from './matches'
export * from './drafts'
export * from './contacts'
export * from './notifications'
export * from './adminReview'
export * from './adminQuality'
export * from './adminRecords'