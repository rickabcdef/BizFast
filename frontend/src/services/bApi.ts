// 程序员 B 的模块数据层：M4 启动包生成与交付 / M11 运营管理后台。
// 契约见 docs/api-contract.md；USE_MOCK 由 frontend/config/index.ts 注入
//（开发默认开，便于无后端时调试页面；生产默认关，必须直连真实后端）。
import { api, resolveUrl } from '@/services/api'
import JSZip from 'jszip'
import type { DeliverableFile, PackageResult, OrderStatus } from '@/types'

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms))

// ==================== M4 启动包生成与交付 ====================

export type PackageJobStatus = 'generating' | 'delivered' | 'failed'

export interface PackageProgress {
  orderId: string
  status: PackageJobStatus
  percent: number // 真实进度：已完成件数 / 10
  done: number
  total: number
  stage: string // 人话阶段文案，如「正在生成 D04 供应商线索与询价话术」
  message: string
  currentItem: string | null // 正在生成的文件名
  retryCount: number
  failed?: boolean
  failReason?: string | null
}

/** 生成任务入队（M4-01：异步生成，前端轮询真实进度）。 */
export function createPackage(input: { orderId?: string | null; matchId?: string | null }): Promise<{ orderId: string }> {
  if (USE_MOCK) {
    const id = input.orderId || 'ORD-2026-0003'
    return delay(300).then(() => {
      if (!mockState.has(id)) mockState.set(id, { done: 0 })
      return { orderId: id }
    })
  }
  return api.post<{ orderId: string }>('/api/package/create', {
    orderId: input.orderId ?? null,
    matchId: input.matchId ?? null
  })
}

/** 真实生成进度（M4-02：percent 由后端按已完成件数给出，前端不造假）。 */
export function getPackageProgress(orderId: string): Promise<PackageProgress> {
  if (USE_MOCK) return delay(500).then(() => mockProgress(orderId))
  return api.get<PackageProgress>(`/api/package/${orderId}/progress`)
}

/** 真实模式下后端返回的 zipUrl 是相对路径（/api/package/{id}/zip）；
 *  若 API_BASE 指向独立源站（前后端分域部署），必须补前缀，否则 <a download> 会 404。 */
function normalizePackage(pkg: PackageResult): PackageResult {
  if (!pkg) return pkg
  const zipUrl = pkg.zipUrl && pkg.zipUrl.startsWith('/') ? resolveUrl(pkg.zipUrl) : pkg.zipUrl
  return { ...pkg, zipUrl }
}

/** 启动包详情（M4-05：云端永久保存，任意端可查）。 */
export function getPackage(orderId: string): Promise<PackageResult> {
  if (USE_MOCK) {
    return delay(300).then(() => {
      const st = mockState.get(orderId)
      if (!st || st.done < 10) {
        const e: any = new Error('未找到对应的生意启动包')
        e.code = 40401
        throw e
      }
      return mockPackage(orderId)
    })
  }
  return api.get<PackageResult>(`/api/package/${orderId}`).then(normalizePackage)
}

/** 我的启动包列表（M4-05 / M10-01 共用；按时间倒序）。 */
export async function getMyPackages(): Promise<PackageResult[]> {
  if (USE_MOCK) {
    await delay(400)
    return [await mockPackage('ORD-2026-0001')]
  }
  const list = await api.get<PackageResult[]>('/api/packages')
  return (list || []).map(normalizePackage)
}

/** 单件下载 / 预览地址（M4-04：预览不产生额外费用；format 选择多格式交付物的具体格式）。 */
export function packageItemUrl(orderId: string, code: string, format?: string): string {
  const url = resolveUrl(`/api/package/${orderId}/item/${code}`)
  if (!format) return url
  return `${url}?format=${encodeURIComponent(format)}`
}

/** 打包下载地址（M4-03：10 件交付物 ZIP 一键下载，包内均为中文命名）。 */
export function packageZipUrl(orderId: string): string {
  return resolveUrl(`/api/package/${orderId}/zip`)
}

/** 重新生成（M4-06：会员免费，单次购买用户可使用 1 次；规则在界面上明确说明）。 */
export function regeneratePackage(orderId: string): Promise<{ orderId: string; status: PackageJobStatus; remaining: number | null }> {
  if (USE_MOCK) return delay(500).then(() => ({ orderId, status: 'generating', remaining: 0 }))
  return api.post<{ orderId: string; status: PackageJobStatus; remaining: number | null }>(
    `/api/package/${orderId}/regenerate`
  )
}

// ---------------- M4 Mock ----------------

