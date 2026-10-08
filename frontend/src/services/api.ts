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

function getToken(path?: string): string | null {
  try {
    // 后台接口（/api/admin，M11 / V5.0 M4）使用管理员独立会话；
    // 其余接口使用用户会话（bf_token）。两者互不混用，否则后台请求会被 require_admin 拒绝。
    if (path && path.startsWith('/api/admin')) {
      return Taro.getStorageSync('bf_admin_token') || null
    }
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

// ---------- M0-04 邀请归因（V5.0）：分享链接带邀请码 → 落地后暂存 → 登录时自动携带 ----------
// 分享出去的卡片链接形如 https://host/?inviter=BF-7Q2X9。被邀请人可能先逛半天再登录，
// 所以邀请码必须在**首次落地**时立刻落盘，否则登录时早已丢失，邀请关系永远绑不上。
const INVITE_KEY = 'bf_inviter_code'

function normalizeCode(raw: unknown): string | null {
  const v = String(raw ?? '').trim().toUpperCase()
  return /^[A-Z0-9-]{3,32}$/.test(v) ? v : null
}

/** 冷启动调用：从落地 URL 抓取邀请码并暂存（已有暂存则不覆盖，先到先得）。 */
export function captureInviterCode(): string | null {
  try {
    let code: string | null = null
    // H5：优先用 query string；小程序 / 其它端兜底 Taro 路由参数
    const search = typeof window !== 'undefined' ? window.location.search : ''
    if (search) {
      const q = new URLSearchParams(search)
      code = normalizeCode(q.get('inviter') ?? q.get('invite') ?? q.get('code'))
    }
    if (!code) {
      const params = (Taro.getCurrentInstance()?.router?.params || {}) as Record<string, string>
      code = normalizeCode(params.inviter ?? params.invite ?? params.code)
    }
    if (!code) return getInviterCode()
    if (!getInviterCode()) Taro.setStorageSync(INVITE_KEY, code)
    return code
  } catch {
    return null
  }
}

export function getInviterCode(): string | null {
  try {
    return Taro.getStorageSync(INVITE_KEY) || null
  } catch {
    return null
  }
}

export function clearInviterCode(): void {
  try {
    Taro.removeStorageSync(INVITE_KEY)
  } catch {
    /* 忽略 */
  }
}

// 登录接口自动补邀请码：两条登录路径（手机号 / 微信）共用，避免只改一处留下死角
const AUTH_LOGIN_PATHS = ['/api/auth/login', '/api/auth/wechat']

function withInviterCode(path: string, options: RequestInit): RequestInit {
  const isLogin = options.method === 'POST' && AUTH_LOGIN_PATHS.some((p) => path.startsWith(p))
  if (!isLogin) return options
  const code = getInviterCode()
  if (!code) return options
  try {
    const payload = options.body ? (JSON.parse(String(options.body)) as Record<string, unknown>) : {}
    if (payload.inviterCode) return options
    return { ...options, body: JSON.stringify({ ...payload, inviterCode: code }) }
  } catch {
    return options
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
  const token = getToken(path)
  if (token) headers['Authorization'] = `Bearer ${token}`
  const guest = getGuestToken()
  if (guest) headers['X-Guest-Token'] = guest

  // M0-04：登录请求自动携带暂存的邀请码（分享落地 → 延迟登录也能正确归因）
  const finalOptions = withInviterCode(path, options)

  let res: Response
  try {
    res = await fetch(resolveUrl(path), { ...finalOptions, headers })
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
  // 邀请码一旦成功用于登录即可清除，避免污染后续其它账号的登录
  if (finalOptions !== options) clearInviterCode()
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
