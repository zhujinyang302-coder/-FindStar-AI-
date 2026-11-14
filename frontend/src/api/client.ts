import axios, { type AxiosError, type AxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'

interface ApiEnvelope<T> {
  code: number | string
  message: string
  data: T
  request_id?: string
}

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 30000
})

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('findstar_token')
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function messageForStatus(status: number, fallback: string): string {
  switch (status) {
    case 401:
      return fallback || '请先登录'
    case 403:
      return fallback || '当前角色无权执行该操作'
    case 404:
      return '记录不存在或对您不可见'
    case 409:
      return fallback || '操作冲突，请刷新后重试'
    case 410:
      return fallback || '该功能或结果已过期，请重新发起'
    case 429:
      return fallback || '操作过于频繁，请稍后再试'
    default:
      return fallback || '请求失败，请稍后重试'
  }
}

client.interceptors.response.use(
  (response) => {
    const body = response.data
    if (body && typeof body === 'object' && 'code' in body) {
      const envelope = body as ApiEnvelope<unknown>
      if (envelope.code === 0) {
        return envelope.data as never
      }
      return Promise.reject(new Error(envelope.message))
    }
    return body
  },
  (error: AxiosError<ApiEnvelope<unknown>>) => {
    const status = error.response?.status ?? 0
    const payload = error.response?.data
    const message = messageForStatus(status, payload?.message || '')
    const requestId = payload?.request_id || (error.response?.headers?.['x-request-id'] as string)
    const suffix = requestId ? `（追踪号 ${requestId}）` : ''

    if (status === 401 && !error.config?.url?.includes('/auth/login')) {
      localStorage.removeItem('findstar_token')
      localStorage.removeItem('findstar_user')
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }
    ElMessage.error(`${message}${suffix}`)
    return Promise.reject(new ApiError(message, status))
  }
)

export async function request<T>(config: AxiosRequestConfig): Promise<T> {
  return (await client.request(config)) as unknown as T
}

export default client