// PRD 4.4.1 十件交付物清单：部分交付物同时交付多格式（如 D03 = PDF + Word）。
// fileType 为卡片主格式（第一项），formats 为完整格式列表。
const D01_D10_MOCK: DeliverableFile[] = [
  { code: 'D01', name: '最佳商机可行性评分卡', fileType: 'pdf', url: '', formats: [{ fileType: 'pdf', url: '' }] },
  { code: 'D02', name: '回本测算表', fileType: 'excel', url: '', formats: [{ fileType: 'excel', url: '' }] },
  { code: 'D03', name: '客户画像与获客清单', fileType: 'pdf', url: '', formats: [{ fileType: 'pdf', url: '' }, { fileType: 'word', url: '' }] },
  { code: 'D04', name: '供应商线索与询价话术', fileType: 'pdf', url: '', formats: [{ fileType: 'pdf', url: '' }] },
  { code: 'D05', name: '定价建议与开业活动方案', fileType: 'pdf', url: '', formats: [{ fileType: 'pdf', url: '' }] },
  { code: 'D06', name: '开店流程清单', fileType: 'pdf', url: '', formats: [{ fileType: 'pdf', url: '' }, { fileType: 'word', url: '' }] },
  { code: 'D07', name: '获客文案模板10条', fileType: 'word', url: '', formats: [{ fileType: 'word', url: '' }, { fileType: 'txt', url: '' }] },
  { code: 'D08', name: '店名与宣传物料', fileType: 'png', url: '', formats: [{ fileType: 'png', url: '' }, { fileType: 'svg', url: '' }] },
  { code: 'D09', name: '30天行动日历', fileType: 'pdf', url: '', formats: [{ fileType: 'pdf', url: '' }, { fileType: 'excel', url: '' }] },
  { code: 'D10', name: '风险清单与止损线', fileType: 'pdf', url: '', formats: [{ fileType: 'pdf', url: '' }] }
]

const FILE_EXT: Record<string, string> = { pdf: 'pdf', excel: 'xlsx', word: 'docx', png: 'png', svg: 'svg', txt: 'txt', zip: 'zip' }
const FILE_LABEL: Record<string, string> = { pdf: 'PDF', excel: 'Excel', word: 'Word', png: 'PNG', svg: 'SVG', txt: 'TXT', zip: 'ZIP' }

// 顺序生成：每次轮询前进 2 件（联调演示用；真实进度以后端为准）
// 失败演示：orderId 为 ORD-2026-0999 时第一次轮询返回失败（M4-08 失败态联调），重试后正常生成。
const mockState = new Map<string, { done: number; tried?: boolean }>()
function mockProgress(orderId: string): PackageProgress {
  const st = mockState.get(orderId) || { done: 0 }
  if (orderId === 'ORD-2026-0999' && !st.tried) {
    st.tried = true
    mockState.set(orderId, st)
    return {
      orderId,
      status: 'failed',
      percent: 20,
      done: 2,
      total: 10,
      stage: 'AI 服务暂时不可用',
      message: '生成失败，正在自动重试（第 1/2 次）',
      currentItem: null,
      retryCount: 1,
      failed: true,
      failReason: 'AI 服务暂时不可用，系统已自动重试 2 次仍未成功（模拟）'
    }
  }
  st.done = Math.min(10, st.done + 2)
  mockState.set(orderId, st)
  const done = st.done
  const item = D01_D10_MOCK[Math.min(done - 1, 9)]
  return {
    orderId,
    status: done >= 10 ? 'delivered' : 'generating',
    percent: done * 10,
    done,
    total: 10,
    stage: done >= 10 ? '10 件交付物已全部生成' : `正在生成 ${item.code} ${item.name}`,
    message: done >= 10 ? '生成完成，正在打包 ZIP' : `已完成 ${done}/10，AI 正在干活，别走开`,
    currentItem: done >= 10 ? null : item.name,
    retryCount: 0,
    failed: false,
    failReason: null
  }
}

async function mockPackage(orderId: string): Promise<PackageResult> {
  const data: PackageResult = {
    orderId,
    status: 'delivered',
    items: D01_D10_MOCK.map((it) => {
      const formats = (it.formats || [{ fileType: it.fileType, url: '' }]).map((f) => ({
        fileType: f.fileType,
        url: mockItemDataUrl(it.name, f.fileType)
      }))
      return {
        code: it.code,
        name: it.name,
        fileType: formats[0].fileType,
        url: formats[0].url,
        formats
      }
    }),
    zipUrl: MOCK_EMPTY_ZIP,
    retryCount: 0
  }
  data.zipUrl = await buildMockZipUrl(data)
  return data
}

