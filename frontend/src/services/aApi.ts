// 程序员 A 的模块数据层：M2 诊断 / M3 匹配 / M5 付费 / M9 消息。
// 全部直连真实后端（契约见 docs/api-contract.md），不做前端 Mock——
// 便于「开发即联调」，避免 Mock 掩盖真实契约问题。
// 响应统一为 camelCase（后端 schemas/common.ok() 出口已转换）。
import { api, resolveUrl } from '@/services/api'
import type { Platform, Plan, OrderStatus } from '@/types'

// ---------------- M2 诊断 ----------------
export interface DiagnoseCreateOut {
  taskId: string
  cached: boolean
  status: DiagnoseStatus
  percent: number
}

export type DiagnoseStatus = 'pending' | 'running' | 'ready' | 'failed'

/** M2-07 补充问答（全部可选，可整体跳过）。 */
export interface DiagnoseExtraInput {
  experience?: 'none' | 'some' | 'pro' | null
  mode?: 'offline' | 'online' | 'both' | null
  priority?: 'cost' | 'profit' | 'balance' | null
  skipped?: boolean
}

export interface DiagnoseExtra extends DiagnoseExtraInput {
  skipped?: boolean
}

export interface DiagnoseProgress {
  taskId: string
  status: DiagnoseStatus
  stage: string
  percent: number
  message: string
  stages: string[]
  doneStages: string[]
}

export interface DiagnoseTags {
  capitalLevel: 'low' | 'mid' | 'high' | 'ultra'
  timeLevel: 'part' | 'full' | 'flex'
  cityLevel: 'tier1' | 'new_tier1' | 'tier2' | 'tier3' | 'tier4'
  capitalLabel: string
  timeLabel: string
  cityLabel: string
  labels: string[]
  preferenceLabels: string[]
}

export interface HeatDirection {
  name: string
  heat: number
  reason: string
}

export interface DiagnoseResult {
  taskId: string
  status: DiagnoseStatus
  city: string
  tags: DiagnoseTags | null
  directions: HeatDirection[]
  heatmapUrl: string
  cached: boolean
  degraded: boolean
  caseCount: number
  elapsedMs: number
  extra?: DiagnoseExtra | null
  progress?: DiagnoseProgress
}

/** 提交三要素并创建诊断任务（M2-01）；extra 为 M2-07 的补充问答，可不传。 */
export function createDiagnose(input: {
  capital: number
  dailyHours: number
  city: string
  extra?: DiagnoseExtraInput | null
}): Promise<DiagnoseCreateOut> {
  return api.post<DiagnoseCreateOut>('/api/diagnose', input)
}

/** 真实进度（M2-02）：percent 由后端按已完成阶段数给出，前端不伪造。 */
export function getDiagnoseProgress(taskId: string): Promise<DiagnoseProgress> {
  return api.get<DiagnoseProgress>(`/api/diagnose/${taskId}/progress`)
}

export function getDiagnoseResult(taskId: string): Promise<DiagnoseResult> {
  return api.get<DiagnoseResult>(`/api/diagnose/${taskId}/result`)
}

/** 热度图图片地址（≤30s 生成的第一份可带走成果，M2-04）。 */
export function heatmapSrc(taskId: string): string {
  return resolveUrl(`/api/diagnose/heatmap/${taskId}`)
}

// ---------------- M2-05 分享 ----------------
export interface ShareCardData {
  taskId: string
  imageUrl: string
  title: string
  subtitle: string
  directions: HeatDirection[]
  qrContent: string
  shareText: string
  shareUrl: string
}

/** 分享卡片数据（产品名 + 二维码 + 3 个最热方向）。 */
export function getShareCard(taskId: string): Promise<ShareCardData> {
  return api.get<ShareCardData>(`/api/diagnose/${taskId}/share`)
}

/** 分享卡片图片地址（含产品名称与二维码，可直接保存/分享）。 */
export function shareCardSrc(taskId: string): string {
  return resolveUrl(`/api/diagnose/share-card/${taskId}`)
}

/** 轮询进度直到 ready / failed（M2-02 不造假：只读后端真实状态）。 */
export async function pollDiagnose(
  taskId: string,
  onTick: (p: DiagnoseProgress) => void,
  intervalMs = 700,
  timeoutMs = 120000
): Promise<DiagnoseProgress> {
  const started = Date.now()
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const p = await getDiagnoseProgress(taskId)
    onTick(p)
    if (p.status === 'ready' || p.status === 'failed') return p
    if (Date.now() - started > timeoutMs) return p
    await new Promise((r) => setTimeout(r, intervalMs))
  }
}

// ---------------- M3 商机匹配 ----------------
export interface FiveElements {
  capital: string
  payback: string
  margin: string
  firstCustomer: string
  difficulty: string
}

export interface OppMetrics {
  capitalAmountYuan: number
  capitalMinYuan: number
  capitalMaxYuan: number
  paybackMonths: number
  marginPercent: number
  difficultyStars: number
  recommendScore: number
}

