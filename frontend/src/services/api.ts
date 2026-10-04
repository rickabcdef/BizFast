// 统一 API 客户端：fetch 封装，注入 Token、统一错误处理、进度轮询。
// 所有错误提示中文化（见 docs/api-contract.md 与 types/ERROR_MESSAGES）。
import { ERROR_MESSAGES, type ApiResult } from '@/types'

const BASE = (typeof API_BASE !== 'undefined' ? API_BASE : '/api') as string

function getToken(): string | null {
  try {
    return Taro.getStorageSync('bf_token') || null
  } catch {
    return null
  }
}

export class BizError extends Error {
  code: number
  constructor(code: number, message: string) {
    super(message)
    this.code = code
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options.headers as Record<string, string>) || {})
  }
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, { ...options, headers })
  } catch {
    throw new BizError(50001, ERROR_MESSAGES[50001])
  }

  let body: ApiResult<T>
  try {
    body = (await res.json()) as ApiResult<T>
  } catch {
    throw new BizError(50001, ERROR_MESSAGES[50001])
  }

  if (body.code !== 0) {
    const msg = body.message || ERROR_MESSAGES[body.code] || ERROR_MESSAGES[50001]
    throw new BizError(body.code, msg)
  }
  return body.data
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: 'GET' }),
  post: <T>(path: string, data?: unknown) =>
    request<T>(path, { method: 'POST', body: data ? JSON.stringify(data) : undefined }),
  // 轮询进度：直到 predicate 为真或超时
  async poll<T>(
    path: string,
    predicate: (d: T) => boolean,
    intervalMs = 2000,
    timeoutMs = 180000
  ): Promise<T> {
    const start = Date.now()
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const d = await api.get<T>(path)
      if (predicate(d)) return d
      if (Date.now() - start > timeoutMs) return d
      await new Promise((r) => setTimeout(r, intervalMs))
    }
  }
}

export default api