// ---------------- Mock 占位文件（离线演示可用，真实环境以后端为准） ----------------
const MOCK_EMPTY_ZIP = 'data:application/zip;base64,UEsFBgAAAAAAAAAAAAAAAAAAAAAAAA=='

function mockItemDataUrl(name: string, fileType: string): string {
  const safeName = encodeURIComponent(`生意快启_${name}`)
  switch (fileType) {
    case 'pdf':
      return mockPdfDataUrl(`生意快启_${name}`)
    case 'png':
      // 1x1 透明 PNG（演示占位）
      return 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
    case 'svg':
      return `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="600" height="400"><rect width="600" height="400" fill="%230F172A"/><text x="40" y="200" font-size="32" fill="white">${safeName}</text><text x="40" y="240" font-size="20" fill="%238B93B8">生意快启 · 演示物料（Mock）</text></svg>`
    case 'txt':
      return `data:text/plain;charset=utf-8,${safeName}%0A%0A这是生意快启的演示文件（Mock）。真实环境由后端生成实体文件。`
    case 'word':
    case 'excel':
    default:
      // excel / word 等：给一个可下载的占位文本
      return `data:text/plain;charset=utf-8,${safeName}%0A%0A演示文件（Mock）：真实环境由后端生成对应格式的实体文件。`
  }
}

/** Mock ZIP：用 JSZip 把 10 件交付物的全部格式打包为「中文命名」的真实 ZIP（M4-03 演示）。 */
async function buildMockZipUrl(pkg: PackageResult): Promise<string> {
  if (typeof window === 'undefined' || typeof URL === 'undefined') return MOCK_EMPTY_ZIP
  const zip = new JSZip()
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  const date = `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}`
  for (const it of pkg.items) {
    const formats = it.formats || [{ fileType: it.fileType, url: it.url }]
    for (const f of formats) {
      // data URL → Blob → 写入 ZIP；文件名「生意快启_交付物名称_生成日期.扩展名」
      const ext = FILE_EXT[f.fileType] || 'file'
      zip.file(`生意快启_${it.name}_${date}.${ext}`, dataUrlToBlob(f.url))
    }
  }
  try {
    const blob = await zip.generateAsync({ type: 'blob' })
    return URL.createObjectURL(blob)
  } catch {
    return MOCK_EMPTY_ZIP
  }
}

function dataUrlToBlob(dataUrl: string): Blob {
  try {
    const [head, body] = dataUrl.split(',')
    const mime = /data:([^;]+)/.exec(head || '')?.[1] || 'application/octet-stream'
    const bin = atob(body || '')
    const u8 = new Uint8Array(bin.length)
    for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i)
    return new Blob([u8], { type: mime })
  } catch {
    return new Blob([dataUrl], { type: 'application/octet-stream' })
  }
}

/** 最小合法 PDF（运行时计算 xref 偏移，保证浏览器可预览）。 */
function mockPdfDataUrl(title: string): string {
  const esc = title.replace(/[()\\]/g, (s) => `\\${s}`)
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>`,
    `<< /Length ${esc.length + 44} >>\nstream\nBT /F1 18 Tf 72 740 Td (${esc}) Tj ET\nendstream`,
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'
  ]
  let pdf = '%PDF-1.4\n'
  const offsets: number[] = []
  for (let i = 0; i < objects.length; i++) {
    offsets.push(pdf.length)
    pdf += `${i + 1} 0 obj\n${objects[i]}\nendobj\n`
  }
  const xrefPos = pdf.length
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`
  for (const off of offsets) pdf += `${String(off).padStart(10, '0')} 00000 n \n`
  pdf += `trailer << /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefPos}\n%%EOF`
  return `data:application/pdf;base64,${btoa(unescape(encodeURIComponent(pdf)))}`
}

// ==================== M11 运营管理后台 ====================

export type AdminRole = 'admin' | 'operator' | 'support'
export type ReviewStatus = 'pending' | 'passed' | 'rejected'

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
  createdAt: string
}

export interface PromptItem {
  key: string
  name: string
  content: string
  model: string
  updatedAt: string
}

export interface ReviewItem {
  id: string
  type: string
  content: string
  result: string | null
  status: ReviewStatus
  statusLabel: string
  reason: string | null
  createdAt: string
}

export interface RolePerm {
  key: string
  label: string
  enabled: boolean
}

export interface RoleItem {
  role: AdminRole
  name: string
  description: string
  perms: RolePerm[]
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
  date: string
  orders: number
  revenue: number
}