export interface OpportunityCard {
  id: string
  title: string
  icon: string
  category: string
  rank: number
  recommendScore: number
  summary: string
  tags: string[]
  fiveElements: FiveElements
  metrics: OppMetrics
  risks: string[]
  locked: boolean
}

export interface CaseItem {
  title: string
  source: string
  time: string
  highlight: string
}

export interface CostItem {
  item: string
  amount: string
  note: string
}

export interface RevenueItem {
  item: string
  value: string
  note: string
}

export interface OpportunityDetail extends OpportunityCard {
  intro: string
  targetCustomers: string
  channels: string
  skillRequired: string
  costBreakdown: CostItem[]
  revenueEstimate: RevenueItem[]
  cases: CaseItem[]
  stopLoss: string
  steps: string[]
}

export interface MatchList {
  taskId: string
  city: string
  cityTier: string
  caseCount: number
  free: OpportunityCard[]
  locked: OpportunityCard
  totalCandidates: number
}

export function getMatchList(taskId: string): Promise<MatchList> {
  return api.get<MatchList>(`/api/match?taskId=${encodeURIComponent(taskId)}`)
}

export function getMatchDetail(opportunityId: string, taskId?: string): Promise<OpportunityDetail> {
  const q = taskId ? `?taskId=${encodeURIComponent(taskId)}` : ''
  return api.get<OpportunityDetail>(`/api/match/${opportunityId}${q}`)
}

export function toggleFavorite(opportunityId: string): Promise<{ opportunityId: string; favorited: boolean }> {
  return api.post(`/api/match/${opportunityId}/favorite`)
}

// ---------------- M5 付费与订单 ----------------
export interface PlanOption {
  plan: Plan
  name: string
  priceCents: number
  priceLabel: string
  unitLabel: string
  highlight: boolean
  badge: string
  rights: string[]
}

export interface PayParams {
  channel: string
  mode: string
  orderId: string
  amountCents: number
  qrContent: string | null
  redirectUrl: string | null
  prepayId: string | null
  notice: string
}

export interface RiskInfo {
  flagged: boolean
  signal: string | null
  label: string
  notice: string
}

export interface OrderCreateOut {
  orderId: string
  plan: Plan
  amountCents: number
  amountLabel: string
  originalCents: number
  originalLabel: string
  discountCents: number
  discountLabel: string
  couponCode: string | null
  channel: string
  status: OrderStatus
  payParams: PayParams
  reused: boolean
  risk: RiskInfo
}

export interface TimelineItem {
  status: OrderStatus
  label: string
  at: string | null
  done: boolean
  active: boolean
}

export interface OrderView {
  id: string
  plan: Plan
  planName: string
  amountCents: number
  amountLabel: string
  originalCents: number
  originalLabel: string
  discountCents: number
  discountLabel: string
  couponCode: string | null
  platform: Platform
  channel: string
  status: OrderStatus
  statusLabel: string
  matchId: string | null
  packageId: string | null
  packageStatus: string | null
  createdAt: string | null
  paidAt: string | null
  generatingAt: string | null
  deliveredAt: string | null
  refundedAt: string | null
  closedAt: string | null
  timeline: TimelineItem[]
  canRefund: boolean
  refundDeadline: string | null
  risk: RiskInfo
}

export function getPlans(): Promise<{ plans: PlanOption[] }> {
  return api.get<{ plans: PlanOption[] }>('/api/payment/plans')
}

/** V5.0 档位 5：增值加购包（按项计价，成本高、绝不并入标准套餐）。 */
export interface AddonOption {
  addon: string
  name: string
  priceCents: number
  priceLabel: string
  unitLabel: string
}

export function getAddons(): Promise<{ addons: AddonOption[] }> {
  return api.get<{ addons: AddonOption[] }>('/api/payment/addons')
}

export function createOrder(input: {
  plan: Plan
  platform: Platform
  matchId?: string | null
  idempotencyKey?: string | null
  couponCode?: string | null
  autoRenew?: boolean | null
}): Promise<OrderCreateOut> {
  return api.post<OrderCreateOut>('/api/payment/create', {
    plan: input.plan,
    platform: input.platform,
    matchId: input.matchId ?? null,
    idempotencyKey: input.idempotencyKey ?? null,
    couponCode: input.couponCode ?? null,
    autoRenew: input.autoRenew ?? null
  })
}

// ---------------- M5-09 优惠券 / 邀请码 ----------------
export interface CouponValidateOut {
  code: string
  kind: string
  title: string
  discountCents: number
  discountLabel: string
  originalCents: number
  originalLabel: string
  finalCents: number
  finalLabel: string
  rules: string
  notice: string
}

export interface CouponItem {
  code: string
  kind: string
  title: string
  discountType: string
  value: number
  discountLabel: string
  planScope: string
  planScopeLabel: string
  minAmount: number
  usable: boolean
  reason: string
  expiresAt: string | null
}

