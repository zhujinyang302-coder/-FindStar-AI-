// 时间格式化工具。
// 后端统一存储 UTC naive 时间；展示时转换为浏览器本地时间。

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '时间未知'
  const hasZone = value.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(value)
  const date = new Date(hasZone ? value : `${value}Z`)
  if (Number.isNaN(date.getTime())) return value
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours()
  )}:${pad(date.getMinutes())}`
}

export function toUtcIso(local: string | null | undefined): string | null {
  if (!local) return null
  const date = new Date(local)
  if (Number.isNaN(date.getTime())) return null
  return date.toISOString()
}

export const CATEGORIES: string[] = [
  '电子产品',
  '数码配件',
  '证件卡类',
  '钥匙',
  '钱包箱包',
  '衣物',
  '书籍文具',
  '水杯餐具',
  '雨具',
  '运动器材',
  '首饰配饰',
  '其他',
  '未知'
]

const STATUS_MAP: Record<string, string> = {
  pending_listing: '待上架审核',
  active: '已上架',
  listing_rejected: '上架驳回',
  delisting_review: '下架审核中',
  delisted: '已下架',
  claimed: '已认领',
  resolved: '已完成',
  closed: '已关闭',
  processing: '匹配处理中',
  completed: '匹配完成',
  no_candidates: '暂无可靠候选',
  degraded_completed: '降级完成',
  invalidated: '已失效',
  expired: '已过期',
  archived: '已归档',
  pending: '待处理',
  confirmed: '已确认',
  rejected: '已拒绝'
}

export function statusLabel(status: string): string {
  return STATUS_MAP[status] || status
}

export function statusTagType(status: string): 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  if (['active', 'completed', 'confirmed', 'resolved', 'claimed'].includes(status)) return 'success'
  if (['pending_listing', 'delisting_review', 'processing', 'pending'].includes(status)) return 'warning'
  if (['listing_rejected', 'rejected', 'invalidated', 'expired'].includes(status)) return 'danger'
  return 'info'
}

export function areaLabel(areaName: string | null | undefined): string {
  return areaName || '校园内'
}