export interface PageBox<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
}

/** 管理员登录（后台内部账号；密钥走环境变量，不进代码库）。
 *  真实后端为两步式：① 账号密码 → 下发 needTotp/totpHint；② TOTP 校验 → 签发 JWT。
 *  本地开发用后端下发的 totpHint 自动完成第二步，页面只需账号密码即可登录。 */
export async function adminLogin(
  username: string,
  password: string
): Promise<{ token: string; name: string; role: AdminRole }> {
  if (USE_MOCK) {
    return delay(400).then(() => {
      if (!username.trim() || !password.trim()) {
        const e: any = new Error('请输入管理员账号与密码')
        e.code = 40001
        throw e
      }
      return { token: `mock-admin-${Date.now()}`, name: username.trim(), role: username.trim() === 'admin' ? 'admin' : 'operator' }
    })
  }
  const step1 = await api.post<{ needTotp: boolean; totpHint: string }>('/api/admin/auth/login', {
    username,
    password
  })
  const session = await api.post<{ token: string; name: string; role: AdminRole }>(
    '/api/admin/auth/verify-2fa',
    { username, totp: step1?.totpHint || '' }
  )
  return { token: session.token, name: session.name, role: session.role }
}

// ---------------- M11-05 数据看板 ----------------
export function getAdminDashboard(): Promise<{ kpis: DashboardKpis; trend: DashboardTrend[]; refreshAt: string }> {
  if (USE_MOCK) return delay(500).then(() => mockDashboard())
  return api.get<{ kpis: DashboardKpis; trend: DashboardTrend[]; refreshAt: string }>('/api/admin/dashboard')
}

// ---------------- M11-01 用户管理 ----------------
export function getAdminUsers(params: { page?: number; pageSize?: number; keyword?: string; memberStatus?: string }): Promise<PageBox<AdminUser>> {
  const q = new URLSearchParams()
  q.set('page', String(params.page ?? 1))
  q.set('pageSize', String(params.pageSize ?? 20))
  if (params.keyword) q.set('keyword', params.keyword)
  if (params.memberStatus) q.set('memberStatus', params.memberStatus)
  if (USE_MOCK) return delay(400).then(() => mockUsers(params))
  return api.get<PageBox<AdminUser>>(`/api/admin/users?${q.toString()}`)
}

/** 用户详情：后端返回 {user, orders, packages}，页面按「消费记录」展示，
 *  这里统一成 consumption 字段，避免视图层再感知后端字段名。 */
export async function getAdminUserDetail(userId: string): Promise<{ user: AdminUser; consumption: AdminOrder[] }> {
  if (USE_MOCK) return delay(300).then(() => ({ user: mockUsers({}).items[0], consumption: mockOrders({}).items.slice(0, 2) }))
  const d = await api.get<{ user: AdminUser; orders?: AdminOrder[]; packages?: any[] }>(
    `/api/admin/users/${userId}`
  )
  return { user: d.user, consumption: d.orders || [] }
}

// ---------------- M11-02 订单管理 ----------------
export function getAdminOrders(params: { page?: number; pageSize?: number; status?: string; keyword?: string }): Promise<PageBox<AdminOrder>> {
  const q = new URLSearchParams()
  q.set('page', String(params.page ?? 1))
  q.set('pageSize', String(params.pageSize ?? 20))
  if (params.status) q.set('status', params.status)
  if (params.keyword) q.set('keyword', params.keyword)
  if (USE_MOCK) return delay(400).then(() => mockOrders(params))
  return api.get<PageBox<AdminOrder>>(`/api/admin/orders?${q.toString()}`)
}

/** 处理退款（M11-02：同意原路退回 / 驳回并记录原因；操作人写入审计日志）。 */
export function processRefund(orderId: string, action: 'approve' | 'reject', reason?: string): Promise<{ orderId: string; status: OrderStatus; message: string }> {
  if (USE_MOCK) return delay(400).then(() => ({ orderId, status: action === 'approve' ? 'refunded' : 'paid', message: action === 'approve' ? '已同意退款，24 小时内原路到账' : '已驳回退款申请' }))
  return api.put<{ orderId: string; status: OrderStatus; message: string }>(`/api/admin/orders/${orderId}/refund`, { action, reason: reason || null })
}

