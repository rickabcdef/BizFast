// ===================================================================
// BizFast 运营管理后台 · 数据层（真实后端 /api/admin）
// 独立于用户端登录态；契约见 backend/app/routers/admin.py。
// 所有写操作在后端写入审计日志（M11-08）。
// ===================================================================
import { ElMessage } from 'element-plus'

export type AdminRole = 'admin' | 'operator' | 'support' | 'finance'
export type ReviewStatus = 'pending' | 'passed' | 'rejected'
export type OrderStatus = 'pending' | 'paid' | 'generating' | 'delivered' | 'refunded' | 'closed'

export interface AdminUser {
  id: string
  phone: string
  nickname: string
  city: string
  memberStatus: 'none' | 'single' | 'month' | 'year'
  memberLabel: string
  orderCount: number
  totalSpendYuan: number
  createdAt: string
  riskFlag: boolean
  source: string // 来源渠道（邀请注册 / 埋点渠道 / 自然流量）
  inviterPhone: string // M0-04：邀请人手机号（已脱敏），非邀请注册为空
}

export interface AdminOrder {
  id: string
  userId: string
  userPhone: string
  plan: string
  planName: string
  amountYuan: number
  status: OrderStatus
  statusLabel: string
  channel: string
  createdAt: string
  paidAt: string | null
  refundRequested: boolean
  refundReason: string | null
  downloaded: boolean // V5.0 M2-05：交付物是否已被下载（决定退款走自助还是人工审核）
  abnormal: boolean // 异常订单（已支付未交付 / 支付回调缺失 / 退款待审核）
  abnormalType: string | null // paid_no_delivery | callback_missing | refund_review
  abnormalHandled: boolean // M2-03：人工已标记处理（处理后不再红色高亮）
}

export interface AdminOpportunity {
  id: string
  title: string
  category: string
  city: string
  capitalMin: number
  capitalMax: number
  paybackMonths: number
  marginPercent: number
  difficultyStars: number
  source: string
  status: ReviewStatus
  statusLabel: string
  onShelf: boolean // 上下架
  createdAt: string
}

export interface PromptVersion {
  version: number
  content: string
  model: string
  updatedAt: string
  operator: string
}

export interface PromptItem {
  key: string
  name: string
  content: string
  model: string
  updatedAt: string
  versions: PromptVersion[]
}

export interface ReviewItem {
  id: string
  type: string
  content: string
  result: string | null
  status: ReviewStatus
  statusLabel: string
  reason: string | null
  appeal: boolean // 是否申诉
  appealReason: string | null
  createdAt: string
}

export interface RoleItem {
  role: AdminRole
  name: string
  description: string
  perms: { key: string; label: string; enabled: boolean }[]
}

export interface AuditLogItem {
  id: string
  operator: string
  role: string
  action: string
  target: string
  detail: string
  createdAt: string
}

export interface DashboardKpis {
  diagnoseCount: number
  payCount: number
  revenueYuan: number
  refundRate: string
  conversionRate: string
  packageDoneRate: string
  avgOrderYuan: string
}

export interface DashboardTrend {
  label: string // 日期 / 周 / 月
  orders: number
  revenue: number
}

export interface OpsSlot {
  id: string
  name: string
  type: 'recommend' | 'popup' | 'coupon'
  title: string
  content: string
  enabled: boolean
  startAt: string
  endAt: string
  updatedAt: string
}

export interface PageBox<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
}

// ---------------- 请求封装（统一信封 + 中文错误 + 鉴权头） ----------------

// 后端基址：生产由 nginx 反代 /api 到后端（infra/nginx.conf），
// 开发由 vite.config.ts 的 server.proxy 转发；也可用 VITE_API_BASE 覆盖。
const RAW_BASE = ((import.meta as any).env?.VITE_API_BASE as string | undefined) || ''
const ORIGIN = RAW_BASE.replace(/\/+$/, '')

function resolveUrl(path: string): string {
  if (!ORIGIN) return path.startsWith('/api') ? path : `/api${path}`
  return `${ORIGIN}${path}`
}

export const ADMIN_TOKEN_KEY = 'bizfast_admin_token' // 独立于用户端登录态（M10/用户端不使用该 key）
export const ADMIN_SESSION_KEY = 'bizfast_admin_session'

export interface AdminSession {
  token: string
  name: string
  username: string
  role: AdminRole
  loginAt: string
}

interface Envelope<T> {
  code: number
  message: string
  data: T
  request_id: string
}

