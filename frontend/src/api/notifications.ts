import { request } from './client'
import type { NotificationList } from '@/types'

export function fetchNotifications(params?: {
  page?: number
  page_size?: number
}): Promise<NotificationList> {
  return request<NotificationList>({ url: '/notifications', params })
}

export function fetchUnreadCount(): Promise<{ unread_count: number }> {
  return request({ url: '/notifications/unread-count' })
}

export function markNotificationRead(id: number): Promise<{ id: number; is_read: boolean }> {
  return request({ url: `/notifications/${id}/read`, method: 'post' })
}

export function markAllNotificationsRead(): Promise<{ updated: number }> {
  return request({ url: '/notifications/read-all', method: 'post' })
}