// ---------------- M11-03 商机库管理 ----------------
export function getAdminOpportunities(params: { page?: number; pageSize?: number; status?: string; keyword?: string }): Promise<PageBox<AdminOpportunity>> {
  const q = new URLSearchParams()
  q.set('page', String(params.page ?? 1))
  q.set('pageSize', String(params.pageSize ?? 20))
  if (params.status) q.set('status', params.status)
  if (params.keyword) q.set('keyword', params.keyword)
  if (USE_MOCK) return delay(400).then(() => mockOpportunities(params))
  return api.get<PageBox<AdminOpportunity>>(`/api/admin/opportunities?${q.toString()}`)
}

/** 批量导入（M11-03 P0：粘贴 CSV/表格数据，后端校验后入库待审）。 */
export function importOpportunities(items: AdminOpportunity[]): Promise<{ imported: number; rejected: number; errors: string[] }> {
  if (USE_MOCK) {
    return delay(500).then(() => ({ imported: items.length, rejected: 0, errors: [] }))
  }
  return api.post<{ imported: number; rejected: number; errors: string[] }>('/api/admin/opportunities/import', { items })
}

/** 商机审核（M11-03 / M11-06：通过或驳回，违规内容拦截率 ≥ 99%）。 */
export function reviewOpportunity(id: string, action: 'approve' | 'reject', reason?: string): Promise<{ id: string; status: ReviewStatus; message: string }> {
  if (USE_MOCK) return delay(300).then(() => ({ id, status: action === 'approve' ? 'passed' : 'rejected', message: action === 'approve' ? '已通过' : '已驳回' }))
  return api.post<{ id: string; status: ReviewStatus; message: string }>(`/api/admin/opportunities/${id}/review`, { action, reason: reason || null })
}

// ---------------- M11-04 提示词配置 ----------------
export function getAdminPrompts(): Promise<{ items: PromptItem[]; notice: string }> {
  if (USE_MOCK) return delay(300).then(() => mockPrompts())
  return api.get<{ items: PromptItem[]; notice: string }>('/api/admin/prompts')
}

export function saveAdminPrompt(key: string, patch: { content?: string; model?: string }): Promise<PromptItem> {
  if (USE_MOCK) return delay(300).then(() => ({ key, name: key, content: patch.content || '', model: patch.model || 'default', updatedAt: '刚刚' }))
  return api.put<PromptItem>(`/api/admin/prompts/${key}`, patch)
}

// ---------------- M11-06 内容审核 ----------------
export function getAdminReviews(params: { page?: number; pageSize?: number; status?: string; keyword?: string }): Promise<PageBox<ReviewItem>> {
  const q = new URLSearchParams()
  q.set('page', String(params.page ?? 1))
  q.set('pageSize', String(params.pageSize ?? 20))
  if (params.status) q.set('status', params.status)
  if (params.keyword) q.set('keyword', params.keyword)
  if (USE_MOCK) return delay(400).then(() => mockReviews(params))
  return api.get<PageBox<ReviewItem>>(`/api/admin/reviews?${q.toString()}`)
}

export function reviewAction(id: string, action: 'pass' | 'reject', reason?: string): Promise<{ id: string; status: ReviewStatus; message: string }> {
  if (USE_MOCK) return delay(300).then(() => ({ id, status: action === 'pass' ? 'passed' : 'rejected', message: action === 'pass' ? '已通过' : '已拦截' }))
  return api.post<{ id: string; status: ReviewStatus; message: string }>(`/api/admin/reviews/${id}/action`, { action, reason: reason || null })
}

// ---------------- M11-07 权限管理 ----------------
export function getAdminRoles(): Promise<{ items: RoleItem[]; notice: string }> {
  if (USE_MOCK) return delay(300).then(() => mockRoles())
  return api.get<{ items: RoleItem[]; notice: string }>('/api/admin/roles')
}

export function saveAdminRole(role: AdminRole, perms: RolePerm[]): Promise<RoleItem> {
  if (USE_MOCK) return delay(300).then(() => ({ role, name: role, description: '', perms }))
  return api.put<RoleItem>(`/api/admin/roles/${role}`, { perms })
}

// ---------------- M11-08 审计日志 ----------------
export function getAdminAuditLogs(params: { page?: number; pageSize?: number; operator?: string; action?: string }): Promise<PageBox<AuditLogItem>> {
  const q = new URLSearchParams()
  q.set('page', String(params.page ?? 1))
  q.set('pageSize', String(params.pageSize ?? 20))
  if (params.operator) q.set('operator', params.operator)
  if (params.action) q.set('action', params.action)
  if (USE_MOCK) return delay(400).then(() => mockAuditLogs(params))
  return api.get<PageBox<AuditLogItem>>(`/api/admin/audit?${q.toString()}`)
}

// ---------------- M11 Mock ----------------