/** 校验券码（不核销，仅预览能减多少）。失败会抛出带中文 message 的 BizError。 */
export function validateCoupon(code: string, plan: Plan): Promise<CouponValidateOut> {
  return api.post<CouponValidateOut>('/api/payment/coupon/validate', { code, plan })
}

/** 可用优惠码清单（含「不可叠加」规则文案）。 */
export function getCoupons(): Promise<{ items: CouponItem[]; rules: string; hint: string }> {
  return api.get('/api/payment/coupons')
}

// ---------------- M5-08 自动续费 ----------------
export interface SubscriptionView {
  plan: string
  planName: string
  isMember: boolean
  autoRenew: boolean
  renewable: boolean
  expireAt: string | null
  daysLeft: number | null
  renewAt: string | null
  renewNoticeDays: number
  notice: string
  priceCents: number
  priceLabel: string
  message?: string | null
}

export function getSubscription(): Promise<SubscriptionView> {
  return api.get<SubscriptionView>('/api/payment/subscription')
}

export function setAutoRenew(autoRenew: boolean): Promise<SubscriptionView> {
  return api.put<SubscriptionView>('/api/payment/subscription', { autoRenew })
}

/** 一键取消自动续费（PRD：取消入口不超过 3 步）。 */
export function cancelSubscription(): Promise<SubscriptionView> {
  return api.post<SubscriptionView>('/api/payment/subscription/cancel')
}

// ---------------- M5-10 风控 ----------------
export interface RiskOverview {
  hasReview: boolean
  items: { signal: string; label: string; createdAt: string | null }[]
  notice: string
}

export function getRiskOverview(): Promise<RiskOverview> {
  return api.get<RiskOverview>('/api/payment/risk')
}

export function getOrder(orderId: string): Promise<OrderView> {
  return api.get<OrderView>(`/api/payment/order/${orderId}`)
}

/** 模拟渠道回调（本地 PAYMENT_MOCK=true 时用于完成支付；真实环境由渠道回调）。 */
export function payCallback(
  channel: string,
  orderId: string
): Promise<{ orderId: string; status: OrderStatus; statusLabel: string; duplicated: boolean; message: string }> {
  return api.post(`/api/payment/callback/${channel}`, { order_id: orderId, result: 'success' })
}

export function refundOrder(
  orderId: string,
  reason?: string
): Promise<{ orderId: string; status: OrderStatus; statusLabel: string; refundedAt: string | null; message: string }> {
  return api.post('/api/payment/refund', { orderId, reason: reason || null })
}

// ---------------- M9 消息与提醒 ----------------
export type NotifyCategory = 'system' | 'order' | 'package' | 'refund' | 'activity'

export interface NotificationItem {
  id: string
  category: NotifyCategory
  categoryLabel: string
  title: string
  content: string
  link: string | null
  isRead: boolean
  createdAt: string
}

export interface MessagePage {
  items: NotificationItem[]
  unread: number
  total: number
  page: number
  pageSize: number
}

export interface SubscribeItem {
  /** 稳定的能力标识（service_notice / app_push / desktop_notice），不随 camelCase 转换 */
  key: string
  label: string
  description: string
  supported: boolean
  enabled: boolean
  platformNote: string
}

export interface SubscribeInfo {
  platform: string
  items: SubscribeItem[]
  notice: string
}

export interface NotifySetting {
  serviceNotice: boolean
  appPush: boolean
  desktopNotice: boolean
  marketReminder: boolean
  dndEnabled: boolean
  dndStart: string
  dndEnd: string
}

export function getMessages(params: {
  page?: number
  pageSize?: number
  category?: NotifyCategory | null
  unreadOnly?: boolean
}): Promise<MessagePage> {
  const q = new URLSearchParams()
  q.set('page', String(params.page ?? 1))
  q.set('pageSize', String(params.pageSize ?? 20))
  if (params.category) q.set('category', params.category)
  if (params.unreadOnly) q.set('unreadOnly', 'true')
  return api.get<MessagePage>(`/api/notify/messages?${q.toString()}`)
}

export function getUnread(): Promise<{ unread: number }> {
  return api.get<{ unread: number }>('/api/notify/unread')
}

export function markRead(id?: string): Promise<{ updated: number; unread: number }> {
  return api.post(`/api/notify/read${id ? `?id=${encodeURIComponent(id)}` : ''}`)
}

export function getSubscribe(platform: Platform): Promise<SubscribeInfo> {
  return api.get<SubscribeInfo>(`/api/notify/subscribe?platform=${platform}`)
}

export function getNotifySettings(): Promise<NotifySetting> {
  return api.get<NotifySetting>('/api/notify/settings')
}

export function updateNotifySettings(patch: Partial<NotifySetting>): Promise<NotifySetting> {
  return api.put<NotifySetting>('/api/notify/settings', patch)
}
