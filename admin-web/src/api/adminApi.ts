// ===================================================================
// BizFast 运营管理后台 · 数据层（Mock）
// 独立于用户端登录态；真实环境由独立后端 /api/admin 提供，契约见下方各函数。
// 所有写操作均写入审计日志（M11-08）。
// ===================================================================

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms))

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
  source: string // 来源渠道
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
  abnormal: boolean // 异常订单（已支付未交付 / 支付回调缺失）
  abnormalType: string | null // paid_no_delivery | callback_missing
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

// ---------------- 登录与会话（独立登录态 + TOTP 二次验证） ----------------

const ACCOUNTS: Record<string, { password: string; name: string; role: AdminRole }> = {
  admin: { password: 'admin123', name: '系统管理员', role: 'admin' },
  operator: { password: 'op123', name: '运营小王', role: 'operator' },
  support: { password: 'sup123', name: '客服小张', role: 'support' },
  finance: { password: 'fin123', name: '财务小丽', role: 'finance' }
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

export async function adminLoginStep1(username: string, password: string): Promise<{ needTotp: boolean; totpHint: string }> {
  await delay(400)
  const acc = ACCOUNTS[username.trim()]
  if (!acc || acc.password !== password) {
    const e: any = new Error('账号或密码错误')
    e.code = 40001
    throw e
  }
  // 二次验证：下发 TOTP（演示环境固定 123456，真实环境走 TOTP / 手机验证码）
  return { needTotp: true, totpHint: '123456' }
}

export async function adminLoginStep2(username: string, totp: string, hint: string): Promise<AdminSession> {
  await delay(300)
  if (totp.trim() !== hint) {
    const e: any = new Error('验证码不正确，请重新输入')
    e.code = 40002
    throw e
  }
  const acc = ACCOUNTS[username.trim()]
  const session: AdminSession = {
    token: `adm-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    name: acc.name,
    username: username.trim(),
    role: acc.role,
    loginAt: new Date().toLocaleString('zh-CN')
  }
  writeAudit(session, '登录', '后台', `账号 ${username} 通过账号密码 + TOTP 二次验证登录`)
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
  await delay(400)
  const kpis: DashboardKpis = {
    diagnoseCount: 1247,
    payCount: 86,
    revenueYuan: 1324,
    conversionRate: '6.9%',
    packageDoneRate: '99.2%',
    refundRate: '3.5%',
    avgOrderYuan: '15.4'
  }
  const trend = mockTrend(granularity)
  return { kpis, trend, refreshAt: '刚刚（延迟 ≤ 5 分钟）' }
}

function mockTrend(g: TrendGranularity): DashboardTrend[] {
  if (g === 'day') {
    return [
      { label: '10/1', orders: 10, revenue: 148 },
      { label: '10/2', orders: 16, revenue: 236 },
      { label: '10/3', orders: 9, revenue: 121 },
      { label: '10/4', orders: 15, revenue: 232 },
      { label: '10/5', orders: 8, revenue: 104 },
      { label: '10/6', orders: 12, revenue: 186 },
      { label: '10/7', orders: 16, revenue: 254 }
    ]
  }
  if (g === 'week') {
    return [
      { label: '第 39 周', orders: 42, revenue: 612 },
      { label: '第 40 周', orders: 58, revenue: 902 },
      { label: '第 41 周', orders: 51, revenue: 778 },
      { label: '第 42 周', orders: 66, revenue: 1032 },
      { label: '第 43 周', orders: 49, revenue: 756 }
    ]
  }
  return [
    { label: '2026-06', orders: 121, revenue: 1760 },
    { label: '2026-07', orders: 156, revenue: 2380 },
    { label: '2026-08', orders: 188, revenue: 2864 },
    { label: '2026-09', orders: 224, revenue: 3412 },
    { label: '2026-10', orders: 86, revenue: 1324 }
  ]
}

// ---------------- M11-01 用户管理（详情含全部订单与启动包记录） ----------------

const mockUsersData: AdminUser[] = [
  { id: 'U-1001', phone: '138****2211', nickname: '陈小满', city: '上海', memberStatus: 'month', memberLabel: '月度会员', orderCount: 3, totalSpendYuan: 87, createdAt: '2026-09-12 10:24', riskFlag: false, source: '自然流量' },
  { id: 'U-1002', phone: '159****0087', nickname: '阿强开店', city: '杭州', memberStatus: 'single', memberLabel: '单次购买', orderCount: 1, totalSpendYuan: 9.9, createdAt: '2026-09-18 21:05', riskFlag: false, source: '商机详情页' },
  { id: 'U-1003', phone: '186****3345', nickname: 'Linda 妈', city: '成都', memberStatus: 'year', memberLabel: '年度会员', orderCount: 5, totalSpendYuan: 199, createdAt: '2026-09-20 08:47', riskFlag: false, source: '分享卡片' },
  { id: 'U-1004', phone: '137****9902', nickname: '老王摆摊', city: '长沙', memberStatus: 'none', memberLabel: '游客', orderCount: 0, totalSpendYuan: 0, createdAt: '2026-09-25 19:12', riskFlag: false, source: '自然流量' },
  { id: 'U-1005', phone: '188****6678', nickname: 'Momo 副业', city: '广州', memberStatus: 'month', memberLabel: '月度会员', orderCount: 2, totalSpendYuan: 58, createdAt: '2026-09-28 14:33', riskFlag: true, source: '付费弹窗' }
]

const mockOrdersData: AdminOrder[] = [
  { id: 'ORD-2026-0001', userId: 'U-1001', userPhone: '138****2211', plan: 'month', planName: '月度会员', amountYuan: 39, status: 'delivered', statusLabel: '已交付', channel: '支付宝', createdAt: '2026-10-01 20:14', paidAt: '2026-10-01 20:15', refundRequested: false, refundReason: null, abnormal: false, abnormalType: null },
  { id: 'ORD-2026-0002', userId: 'U-1002', userPhone: '159****0087', plan: 'single', planName: '单次启动包', amountYuan: 9.9, status: 'delivered', statusLabel: '已交付', channel: '微信支付', createdAt: '2026-10-01 21:02', paidAt: '2026-10-01 21:03', refundRequested: false, refundReason: null, abnormal: false, abnormalType: null },
  { id: 'ORD-2026-0003', userId: 'U-1003', userPhone: '186****3345', plan: 'year', planName: '年度会员', amountYuan: 199, status: 'paid', statusLabel: '已支付', channel: '支付宝', createdAt: '2026-10-02 10:11', paidAt: '2026-10-02 10:12', refundRequested: false, refundReason: null, abnormal: true, abnormalType: 'paid_no_delivery' },
  { id: 'ORD-2026-0004', userId: 'U-1005', userPhone: '188****6678', plan: 'month', planName: '月度会员', amountYuan: 39, status: 'paid', statusLabel: '已支付', channel: '微信支付', createdAt: '2026-10-03 16:40', paidAt: null, refundRequested: false, refundReason: null, abnormal: true, abnormalType: 'callback_missing' },
  { id: 'ORD-2026-0005', userId: 'U-1001', userPhone: '138****2211', plan: 'single', planName: '单次启动包', amountYuan: 9.9, status: 'paid', statusLabel: '已支付', channel: '支付宝', createdAt: '2026-10-04 09:20', paidAt: '2026-10-04 09:21', refundRequested: true, refundReason: '重复购买，申请退款', abnormal: false, abnormalType: null },
  { id: 'ORD-2026-0006', userId: 'U-1003', userPhone: '186****3345', plan: 'single', planName: '单次启动包', amountYuan: 9.9, status: 'generating', statusLabel: '生成中', channel: '微信支付', createdAt: '2026-10-05 11:05', paidAt: '2026-10-05 11:06', refundRequested: false, refundReason: null, abnormal: false, abnormalType: null },
  { id: 'ORD-2026-0007', userId: 'U-1005', userPhone: '188****6678', plan: 'month', planName: '月度会员', amountYuan: 39, status: 'refunded', statusLabel: '已退款', channel: '微信支付', createdAt: '2026-10-04 15:02', paidAt: '2026-10-04 15:03', refundRequested: false, refundReason: null, abnormal: false, abnormalType: null }
]

const mockPackagesData = [
  { orderId: 'ORD-2026-0001', name: '长沙·夜市柠檬茶摊 启动包', fileCount: 10, status: 'delivered', createdAt: '2026-10-01 20:16' },
  { orderId: 'ORD-2026-0002', name: '杭州·上门宠物洗护 启动包', fileCount: 10, status: 'delivered', createdAt: '2026-10-01 21:05' },
  { orderId: 'ORD-2026-0005', name: '上海·社区团购团长 启动包', fileCount: 10, status: 'delivered', createdAt: '2026-10-04 09:22' },
  { orderId: 'ORD-2026-0006', name: '广州·周末市集手作 启动包', fileCount: 0, status: 'generating', createdAt: '2026-10-05 11:07' }
]

export async function getAdminUsers(params: { page?: number; pageSize?: number; keyword?: string; memberStatus?: string }): Promise<PageBox<AdminUser>> {
  await delay(350)
  let items = [...mockUsersData]
  if (params.keyword) {
    const k = params.keyword.trim()
    items = items.filter((u) => u.phone.includes(k) || u.nickname.includes(k) || u.city.includes(k))
  }
  if (params.memberStatus) items = items.filter((u) => u.memberStatus === params.memberStatus)
  const page = params.page ?? 1
  const pageSize = params.pageSize ?? 20
  return { items: items.slice((page - 1) * pageSize, page * pageSize), total: items.length, page, pageSize }
}

export async function getAdminUserDetail(userId: string): Promise<{ user: AdminUser; orders: AdminOrder[]; packages: typeof mockPackagesData }> {
  await delay(300)
  const user = mockUsersData.find((u) => u.id === userId) || mockUsersData[0]
  const orders = mockOrdersData.filter((o) => o.userId === user.id)
  const packages = mockPackagesData.filter((p) => orders.some((o) => o.id === p.orderId))
  return { user, orders, packages }
}

// ---------------- M11-02 订单管理（异常标红告警 / 退款 / 对账导出） ----------------

export async function getAdminOrders(params: { page?: number; pageSize?: number; status?: string; keyword?: string; abnormal?: boolean }): Promise<PageBox<AdminOrder>> {
  await delay(350)
  let items = [...mockOrdersData]
  if (params.status) items = items.filter((o) => o.status === params.status)
  if (params.abnormal) items = items.filter((o) => o.abnormal)
  if (params.keyword) {
    const k = params.keyword.trim()
    items = items.filter((o) => o.id.includes(k) || o.userPhone.includes(k))
  }
  const page = params.page ?? 1
  const pageSize = params.pageSize ?? 20
  return { items: items.slice((page - 1) * pageSize, page * pageSize), total: items.length, page, pageSize }
}

export async function processRefund(session: AdminSession, orderId: string, action: 'approve' | 'reject', reason?: string): Promise<{ orderId: string; status: OrderStatus; message: string }> {
  await delay(350)
  const order = mockOrdersData.find((o) => o.id === orderId)
  if (order) {
    order.status = action === 'approve' ? 'refunded' : 'paid'
    order.statusLabel = action === 'approve' ? '已退款' : '已支付'
  }
  writeAudit(session, action === 'approve' ? '同意退款' : '驳回退款', `订单 ${orderId}`, reason ? `原因：${reason}` : '')
  return {
    orderId,
    status: action === 'approve' ? 'refunded' : 'paid',
    message: action === 'approve' ? '已同意退款，24 小时内原路到账' : '已驳回退款申请'
  }
}

export const ORDER_ABNORMAL_LABEL: Record<string, string> = {
  paid_no_delivery: '已支付未交付（超 2 小时）',
  callback_missing: '支付回调缺失'
}

// ---------------- M11-03 商机库管理（新增 / 编辑 / 上下架 / 批量导入 / 审核） ----------------

const mockOppsData: AdminOpportunity[] = [
  { id: 'OP-2001', title: '社区团购团长（兼职）', category: '社区零售', city: '全国', capitalMin: 5000, capitalMax: 20000, paybackMonths: 3, marginPercent: 28, difficultyStars: 2, source: '案例库', status: 'passed', statusLabel: '已通过', onShelf: true, createdAt: '2026-09-20 10:00' },
  { id: 'OP-2002', title: '上门宠物洗护（轻资产）', category: '本地生活', city: '上海', capitalMin: 30000, capitalMax: 80000, paybackMonths: 6, marginPercent: 45, difficultyStars: 3, source: '案例库', status: 'passed', statusLabel: '已通过', onShelf: true, createdAt: '2026-09-21 14:22' },
  { id: 'OP-2003', title: '夜市柠檬茶摊', category: '餐饮小吃', city: '长沙', capitalMin: 8000, capitalMax: 15000, paybackMonths: 2, marginPercent: 62, difficultyStars: 1, source: '批量导入', status: 'passed', statusLabel: '已通过', onShelf: false, createdAt: '2026-09-25 09:12' },
  { id: 'OP-2004', title: '亲子手工体验馆', category: '教育亲子', city: '成都', capitalMin: 80000, capitalMax: 200000, paybackMonths: 12, marginPercent: 35, difficultyStars: 4, source: '案例库', status: 'pending', statusLabel: '待审核', onShelf: false, createdAt: '2026-10-01 16:30' },
  { id: 'OP-2005', title: '社区早餐档口', category: '餐饮小吃', city: '广州', capitalMin: 15000, capitalMax: 40000, paybackMonths: 5, marginPercent: 40, difficultyStars: 2, source: '批量导入', status: 'rejected', statusLabel: '已驳回', onShelf: false, createdAt: '2026-10-02 11:40' }
]

export async function getAdminOpportunities(params: { page?: number; pageSize?: number; status?: string; keyword?: string }): Promise<PageBox<AdminOpportunity>> {
  await delay(350)
  let items = [...mockOppsData]
  if (params.status) items = items.filter((o) => o.status === params.status)
  if (params.keyword) {
    const k = params.keyword.trim()
    items = items.filter((o) => o.title.includes(k) || o.category.includes(k) || o.city.includes(k))
  }
  const page = params.page ?? 1
  const pageSize = params.pageSize ?? 20
  return { items: items.slice((page - 1) * pageSize, page * pageSize), total: items.length, page, pageSize }
}

export async function saveOpportunity(session: AdminSession, input: Partial<AdminOpportunity> & { id?: string }): Promise<AdminOpportunity> {
  await delay(300)
  if (input.id) {
    const old = mockOppsData.find((o) => o.id === input.id)
    if (old) Object.assign(old, input, { status: old.status, statusLabel: old.statusLabel })
    writeAudit(session, '编辑商机', input.id || '', `编辑商机：${input.title}`)
    return old as AdminOpportunity
  }
  const item: AdminOpportunity = {
    id: `OP-${Date.now()}`,
    title: input.title || '',
    category: input.category || '未分类',
    city: input.city || '全国',
    capitalMin: Number(input.capitalMin) || 0,
    capitalMax: Number(input.capitalMax) || 0,
    paybackMonths: Number(input.paybackMonths) || 0,
    marginPercent: Number(input.marginPercent) || 0,
    difficultyStars: Number(input.difficultyStars) || 1,
    source: '手动新增',
    status: 'pending',
    statusLabel: '待审核',
    onShelf: false,
    createdAt: new Date().toISOString().slice(0, 10)
  }
  mockOppsData.unshift(item)
  writeAudit(session, '新增商机', item.id, `新增商机：${item.title}`)
  return item
}

export async function toggleOpportunityShelf(session: AdminSession, id: string, onShelf: boolean): Promise<{ id: string; onShelf: boolean; message: string }> {
  await delay(250)
  const item = mockOppsData.find((o) => o.id === id)
  if (item) item.onShelf = onShelf
  writeAudit(session, onShelf ? '上架商机' : '下架商机', id, onShelf ? '商机已对用户端生效' : '商机已从用户端下线')
  return { id, onShelf, message: onShelf ? '已上架（5 分钟内对用户端生效）' : '已下架（立即对用户端下线）' }
}

export async function importOpportunities(session: AdminSession, items: AdminOpportunity[]): Promise<{ imported: number; rejected: number; errors: string[] }> {
  await delay(450)
  mockOppsData.unshift(...items)
  writeAudit(session, '批量导入商机', `${items.length} 条`, `导入 ${items.length} 条商机，进入待审核`)
  return { imported: items.length, rejected: 0, errors: [] }
}

export async function reviewOpportunity(session: AdminSession, id: string, action: 'approve' | 'reject', reason?: string): Promise<{ id: string; status: ReviewStatus; message: string }> {
  await delay(300)
  const item = mockOppsData.find((o) => o.id === id)
  if (item) {
    item.status = action === 'approve' ? 'passed' : 'rejected'
    item.statusLabel = action === 'approve' ? '已通过' : '已驳回'
  }
  writeAudit(session, action === 'approve' ? '通过商机' : '驳回商机', id, reason ? `原因：${reason}` : '')
  return { id, status: action === 'approve' ? 'passed' : 'rejected', message: action === 'approve' ? '已通过' : '已驳回' }
}

// ---------------- M11-04 提示词配置（版本历史与一键回滚） ----------------

const mockPromptsData: PromptItem[] = [
  {
    key: 'diagnose',
    name: '生意诊断 · 分析提示词',
    content: '你是资深生意顾问。请根据用户的三项条件（资金档、时间档、城市等级）给出客观诊断：当前适合哪些方向、每个方向的核心机会与风险。要求语言通俗、结论明确。',
    model: 'doubao-seed-1.6',
    updatedAt: '2026-10-03 10:20',
    versions: [
      { version: 1, content: '你是资深生意顾问。请根据用户条件给出诊断结论。', model: 'default', updatedAt: '2026-09-25 09:00', operator: 'admin' },
      { version: 2, content: '你是资深生意顾问。请根据用户的三项条件（资金档、时间档、城市等级）给出客观诊断。', model: 'doubao-lite', updatedAt: '2026-09-30 14:30', operator: 'admin' },
      { version: 3, content: '你是资深生意顾问。请根据用户的三项条件（资金档、时间档、城市等级）给出客观诊断：当前适合哪些方向、每个方向的核心机会与风险。要求语言通俗、结论明确。', model: 'doubao-seed-1.6', updatedAt: '2026-10-03 10:20', operator: 'operator' }
    ]
  },
  {
    key: 'match',
    name: '商机匹配 · 打分提示词',
    content: '根据诊断结果与商机库数据，按市场热度、投入匹配度、回本周期、难度、风险五个维度打分（1-100），并给出 3 个最优商机排序。',
    model: 'doubao-seed-1.6',
    updatedAt: '2026-10-02 09:15',
    versions: [
      { version: 1, content: '根据诊断结果匹配 3 个商机。', model: 'default', updatedAt: '2026-09-26 11:00', operator: 'admin' },
      { version: 2, content: '根据诊断结果与商机库数据，按市场热度、投入匹配度、回本周期、难度、风险五个维度打分（1-100），并给出 3 个最优商机排序。', model: 'doubao-seed-1.6', updatedAt: '2026-10-02 09:15', operator: 'operator' }
    ]
  },
  {
    key: 'package',
    name: '启动包 · 交付物生成提示词',
    content: '为用户生成 10 件启动包交付物：可行性评分卡、回本测算表、客户画像、供应商线索、定价方案、开店流程、获客文案、店名物料、30 天日历、风险清单。全部使用中文，可直接使用。',
    model: 'doubao-seed-1.6',
    updatedAt: '2026-10-01 16:00',
    versions: [
      { version: 1, content: '生成启动包 10 件交付物。', model: 'default', updatedAt: '2026-09-27 10:00', operator: 'admin' },
      { version: 2, content: '为用户生成 10 件启动包交付物：可行性评分卡、回本测算表、客户画像、供应商线索、定价方案、开店流程、获客文案、店名物料、30 天日历、风险清单。全部使用中文，可直接使用。', model: 'doubao-seed-1.6', updatedAt: '2026-10-01 16:00', operator: 'operator' }
    ]
  },
  {
    key: 'templates',
    name: '获客文案 · 模板提示词',
    content: '根据商机类型生成 10 条获客文案：3 条朋友圈、4 条短视频脚本、3 条私聊开场白。每条 50 字以内，语气自然，可直接改用。',
    model: 'doubao-lite',
    updatedAt: '2026-09-29 15:40',
    versions: [
      { version: 1, content: '生成获客文案模板 10 条。', model: 'default', updatedAt: '2026-09-28 09:30', operator: 'admin' },
      { version: 2, content: '根据商机类型生成 10 条获客文案：3 条朋友圈、4 条短视频脚本、3 条私聊开场白。每条 50 字以内，语气自然，可直接改用。', model: 'doubao-lite', updatedAt: '2026-09-29 15:40', operator: 'operator' }
    ]
  }
]

export async function getAdminPrompts(): Promise<{ items: PromptItem[]; notice: string }> {
  await delay(300)
  return { items: mockPromptsData.map((p) => ({ ...p, versions: p.versions.map((v) => ({ ...v })) })), notice: '修改后无需发版即可生效；支持版本历史与一键回滚（M11-04）' }
}

export async function saveAdminPrompt(session: AdminSession, key: string, patch: { content?: string; model?: string }): Promise<PromptItem> {
  await delay(300)
  const item = mockPromptsData.find((p) => p.key === key)!
  const nextVersion = Math.max(0, ...item.versions.map((v) => v.version)) + 1
  item.versions.push({
    version: nextVersion,
    content: patch.content ?? item.content,
    model: patch.model ?? item.model,
    updatedAt: new Date().toLocaleString('zh-CN'),
    operator: session.name
  })
  item.content = patch.content ?? item.content
  item.model = patch.model ?? item.model
  item.updatedAt = `刚刚（v${nextVersion}）`
  writeAudit(session, '保存提示词', key, `v${nextVersion}，模型 ${item.model}`)
  return item
}

export async function rollbackPrompt(session: AdminSession, key: string, version: number): Promise<PromptItem> {
  await delay(300)
  const item = mockPromptsData.find((p) => p.key === key)!
  const v = item.versions.find((x) => x.version === version)
  if (!v) throw new Error('版本不存在')
  item.content = v.content
  item.model = v.model
  item.updatedAt = `已回滚至 v${version}（${v.updatedAt}）`
  writeAudit(session, '回滚提示词', key, `回滚至 v${version}`)
  return item
}

// ---------------- M11-06 / M11-09 内容审核（批量处理 / 申诉 / 一键下架） ----------------

const mockReviewsData: ReviewItem[] = [
  { id: 'RV-3001', type: '获客文案', content: '夜市柠檬茶摊开业福利：买一送一，欢迎来打卡！', result: null, status: 'pending', statusLabel: '待审核', reason: null, appeal: false, appealReason: null, createdAt: '2026-10-05 10:01' },
  { id: 'RV-3002', type: '店名物料', content: '店名方案：发财茶摊（含 SVG 海报 1 张）', result: null, status: 'pending', statusLabel: '待审核', reason: null, appeal: false, appealReason: null, createdAt: '2026-10-05 10:05' },
  { id: 'RV-3003', type: '朋友圈文案', content: '今日出摊！首单立减 5 元，私聊我拿优惠券。', result: '命中敏感词：诱导私聊', status: 'rejected', statusLabel: '已拦截', reason: '含营销诱导类敏感词', appeal: true, appealReason: '文案仅为常规促销话术，请人工复核', createdAt: '2026-10-05 10:12' },
  { id: 'RV-3004', type: '供应商线索', content: '本地批发市场 3 家 + 线上货源平台 2 个方向', result: null, status: 'passed', statusLabel: '已通过', reason: null, appeal: false, appealReason: null, createdAt: '2026-10-05 09:20' },
  { id: 'RV-3005', type: '短视频脚本', content: '15 秒短视频脚本：展示出摊过程 + 顾客反馈', result: null, status: 'pending', statusLabel: '待审核', reason: null, appeal: false, appealReason: null, createdAt: '2026-10-05 11:02' }
]

export async function getAdminReviews(params: { page?: number; pageSize?: number; status?: string; keyword?: string }): Promise<PageBox<ReviewItem>> {
  await delay(350)
  let items = [...mockReviewsData]
  if (params.status) items = items.filter((r) => r.status === params.status)
  if (params.keyword) {
    const k = params.keyword.trim()
    items = items.filter((r) => r.type.includes(k) || r.content.includes(k))
  }
  const page = params.page ?? 1
  const pageSize = params.pageSize ?? 20
  return { items: items.slice((page - 1) * pageSize, page * pageSize), total: items.length, page, pageSize }
}

export async function reviewAction(session: AdminSession, id: string, action: 'pass' | 'reject', reason?: string): Promise<{ id: string; status: ReviewStatus; message: string }> {
  await delay(280)
  const item = mockReviewsData.find((r) => r.id === id)
  if (item) {
    item.status = action === 'pass' ? 'passed' : 'rejected'
    item.statusLabel = action === 'pass' ? '已通过' : '已拦截'
    item.result = action === 'pass' ? null : (reason || '人工复核拦截')
    item.reason = action === 'pass' ? null : (reason || '人工复核拦截')
  }
  writeAudit(session, action === 'pass' ? '审核通过内容' : '拦截内容', id, reason ? `原因：${reason}` : '')
  return { id, status: action === 'pass' ? 'passed' : 'rejected', message: action === 'pass' ? '已通过' : '已拦截' }
}

export async function batchReviewAction(session: AdminSession, ids: string[], action: 'pass' | 'reject'): Promise<{ count: number; message: string }> {
  await delay(400)
  let count = 0
  for (const id of ids) {
    const item = mockReviewsData.find((r) => r.id === id)
    if (!item || item.status !== 'pending') continue
    item.status = action === 'pass' ? 'passed' : 'rejected'
    item.statusLabel = action === 'pass' ? '已通过' : '已拦截'
    item.result = action === 'pass' ? null : '批量拦截'
    count++
  }
  writeAudit(session, `批量${action === 'pass' ? '通过' : '拦截'}`, `${count} 条`, `内容审核批量操作 ${count} 条`)
  return { count, message: `批量操作完成：${count} 条` }
}

export async function appealReview(session: AdminSession, id: string, action: 'approve' | 'reject'): Promise<{ id: string; status: ReviewStatus; message: string }> {
  await delay(300)
  const item = mockReviewsData.find((r) => r.id === id)
  if (item && action === 'approve') {
    item.status = 'passed'
    item.statusLabel = '已通过'
    item.reason = null
    item.appeal = false
  }
  writeAudit(session, action === 'approve' ? '通过申诉' : '驳回申诉', id, action === 'approve' ? '申诉通过，内容恢复' : '')
  return { id, status: action === 'approve' ? 'passed' : item?.status || 'rejected', message: action === 'approve' ? '申诉已通过，内容恢复展示' : '申诉已驳回' }
}

export async function forceOfflineReview(session: AdminSession, id: string): Promise<{ id: string; message: string }> {
  await delay(280)
  const item = mockReviewsData.find((r) => r.id === id)
  if (item) {
    item.status = 'rejected'
    item.statusLabel = '已拦截'
    item.result = '一键下架'
    item.reason = '运营一键下架（违规）'
  }
  writeAudit(session, '一键下架内容', id, '违规内容一键下架，用户端立即不可见')
  return { id, message: '已下架，违规内容 1 分钟内对用户端不可见' }
}

// ---------------- M11-07 权限管理（四角色：管理员 / 运营 / 客服 / 财务） ----------------

const ROLE_PERMS: { key: string; label: string }[] = [
  { key: 'dashboard', label: '数据看板' },
  { key: 'users', label: '用户管理' },
  { key: 'orders', label: '订单管理' },
  { key: 'refund', label: '退款处理' },
  { key: 'opps', label: '商机库管理' },
  { key: 'prompts', label: '提示词配置' },
  { key: 'reviews', label: '内容审核' },
  { key: 'roles', label: '权限管理' },
  { key: 'audit', label: '审计日志' },
  { key: 'ops', label: '运营位配置' },
  { key: 'export', label: '数据导出' }
]

const mockRolesData: RoleItem[] = [
  {
    role: 'admin',
    name: '管理员',
    description: '全部权限，含权限管理与审计日志（基础权限不可关闭）',
    perms: ROLE_PERMS.map((p) => ({ ...p, enabled: true }))
  },
  {
    role: 'operator',
    name: '运营',
    description: '日常运营：看板 / 商机 / 提示词 / 内容审核 / 运营位',
    perms: ROLE_PERMS.map((p) => ({ ...p, enabled: ['dashboard', 'opps', 'prompts', 'reviews', 'ops'].includes(p.key) }))
  },
  {
    role: 'support',
    name: '客服',
    description: '用户与订单服务：用户查看 / 订单查看 / 退款处理',
    perms: ROLE_PERMS.map((p) => ({ ...p, enabled: ['users', 'orders', 'refund'].includes(p.key) }))
  },
  {
    role: 'finance',
    name: '财务',
    description: '对账与退款：订单 / 退款 / 数据导出',
    perms: ROLE_PERMS.map((p) => ({ ...p, enabled: ['orders', 'refund', 'export'].includes(p.key) }))
  }
]

export async function getAdminRoles(): Promise<{ items: RoleItem[]; notice: string }> {
  await delay(300)
  return { items: mockRolesData.map((r) => ({ ...r, perms: r.perms.map((p) => ({ ...p })) })), notice: '角色分级：管理员 / 运营 / 客服 / 财务，遵循最小权限原则；每项操作均记录操作人' }
}

export async function saveAdminRole(session: AdminSession, role: AdminRole, perms: RolePerm[]): Promise<RoleItem> {
  await delay(300)
  const item = mockRolesData.find((r) => r.role === role)!
  item.perms = perms
  writeAudit(session, '修改权限', role, `保存角色 ${role} 的权限配置`)
  return item
}

export type RolePerm = { key: string; label: string; enabled: boolean }

// ---------------- M11-08 审计日志（保留 ≥ 180 天，不可篡改） ----------------

const mockAuditData: AuditLogItem[] = [
  { id: 'A-9001', operator: '系统管理员', role: '管理员', action: '登录', target: '后台', detail: '账号 admin 通过账号密码 + TOTP 二次验证登录', createdAt: '2026-10-05 11:20:30' },
  { id: 'A-9002', operator: '运营小王', role: '运营', action: '保存提示词', target: 'diagnose', detail: 'v3，模型 doubao-seed-1.6', createdAt: '2026-10-03 10:20:44' },
  { id: 'A-9003', operator: '系统管理员', role: '管理员', action: '同意退款', target: 'ORD-2026-0005', detail: '用户重复购买，申请退款', createdAt: '2026-10-04 09:25:11' },
  { id: 'A-9004', operator: '运营小王', role: '运营', action: '上架商机', target: 'OP-2001', detail: '商机已对用户端生效', createdAt: '2026-10-04 14:02:19' },
  { id: 'A-9005', operator: '客服小张', role: '客服', action: '拦截内容', target: 'RV-3003', detail: '含营销诱导类敏感词', createdAt: '2026-10-05 10:12:05' }
]

export async function getAdminAuditLogs(params: { page?: number; pageSize?: number; operator?: string; action?: string }): Promise<PageBox<AuditLogItem>> {
  await delay(350)
  let items = [...mockAuditData]
  if (params.operator) items = items.filter((a) => a.operator.includes(params.operator!))
  if (params.action) items = items.filter((a) => a.action.includes(params.action!))
  const page = params.page ?? 1
  const pageSize = params.pageSize ?? 20
  return { items: items.slice((page - 1) * pageSize, page * pageSize), total: items.length, page, pageSize }
}

function writeAudit(session: AdminSession, action: string, target: string, detail: string): void {
  mockAuditData.unshift({
    id: `A-${Date.now()}`,
    operator: session.name,
    role: ROLE_NAME[session.role],
    action,
    target,
    detail,
    createdAt: new Date().toLocaleString('zh-CN', { hour12: false })
  })
}

export const ROLE_NAME: Record<AdminRole, string> = {
  admin: '管理员',
  operator: '运营',
  support: '客服',
  finance: '财务'
}

// ---------------- M11-10 运营位与活动配置（P2） ----------------

const mockOpsData: OpsSlot[] = [
  { id: 'OP-SLOT-1', name: '首页推荐位 · 商机 1', type: 'recommend', title: '社区团购团长（兼职）', content: '推荐位展示商机标题与摘要', enabled: true, startAt: '2026-10-01 00:00', endAt: '2026-10-31 23:59', updatedAt: '2026-10-01 09:00' },
  { id: 'OP-SLOT-2', name: '新用户活动弹窗', type: 'popup', title: '首单立减 5 元', content: '新用户进入商机结果页弹窗，展示优惠信息', enabled: true, startAt: '2026-10-01 00:00', endAt: '2026-10-15 23:59', updatedAt: '2026-10-01 09:10' },
  { id: 'OP-SLOT-3', name: '月度会员优惠券', type: 'coupon', title: '月度会员立减 10 元券', content: '付费弹窗展示优惠券，券码自动发放', enabled: false, startAt: '2026-10-05 00:00', endAt: '2026-10-20 23:59', updatedAt: '2026-10-05 10:00' }
]

export async function getAdminOps(): Promise<{ items: OpsSlot[]; notice: string }> {
  await delay(300)
  return { items: mockOpsData.map((o) => ({ ...o })), notice: '配置后实时生效（M11-10，P2）' }
}

export async function saveAdminOps(session: AdminSession, item: OpsSlot): Promise<OpsSlot> {
  await delay(300)
  const old = mockOpsData.find((o) => o.id === item.id)
  if (old) Object.assign(old, item, { updatedAt: '刚刚' })
  writeAudit(session, '配置运营位', item.id, `保存运营位：${item.name}`)
  return old as OpsSlot
}

export async function toggleAdminOps(session: AdminSession, id: string, enabled: boolean): Promise<{ id: string; message: string }> {
  await delay(250)
  const item = mockOpsData.find((o) => o.id === id)
  if (item) item.enabled = enabled
  writeAudit(session, enabled ? '启用运营位' : '停用运营位', id, enabled ? '配置已实时生效' : '配置已停用')
  return { id, message: enabled ? '已启用（实时生效）' : '已停用' }
}

// ---------------- M11-11 数据导出中心（P2，单次 ≤ 10 万条） ----------------

export async function exportCenterData(session: AdminSession, kind: 'users' | 'orders' | 'deliveries' | 'events', format: 'csv' | 'json'): Promise<{ fileName: string; content: string; message: string }> {
  await delay(600)
  const rows: Record<string, any>[] =
    kind === 'users'
      ? mockUsersData.map((u) => ({ 用户ID: u.id, 手机号: u.phone, 昵称: u.nickname, 城市: u.city, 会员状态: u.memberLabel, 订单数: u.orderCount, 消费总额: u.totalSpendYuan, 来源渠道: u.source, 注册时间: u.createdAt }))
      : kind === 'orders'
        ? mockOrdersData.map((o) => ({ 订单号: o.id, 用户: o.userPhone, 套餐: o.planName, 金额: o.amountYuan, 状态: o.statusLabel, 渠道: o.channel, 下单时间: o.createdAt, 支付时间: o.paidAt || '', 异常: o.abnormal ? ORDER_ABNORMAL_LABEL[o.abnormalType || ''] || '是' : '否' }))
        : kind === 'deliveries'
          ? mockPackagesData.map((p) => ({ 订单号: p.orderId, 启动包: p.name, 文件数: p.fileCount, 状态: p.status, 生成时间: p.createdAt }))
          : [
              { 事件: 'home_view', 触发: '进入首屏', 参数: '来源渠道/端类型/是否登录' },
              { 事件: 'pay_success', 触发: '支付成功', 参数: '订单号/金额/渠道' },
              { 事件: 'package_generate_done', 触发: '启动包生成完成', 参数: '耗时/成功件数' }
            ]
  const header = Object.keys(rows[0] || {})
  const lines = [header.join(','), ...rows.map((r) => header.map((h) => String(r[h] ?? '').replace(/,/g, '，')).join(','))]
  const content = lines.join('\n')
  const fileName = `生意快启_${kind}_${Date.now()}.${format === 'csv' ? 'csv' : 'json'}`
  writeAudit(session, '数据导出', kind, `导出 ${rows.length} 条（${format.toUpperCase()}）`)
  return { fileName, content, message: `已生成 ${fileName}（${rows.length} 条）` }
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