function mockDashboard(): { kpis: DashboardKpis; trend: DashboardTrend[]; refreshAt: string } {
  const trend: DashboardTrend[] = []
  const today = new Date()
  for (let i = 6; i >= 0; i--) {
    const d = new Date(today.getTime() - i * 86400000)
    trend.push({
      date: `${d.getMonth() + 1}/${d.getDate()}`,
      orders: 8 + ((i * 7) % 13),
      revenue: 120 + ((i * 89) % 260)
    })
  }
  return {
    kpis: {
      diagnoseCount: 1247,
      payCount: 86,
      revenueYuan: 1324,
      refundRate: '3.5%',
      conversionRate: '6.9%',
      packageDoneRate: '99.2%',
      avgOrderYuan: '15.4'
    },
    trend,
    refreshAt: '刚刚'
  }
}

function mockUsers(params: { keyword?: string; memberStatus?: string }): PageBox<AdminUser> {
  const all: AdminUser[] = [
    { id: 'U-1001', phone: '138****2211', nickname: '陈小满', city: '上海', memberStatus: 'month', memberLabel: '月度会员', orderCount: 3, totalSpendYuan: 87, createdAt: '2026-09-12 10:24', riskFlag: false },
    { id: 'U-1002', phone: '159****0087', nickname: '阿强开店', city: '杭州', memberStatus: 'single', memberLabel: '单次购买', orderCount: 1, totalSpendYuan: 9.9, createdAt: '2026-09-18 21:05', riskFlag: false },
    { id: 'U-1003', phone: '186****3345', nickname: 'Linda 妈', city: '成都', memberStatus: 'year', memberLabel: '年度会员', orderCount: 5, totalSpendYuan: 199, createdAt: '2026-09-20 08:47', riskFlag: false },
    { id: 'U-1004', phone: '137****9902', nickname: '木子李', city: '广州', memberStatus: 'none', memberLabel: '游客', orderCount: 0, totalSpendYuan: 0, createdAt: '2026-09-28 19:12', riskFlag: true },
    { id: 'U-1005', phone: '188****7766', nickname: '返乡小张', city: '临沂', memberStatus: 'month', memberLabel: '月度会员', orderCount: 2, totalSpendYuan: 48.9, createdAt: '2026-10-01 14:33', riskFlag: false }
  ]
  const kw = (params.keyword || '').trim()
  const filtered = all.filter(
    (u) =>
      (!kw || u.phone.includes(kw) || u.nickname.includes(kw) || u.city.includes(kw)) &&
      (!params.memberStatus || u.memberStatus === params.memberStatus)
  )
  return { items: filtered, total: filtered.length, page: 1, pageSize: 20 }
}

function mockOrders(params: { status?: string; keyword?: string }): PageBox<AdminOrder> {
  const all: AdminOrder[] = [
    { id: 'ORD-2026-0001', userId: 'U-1001', userPhone: '138****2211', plan: 'month', planName: '月度会员', amountYuan: 39, status: 'delivered', statusLabel: '已交付', channel: '支付宝', createdAt: '2026-10-01 20:14', paidAt: '2026-10-01 20:15', refundRequested: false, refundReason: null },
    { id: 'ORD-2026-0002', userId: 'U-1002', userPhone: '159****0087', plan: 'single', planName: '单次启动包', amountYuan: 9.9, status: 'generating', statusLabel: '生成中', channel: '微信支付', createdAt: '2026-10-02 09:30', paidAt: '2026-10-02 09:31', refundRequested: false, refundReason: null },
    { id: 'ORD-2026-0003', userId: 'U-1003', userPhone: '186****3345', plan: 'year', planName: '年度会员', amountYuan: 199, status: 'paid', statusLabel: '已支付', channel: '支付宝', createdAt: '2026-10-02 15:02', paidAt: '2026-10-02 15:02', refundRequested: true, refundReason: '用不上了想退' },
    { id: 'ORD-2026-0004', userId: 'U-1001', userPhone: '138****2211', plan: 'single', planName: '单次启动包', amountYuan: 9.9, status: 'refunded', statusLabel: '已退款', channel: '微信支付', createdAt: '2026-09-28 11:41', paidAt: '2026-09-28 11:42', refundRequested: false, refundReason: null },
    { id: 'ORD-2026-0005', userId: 'U-1005', userPhone: '188****7766', plan: 'month', planName: '月度会员', amountYuan: 39, status: 'pending', statusLabel: '待支付', channel: '支付宝', createdAt: '2026-10-03 08:55', paidAt: null, refundRequested: false, refundReason: null }
  ]
  const kw = (params.keyword || '').trim()
  const filtered = all.filter(
    (o) =>
      (!kw || o.id.includes(kw) || o.userPhone.includes(kw)) &&
      (!params.status || o.status === params.status)
  )
  return { items: filtered, total: filtered.length, page: 1, pageSize: 20 }
}