function buildQuery(params?: Record<string, unknown>): string {
  const pairs: string[] = []
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v === undefined || v === null || v === '') return
    pairs.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
  })
  return pairs.length ? `?${pairs.join('&')}` : ''
}

async function request<T>(path: string, options: RequestInit = {}, silent = false): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options.headers as Record<string, string>) || {})
  }
  const token = localStorage.getItem(ADMIN_TOKEN_KEY)
  if (token) headers.Authorization = `Bearer ${token}`

  let res: Response
  try {
    res = await fetch(resolveUrl(path), { ...options, headers })
  } catch {
    const msg = '网络连接失败，请检查后端服务是否已启动'
    if (!silent) ElMessage.error(msg)
    throw new Error(msg)
  }

  let body: Envelope<T>
  try {
    body = (await res.json()) as Envelope<T>
  } catch {
    const msg = '服务器返回异常，请稍后重试'
    if (!silent) ElMessage.error(msg)
    throw new Error(msg)
  }

  if (body && typeof body.code === 'number' && body.code !== 0) {
    const err: any = new Error(body.message || '操作失败，请重试')
    err.code = body.code
    if (body.code === 40101) {
      // 登录态失效：清掉会话，回到登录页
      clearAdminSession()
      if (!location.hash.includes('/login')) location.hash = '#/login'
    }
    if (!silent) ElMessage.error(err.message)
    throw err
  }

  return (body?.data ?? ({} as T)) as T
}

// ---------------- 登录与会话（独立登录态 + TOTP 二次验证） ----------------

export async function adminLoginStep1(username: string, password: string): Promise<{ needTotp: boolean; totpHint: string }> {
  return request<{ needTotp: boolean; totpHint: string }>('/api/admin/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password })
  })
}

export async function adminLoginStep2(username: string, totp: string, _hint?: string): Promise<AdminSession> {
  const session = await request<AdminSession>('/api/admin/auth/verify-2fa', {
    method: 'POST',
    body: JSON.stringify({ username, totp })
  })
  setAdminSession(session)
  return session
}

export function getAdminSession(): AdminSession | null {
  try {
    const raw = localStorage.getItem(ADMIN_SESSION_KEY)
    return raw ? (JSON.parse(raw) as AdminSession) : null
  } catch {
    return null
  }
}

export function setAdminSession(s: AdminSession): void {
  localStorage.setItem(ADMIN_TOKEN_KEY, s.token)
  localStorage.setItem(ADMIN_SESSION_KEY, JSON.stringify(s))
}

export function clearAdminSession(): void {
  localStorage.removeItem(ADMIN_TOKEN_KEY)
  localStorage.removeItem(ADMIN_SESSION_KEY)
}

// ---------------- M11-05 数据看板（日 / 周 / 月） ----------------

export type TrendGranularity = 'day' | 'week' | 'month'

export async function getAdminDashboard(granularity: TrendGranularity = 'day'): Promise<{
  kpis: DashboardKpis
  trend: DashboardTrend[]
  refreshAt: string
}> {
  return request(`/api/admin/dashboard${buildQuery({ granularity })}`)
}

// ---------------- M11-01 用户管理（详情含全部订单与启动包记录） ----------------

export async function getAdminUsers(params: { page?: number; pageSize?: number; keyword?: string; memberStatus?: string; source?: string }): Promise<PageBox<AdminUser>> {
  return request(`/api/admin/users${buildQuery({ ...params })}`)
}

export async function getAdminUserDetail(userId: string): Promise<{
  user: AdminUser
  orders: AdminOrder[]
  packages: { orderId: string; name: string; fileCount: number; status: string; createdAt: string }[]
}> {
  const d = await request<{
    user: AdminUser
    orders: AdminOrder[]
    packages: { orderId: string; name: string; fileCount: number; status: string; createdAt: string }[]
  }>(`/api/admin/users/${encodeURIComponent(userId)}`)
  return { ...d, orders: (d.orders || []).map(localizeOrder) }
}

// ---------------- M11-02 订单管理（异常标红告警 / 退款 / 对账导出） ----------------

export async function getAdminOrders(params: { page?: number; pageSize?: number; status?: string; keyword?: string; abnormal?: boolean; channel?: string }): Promise<PageBox<AdminOrder>> {
  const q: Record<string, unknown> = { ...params }
  if (params.abnormal === false) delete q.abnormal
  const d = await request<PageBox<AdminOrder>>(`/api/admin/orders${buildQuery(q)}`)
  return { ...d, items: (d.items || []).map(localizeOrder) }
}

