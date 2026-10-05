// 统一 API 客户端：fetch 封装，注入 Token、统一错误处理、进度轮询。
// 所有错误提示中文化（见 docs/api-contract.md 与 types/ERROR_MESSAGES）。
import Taro from '@tarojs/taro'
import { ERROR_MESSAGES, type ApiResult } from '@/types'

// API_BASE 有两种约定，均需支持：
//   1) 后端源地址，如 http://127.0.0.1:8000  → 拼 /api/...
//   2) 网关前缀（H5 由 nginx 反代），如 /api 或留空 → 直接用 /api/...
// 契约（docs/api-contract.md）中所有 path 均以 /api 开头。
const RAW_BASE = (typeof API_BASE !== 'undefined' ? API_BASE : '') as string
const ORIGIN = RAW_BASE.replace(/\/+$/, '')

export function resolveUrl(path: string): string {
  if (!ORIGIN || ORIGIN === '/api') {
    return path.startsWith('/api') ? path : `/api${path}`
  }
  return `${ORIGIN}${path}`
}

function getToken(): string | null {
  try {
    return Taro.getStorageSync('bf_token') || null
  } catch {
    return null
  }
}

// 游客身份（M1-07）：后端在响应头 X-Guest-Token 下发，前端必须持久化并回传，
// 否则每次请求都会被当成新游客，订单 / 收藏 / 消息将查不到（联调必踩的坑）。
const GUEST_KEY = 'bf_guest_token'

function getGuestToken(): string | null {
  try {
    return Taro.getStorageSync(GUEST_KEY) || null
  } catch {
    return null
  }
}

function saveGuestToken(res: Response): void {
  try {
    const t = res.headers.get('X-Guest-Token')
    if (t && t !== getGuestToken()) Taro.setStorageSync(GUEST_KEY, t)
  } catch {
    /* 存储失败不阻断主流程 */
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
  const guest = getGuestToken()
  if (guest) headers['X-Guest-Token'] = guest

  let res: Response
  try {
    res = await fetch(resolveUrl(path), { ...options, headers })
  } catch {
    throw new BizError(50001, ERROR_MESSAGES[50001])
  }
  // 首次访问由后端生成游客标识，这里落盘，后续请求复用同一身份
  saveGuestToken(res)

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
  put: <T>(path: string, data?: unknown) =>
    request<T>(path, { method: 'PUT', body: data ? JSON.stringify(data) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
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