function mockOpportunities(params: { status?: string; keyword?: string }): PageBox<AdminOpportunity> {
  const all: AdminOpportunity[] = [
    { id: 'OP-5001', title: '社区团购团长（兼职）', category: '社区零售', city: '全国', capitalMin: 5000, capitalMax: 20000, paybackMonths: 3, marginPercent: 28, difficultyStars: 2, source: '案例库', status: 'passed', statusLabel: '已通过', createdAt: '2026-09-20 10:00' },
    { id: 'OP-5002', title: '上门宠物洗护（轻资产）', category: '本地生活', city: '上海', capitalMin: 30000, capitalMax: 80000, paybackMonths: 6, marginPercent: 45, difficultyStars: 3, source: '案例库', status: 'passed', statusLabel: '已通过', createdAt: '2026-09-21 14:22' },
    { id: 'OP-5003', title: '夜市柠檬茶摊', category: '餐饮小吃', city: '长沙', capitalMin: 8000, capitalMax: 15000, paybackMonths: 2, marginPercent: 62, difficultyStars: 1, source: '批量导入', status: 'pending', statusLabel: '待审核', createdAt: '2026-10-01 09:12' },
    { id: 'OP-5004', title: '短视频代剪辑接单', category: '线上服务', city: '全国', capitalMin: 3000, capitalMax: 10000, paybackMonths: 4, marginPercent: 70, difficultyStars: 3, source: '批量导入', status: 'pending', statusLabel: '待审核', createdAt: '2026-10-01 09:13' },
    { id: 'OP-5005', title: '证件照拍摄快照亭', category: '本地生活', city: '郑州', capitalMin: 50000, capitalMax: 120000, paybackMonths: 12, marginPercent: 55, difficultyStars: 4, source: '人工录入', status: 'rejected', statusLabel: '已驳回', createdAt: '2026-09-25 16:40' }
  ]
  const kw = (params.keyword || '').trim()
  const filtered = all.filter(
    (o) =>
      (!kw || o.title.includes(kw) || o.category.includes(kw) || o.city.includes(kw)) &&
      (!params.status || o.status === params.status)
  )
  return { items: filtered, total: filtered.length, page: 1, pageSize: 20 }
}

function mockPrompts(): { items: PromptItem[]; notice: string } {
  return {
    items: [
      { key: 'diagnose.main', name: '诊断主提示词', content: '你是生意诊断专家。根据用户的启动资金、每日时间和城市，输出最热 3 个方向，说人话、给数字、给风险。', model: 'doubao-seed-1.6', updatedAt: '2026-09-30 11:20' },
      { key: 'match.rank', name: '商机排序与五要素', content: '基于诊断标签从商机库挑选 3 个强相关方案，输出启动资金、回本周期、毛利率、第一个客户、上手难度。', model: 'doubao-seed-1.6', updatedAt: '2026-09-30 11:21' },
      { key: 'package.d01', name: 'D01 可行性评分卡', content: '从市场、投入、回报、难度、政策五个维度打分，输出综合结论与一句人话建议。', model: 'doubao-lite', updatedAt: '2026-09-28 17:02' },
      { key: 'package.d07', name: 'D07 获客文案', content: '生成 10 条可直发的获客文案：朋友圈、短视频脚本、私聊开场白各覆盖。', model: 'doubao-lite', updatedAt: '2026-09-28 17:03' }
    ],
    notice: '提示词修改后立即生效，无需发版（M11-04）。生产环境密钥走配置中心。'
  }
}