export async function processRefund(_session: AdminSession, orderId: string, action: 'approve' | 'reject', reason?: string): Promise<{ orderId: string; status: OrderStatus; message: string }> {
  return request(`/api/admin/orders/${encodeURIComponent(orderId)}/refund`, {
    method: 'PUT',
    body: JSON.stringify({ action, reason })
  })
}

// M2-03（V5.0）：人工标记异常订单已处理（写事件 + 关闭关联告警）
export async function resolveAdminOrder(orderId: string, note?: string): Promise<{ orderId: string; handled: boolean; message: string }> {
  return request(`/api/admin/orders/${encodeURIComponent(orderId)}/resolve`, {
    method: 'POST',
    body: JSON.stringify({ note })
  })
}

export const ORDER_ABNORMAL_LABEL: Record<string, string> = {
  paid_no_delivery: '已支付未交付（超 2 小时）',
  callback_missing: '支付回调缺失',
  // V5.0 M2-05：交付物已下载的退款申请必须人工审核
  refund_review: '退款待审核（交付物已下载）'
}

// 支付渠道：后端存英文标识，后台列表展示中文
export const ORDER_CHANNEL_LABEL: Record<string, string> = {
  wechat: '微信支付',
  alipay: '支付宝',
  apple: 'Apple 内购',
  huawei: '华为支付'
}

function localizeOrder(o: AdminOrder): AdminOrder {
  return { ...o, channel: ORDER_CHANNEL_LABEL[o.channel] || o.channel || '' }
}

// ---------------- M11-03 商机库管理（新增 / 编辑 / 上下架 / 批量导入 / 审核） ----------------

export async function getAdminOpportunities(params: { page?: number; pageSize?: number; status?: string; keyword?: string }): Promise<PageBox<AdminOpportunity>> {
  return request(`/api/admin/opportunities${buildQuery({ ...params })}`)
}

export async function saveOpportunity(_session: AdminSession, input: Partial<AdminOpportunity> & { id?: string }): Promise<AdminOpportunity> {
  const payload = {
    title: input.title || '',
    category: input.category || '未分类',
    city: input.city || '全国',
    capitalMin: Number(input.capitalMin) || 0,
    capitalMax: Number(input.capitalMax) || 0,
    paybackMonths: Number(input.paybackMonths) || 0,
    marginPercent: Number(input.marginPercent) || 0,
    difficultyStars: Number(input.difficultyStars) || 1
  }
  if (input.id) {
    return request(`/api/admin/opportunities/${encodeURIComponent(input.id)}`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    })
  }
  return request('/api/admin/opportunities', { method: 'POST', body: JSON.stringify(payload) })
}