function mockReviews(params: { status?: string; keyword?: string }): PageBox<ReviewItem> {
  const all: ReviewItem[] = [
    { id: 'RV-9001', type: '商机文案', content: '夜市柠檬茶摊：启动资金约 1 万元，回本约 2 个月，注意选址与夏季天气风险。', result: null, status: 'pending', statusLabel: '待审核', reason: null, createdAt: '2026-10-01 09:12' },
    { id: 'RV-9002', type: '交付物 D07', content: '私聊开场白：你好呀，最近有个小生意方向想跟你聊聊，你平时会考虑副业吗？', result: null, status: 'pending', statusLabel: '待审核', reason: null, createdAt: '2026-10-01 09:15' },
    { id: 'RV-9003', type: '商机文案', content: '短视频代剪辑接单：一部片子 200-500 元，先接 10 单试水。', result: null, status: 'pending', statusLabel: '待审核', reason: null, createdAt: '2026-10-01 09:13' },
    { id: 'RV-9004', type: '商机文案', content: '保收益理财型话术（含「稳赚」字样，命中敏感词）', result: null, status: 'pending', statusLabel: '待审核', reason: '命中敏感词：稳赚', createdAt: '2026-10-01 09:20' },
    { id: 'RV-9005', type: '交付物 D05', content: '开业活动：前三天全场 8.8 折，扫码进群领 5 元券。', result: 'pass', status: 'passed', statusLabel: '已通过', reason: null, createdAt: '2026-09-30 18:02' }
  ]
  const kw = (params.keyword || '').trim()
  const filtered = all.filter(
    (r) =>
      (!kw || r.content.includes(kw) || r.type.includes(kw)) &&
      (!params.status || r.status === params.status)
  )
  return { items: filtered, total: filtered.length, page: 1, pageSize: 20 }
}

function mockRoles(): { items: RoleItem[]; notice: string } {
  const permDefs = [
    { key: 'dashboard', label: '数据看板' },
    { key: 'users', label: '用户管理' },
    { key: 'orders', label: '订单管理' },
    { key: 'opportunities', label: '商机库管理' },
    { key: 'prompts', label: '提示词配置' },
    { key: 'reviews', label: '内容审核' },
    { key: 'roles', label: '权限管理' },
    { key: 'audit', label: '审计日志' },
    { key: 'share', label: '分享转化' }
  ]
  const mk = (role: AdminRole, name: string, description: string, on: string[]) => ({
    role,
    name,
    description,
    perms: permDefs.map((p) => ({ key: p.key, label: p.label, enabled: on.includes(p.key) }))
  })
  return {
    items: [
      mk('admin', '管理员', '全部权限，含权限管理与审计', ['dashboard', 'users', 'orders', 'opportunities', 'prompts', 'reviews', 'roles', 'audit', 'share']),
      mk('operator', '运营', '日常运营：看板 / 商机库 / 内容审核 / 分享转化', ['dashboard', 'opportunities', 'reviews', 'share']),
      mk('support', '客服', '客服：用户与订单查询 / 退款处理', ['users', 'orders'])
    ],
    notice: '所有后台操作均记录操作人（M11-08），日志保留 ≥ 180 天。'
  }
}

function mockAuditLogs(params: { operator?: string; action?: string }): PageBox<AuditLogItem> {
  const all: AuditLogItem[] = [
    { id: 'LOG-0001', operator: 'admin', role: '管理员', action: '订单退款', target: 'ORD-2026-0004', detail: '同意退款 9.9 元（用户主动申请）', createdAt: '2026-09-28 11:42' },
    { id: 'LOG-0002', operator: 'ops_lily', role: '运营', action: '商机审核', target: 'OP-5001', detail: '通过商机「社区团购团长」', createdAt: '2026-09-20 10:01' },
    { id: 'LOG-0003', operator: 'ops_lily', role: '运营', action: '批量导入', target: '商机库', detail: '导入 120 条商机，通过 118 条', createdAt: '2026-10-01 09:10' },
    { id: 'LOG-0004', operator: 'admin', role: '管理员', action: '提示词更新', target: 'diagnose.main', detail: '更新诊断主提示词（模型切换）', createdAt: '2026-09-30 11:20' },
    { id: 'LOG-0005', operator: 'admin', role: '管理员', action: '权限调整', target: 'support', detail: '为客服角色开放订单退款处理', createdAt: '2026-09-25 15:30' }
  ]
  const filtered = all.filter(
    (l) => (!params.operator || l.operator.includes(params.operator)) && (!params.action || l.action.includes(params.action))
  )
  return { items: filtered, total: filtered.length, page: 1, pageSize: 20 }
}

// ---------------- CSV 导出（M11-01/02：支持导出与对账表） ----------------
/** 在网页端把二维数据导出为 CSV 并触发下载（跨端：非 Web 端提示保存图片）。 */
export function exportCsv(fileName: string, header: string[], rows: (string | number)[][]): boolean {
  if (typeof document === 'undefined') return false
  const esc = (v: string | number) => {
    const s = String(v ?? '')
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const content = '\ufeff' + [header, ...rows].map((r) => r.map(esc).join(',')).join('\r\n')
  try {
    const blob = new Blob([content], { type: 'text/csv;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = fileName
    a.click()
    setTimeout(() => URL.revokeObjectURL(a.href), 1000)
    return true
  } catch {
    return false
  }
}