export async function deleteOpportunity(_session: AdminSession, id: string): Promise<{ id: string; message: string }> {
  return request(`/api/admin/opportunities/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export async function toggleOpportunityShelf(_session: AdminSession, id: string, onShelf: boolean): Promise<{ id: string; onShelf: boolean; message: string }> {
  return request(`/api/admin/opportunities/${encodeURIComponent(id)}/shelf`, {
    method: 'PUT',
    body: JSON.stringify({ onShelf })
  })
}

export async function importOpportunities(_session: AdminSession, items: Partial<AdminOpportunity>[]): Promise<{ imported: number; rejected: number; errors: string[] }> {
  return request('/api/admin/opportunities/import', {
    method: 'POST',
    body: JSON.stringify({
      items: items.map((i) => ({
        title: i.title || '',
        category: i.category || '未分类',
        city: i.city || '全国',
        capitalMin: Number(i.capitalMin) || 0,
        capitalMax: Number(i.capitalMax) || 0,
        paybackMonths: Number(i.paybackMonths) || 0,
        marginPercent: Number(i.marginPercent) || 0,
        difficultyStars: Number(i.difficultyStars) || 1
      }))
    })
  })
}

export async function reviewOpportunity(_session: AdminSession, id: string, action: 'approve' | 'reject', reason?: string): Promise<{ id: string; status: ReviewStatus; message: string }> {
  return request(`/api/admin/opportunities/${encodeURIComponent(id)}/review`, {
    method: 'POST',
    body: JSON.stringify({ action, reason })
  })
}

// ---------------- M11-04 提示词配置（版本历史与一键回滚） ----------------

export async function getAdminPrompts(): Promise<{ items: PromptItem[]; notice: string }> {
  return request('/api/admin/prompts')
}

export async function saveAdminPrompt(_session: AdminSession, key: string, patch: { content?: string; model?: string }): Promise<PromptItem> {
  return request(`/api/admin/prompts/${encodeURIComponent(key)}`, {
    method: 'PUT',
    body: JSON.stringify(patch)
  })
}

export async function getPromptHistory(key: string): Promise<{ versions: PromptVersion[] }> {
  return request(`/api/admin/prompts/${encodeURIComponent(key)}/history`)
}

export async function rollbackPrompt(_session: AdminSession, key: string, version: number): Promise<PromptItem> {
  return request(`/api/admin/prompts/${encodeURIComponent(key)}/rollback`, {
    method: 'POST',
    body: JSON.stringify({ version })
  })
}

// ---------------- M11-06 / M11-09 内容审核（批量处理 / 申诉 / 一键下架） ----------------

export async function getAdminReviews(params: { page?: number; pageSize?: number; status?: string; keyword?: string }): Promise<PageBox<ReviewItem>> {
  return request(`/api/admin/reviews${buildQuery({ ...params })}`)
}

export async function reviewAction(_session: AdminSession, id: string, action: 'pass' | 'reject', reason?: string): Promise<{ id: string; status: ReviewStatus; message: string }> {
  return request(`/api/admin/reviews/${encodeURIComponent(id)}/action`, {
    method: 'POST',
    body: JSON.stringify({ action, reason })
  })
}

export async function batchReviewAction(_session: AdminSession, ids: string[], action: 'pass' | 'reject'): Promise<{ count: number; message: string }> {
  return request('/api/admin/reviews/batch', {
    method: 'POST',
    body: JSON.stringify({ ids, action })
  })
}

export async function appealReview(_session: AdminSession, id: string, action: 'approve' | 'reject'): Promise<{ id: string; status: ReviewStatus; message: string }> {
  return request(`/api/admin/reviews/${encodeURIComponent(id)}/appeal`, {
    method: 'POST',
    body: JSON.stringify({ action })
  })
}

export async function forceOfflineReview(_session: AdminSession, id: string): Promise<{ id: string; message: string }> {
  return request(`/api/admin/reviews/${encodeURIComponent(id)}/offline`, { method: 'POST' })
}

// ---------------- M11-07 权限管理（四角色：管理员 / 运营 / 客服 / 财务） ----------------

export type RolePerm = { key: string; label: string; enabled: boolean }

export async function getAdminRoles(): Promise<{ items: RoleItem[]; notice: string }> {
  return request('/api/admin/roles')
}

export async function saveAdminRole(_session: AdminSession, role: AdminRole, perms: RolePerm[]): Promise<RoleItem> {
  return request(`/api/admin/roles/${encodeURIComponent(role)}`, {
    method: 'PUT',
    body: JSON.stringify({ perms })
  })
}

// ---------------- M11-08 审计日志（保留 ≥ 180 天，不可篡改） ----------------

export async function getAdminAuditLogs(params: { page?: number; pageSize?: number; operator?: string; action?: string }): Promise<PageBox<AuditLogItem>> {
  return request(`/api/admin/audit${buildQuery({ ...params })}`)
}

export const ROLE_NAME: Record<AdminRole, string> = {
  admin: '管理员',
  operator: '运营',
  support: '客服',
  finance: '财务'
}

// ---------------- M11-10 运营位与活动配置（P2） ----------------

export async function getAdminOps(): Promise<{ items: OpsSlot[]; notice: string }> {
  return request('/api/admin/ops')
}

export async function saveAdminOps(_session: AdminSession, item: OpsSlot): Promise<OpsSlot> {
  return request(`/api/admin/ops/${encodeURIComponent(item.id)}`, {
    method: 'PUT',
    body: JSON.stringify({
      name: item.name,
      type: item.type,
      title: item.title,
      content: item.content,
      enabled: item.enabled,
      startAt: item.startAt,
      endAt: item.endAt
    })
  })
}

export async function toggleAdminOps(_session: AdminSession, id: string, enabled: boolean): Promise<{ id: string; message: string }> {
  return request(`/api/admin/ops/${encodeURIComponent(id)}/toggle`, {
    method: 'PUT',
    body: JSON.stringify({ enabled })
  })
}

// ---------------- M11-11 数据导出中心（P2，单次 ≤ 10 万条） ----------------

export async function exportCenterData(
  _session: AdminSession,
  kind: 'users' | 'orders' | 'deliveries' | 'events',
  format: 'csv' | 'json'
): Promise<{ fileName: string; content: string; message: string }> {
  return request(`/api/admin/export/${encodeURIComponent(kind)}${buildQuery({ format })}`)
}

// ---------------- 分享转化概览（M11-D） ----------------

export async function getAdminShareStats(): Promise<Record<string, unknown>> {
  return request('/api/admin/share/stats')
}

// ===================================================================
// V5.0 三块新看板：成本监控 / 转化漏斗 / 裂变数据
// ===================================================================

export interface CostBucket {
  tokens: number
  costCents: number
  costLabel: string
  calls: number
  revenueCents: number
  revenueLabel: string
  costRatio: number
  alert: boolean
}

export interface CostMonitor {
  today: CostBucket
  month: CostBucket
  byModel: { model: string; costCents: number; costLabel: string; tokens: number }[]
  byFeature: { feature: string; featureLabel: string; costCents: number; costLabel: string; tokens: number; calls: number }[]
  gates: {
    modelTier: string
    cacheHitRate: number
    templateRatio: number
    maxRounds: { diagnose: number; package: number; coach: number }
  }
  budget: { free: number; single: number; month: number; year: number }
  alertRatio: number
  alert: boolean
  notice: string
}

/** M4-05 AI 成本监控（超 25% 自动告警） */
export async function getCostMonitor(): Promise<CostMonitor> {
  return request('/api/admin/cost-monitor')
}

export interface FunnelStep {
  step: string
  label: string
  value: number
  rateFromTop: number
  rateFromPrev: number | null
  dropAlert: boolean
}

export interface FunnelData {
  period: string
  steps: FunnelStep[]
  overallConversion: number
  notice: string
}

/** M4-07 转化漏斗（访问 → 诊断 → 付费 → 下载） */
export async function getFunnel(period: 'day' | 'week' | 'month' = 'day'): Promise<FunnelData> {
  return request(`/api/admin/funnel${buildQuery({ period })}`)
}

export interface GrowthData {
  rows: { channel: string; clicks: number }[]
  /** 后端出口统一 camelize（见 backend/app/core 信封层），此处必须用 camelCase。 */
  summary: {
    shares: number
    registers: number
    pays: number
    shareRate: number
    uniqueInviters: number
    paidInvitees: number
    kFactor: number
    fissionCacCents: number
    fissionCacLabel: string
  }
}

/** M4-08 裂变数据看板（转发量 / 新用户 / 付费 / K 因子） */
export async function getGrowth(): Promise<GrowthData> {
  return request('/api/admin/growth')
}

// ---------------- V5.0 第 8 章：数据日报 / 告警 ----------------

/** 每日数据日报（每天 9 点自动生成：营收/订单/新增/退款/AI成本/净现金流） */
export interface DailyReport {
  id: string
  reportDate: string
  revenueCents: number
  revenueLabel: string
  orderCount: number
  newUsers: number
  refundCents: number
  refundLabel: string
  refundCount: number
  aiCostCents: number
  aiCostLabel: string
  channelFeeLabel: string
  netCashCents: number
  netCashLabel: string
  pushStatus: string
  pushedAt: string | null
  content: string
  createdAt: string | null
}

export interface AdminAlertItem {
  id: string
  alertType: string
  level: string
  title: string
  content: string
  relatedType: string | null
  relatedId: string | null
  isRead: boolean
  createdAt: string
}

export async function getDailyReports(limit = 30): Promise<{ items: DailyReport[] }> {
  return request(`/api/admin/daily-reports?limit=${limit}`)
}

export async function generateDailyReport(reportDate?: string): Promise<DailyReport> {
  const q = reportDate ? `?reportDate=${reportDate}` : ''
  return request(`/api/admin/daily-reports/generate${q}`, { method: 'POST' })
}

export async function getAdminAlerts(unreadOnly = false): Promise<{ items: AdminAlertItem[]; unread: number }> {
  return request(`/api/admin/alerts?unreadOnly=${unreadOnly}`)
}

export async function scanAdminAlerts(): Promise<{ orders: number; costs: number }> {
  return request('/api/admin/alerts/scan', { method: 'POST' })
}

export async function readAdminAlerts(alertId?: string): Promise<{ updated: number }> {
  const q = alertId ? `?alertId=${alertId}` : ''
  return request(`/api/admin/alerts/read${q}`, { method: 'POST' })
}

// ---------------- CSV 下载工具 ----------------

export function downloadText(fileName: string, content: string): void {
  const blob = new Blob(['\ufeff' + content], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export function exportCsv(fileName: string, header: string[], rows: (string | number)[][]): boolean {
  const lines = [header.join(','), ...rows.map((r) => r.map((c) => String(c ?? '').replace(/,/g, '，')).join(','))]
  downloadText(fileName, lines.join('\n'))
  return true
}
