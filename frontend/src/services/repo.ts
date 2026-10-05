// 数据层（D 端）：封装 api 调用，并在无后端时提供 Mock 数据，便于网页端联调与演示。
// 真实接口路径严格对齐 docs/api-contract.md；USE_MOCK 由构建常量控制（开发默认开，生产设 false）。
import { api } from '@/services/api'
import type {
  StartupInput,
  PackageResult,
  DeliverableFile,
  UserProfile,
  OrderView,
  Membership,
  InviteInfo,
  ShareStats,
  AuthResult,
  ShareCardData,
  HomeConfig
} from '@/types'

// USE_MOCK 由 frontend/config/index.ts 的 defineConstants 注入（始终有值）
const delay = (ms: number) => new Promise((r) => setTimeout(r, ms))

// ---------------- Mock 数据 ----------------
const D01_D10: DeliverableFile[] = [
  { code: 'D01', name: '最佳商机可行性评分卡', fileType: 'pdf', url: '/mock/D01.pdf' },
  { code: 'D02', name: '回本测算表', fileType: 'excel', url: '/mock/D02.xlsx' },
  { code: 'D03', name: '客户画像与获客清单', fileType: 'pdf', url: '/mock/D03.pdf' },
  { code: 'D04', name: '供应商线索与询价话术', fileType: 'pdf', url: '/mock/D04.pdf' },
  { code: 'D05', name: '定价建议与开业活动方案', fileType: 'pdf', url: '/mock/D05.pdf' },
  { code: 'D06', name: '开店流程清单', fileType: 'pdf', url: '/mock/D06.pdf' },
  { code: 'D07', name: '获客文案模板10条', fileType: 'word', url: '/mock/D07.docx' },
  { code: 'D08', name: '店名与宣传物料', fileType: 'png', url: '/mock/D08.png' },
  { code: 'D09', name: '30天行动日历', fileType: 'pdf', url: '/mock/D09.pdf' },
  { code: 'D10', name: '风险清单与止损线', fileType: 'pdf', url: '/mock/D10.pdf' }
]

const MOCK_PACKAGES: PackageResult[] = [
  { orderId: 'ORD-2026-0001', status: 'delivered', items: D01_D10, zipUrl: '/mock/package.zip', retryCount: 0 }
]

const MOCK_ORDERS: OrderView[] = [
  { orderId: 'ORD-2026-0001', title: '兼职副业·社区团购启动包', status: 'delivered', amount: 39, createdAt: '2026-10-01 20:14' },
  { orderId: 'ORD-2026-0002', title: '月度会员', status: 'paid', amount: 39, createdAt: '2026-10-02 09:30' }
]

const MOCK_MEMBERSHIP: Membership = {
  plan: 'month',
  expireAt: '2026-11-02',
  autoRenew: true
}

const MOCK_SHARE_STATS: ShareStats = {
  rows: [
    { channel: '微信好友', clicks: 1280 },
    { channel: '朋友圈', clicks: 3420 },
    { channel: '抖音', clicks: 980 },
    { channel: '小红书', clicks: 1560 },
    { channel: '复制链接', clicks: 760 }
  ],
  summary: { shares: 8000, registers: 464, pays: 66, shareRate: 0.18 }
}

const MOCK_INVITE: InviteInfo = {
  code: 'BF-7Q2X9',
  link: 'https://bizfast.app/i/BF-7Q2X9',
  coupon: '新人立减 10 元券',
  freeGenerations: 1
}

// ---------------- 接口封装 ----------------
export async function startDiagnose(input: StartupInput): Promise<{ taskId: string }> {
  if (USE_MOCK) {
    await delay(700)
    return { taskId: 'mock-task-001' }
  }
  return api.post<{ taskId: string }>('/api/diagnose', input)
}

export async function getMyPackages(): Promise<PackageResult[]> {
  if (USE_MOCK) {
    await delay(400)
    return MOCK_PACKAGES
  }
  return api.get<PackageResult[]>('/api/packages')
}

export async function getOrders(): Promise<OrderView[]> {
  if (USE_MOCK) {
    await delay(300)
    return MOCK_ORDERS
  }
  return api.get<OrderView[]>('/api/user/orders')
}

export async function getMembership(): Promise<Membership> {
  if (USE_MOCK) {
    await delay(200)
    return MOCK_MEMBERSHIP
  }
  // 会员信息包含在 /api/user/me 中（M10 3.1 账号体系）
  const me = await api.get<UserProfile>('/api/user/me')
  return {
    plan: me.plan === 'none' ? 'single' : (me.plan as Membership['plan']),
    expireAt: me.expireAt || '',
    autoRenew: !!me.autoRenew
  }
}

export async function getShareStats(): Promise<ShareStats> {
  if (USE_MOCK) {
    await delay(400)
    return MOCK_SHARE_STATS
  }
  // M11(D) 分享转化概览（M8-04）
  return api.get<ShareStats>('/api/admin/share/stats')
}

export async function getInviteInfo(): Promise<InviteInfo> {
  if (USE_MOCK) {
    await delay(200)
    return MOCK_INVITE
  }
  // M8-03 我的邀请信息（实时可见）
  return api.get<InviteInfo>('/api/share/invite/info')
}

export async function phoneLogin(phone: string, code: string, inviterCode?: string): Promise<AuthResult> {
  if (USE_MOCK) {
    await delay(500)
    return { token: 'mock-token', user: { isGuest: false, phone, plan: 'single', inviteCode: 'BF-7Q2X9' } }
  }
  // M10 3.1 手机号 + 验证码登录
  return api.post<AuthResult>('/api/auth/login', { phone, code, inviterCode })
}

export async function wechatLogin(unionid?: string): Promise<AuthResult> {
  if (USE_MOCK) {
    await delay(500)
    return { token: 'mock-token', user: { isGuest: false, plan: 'month', inviteCode: 'BF-7Q2X9' } }
  }
  // M10 3.1 微信 unionid 登录（网页端无真实微信 SDK，dev 用占位 unionid）
  return api.post<AuthResult>('/api/auth/wechat', { unionid: unionid || `web-${Date.now()}` })
}

export async function deleteAccount(): Promise<{ deletedAt: string; purgeAt: string }> {
  if (USE_MOCK) {
    await delay(300)
    return { deletedAt: new Date().toISOString(), purgeAt: '' }
  }
  // M10 3.1 注销账号：15 日内清隐私数据
  return api.delete<{ deletedAt: string; purgeAt: string }>('/api/user/account')
}

// ---------------- 分享 / 增长（M8） ----------------
export async function createShareCard(data: ShareCardData): Promise<{ id: string; shareUrl: string }> {
  if (USE_MOCK) {
    await delay(200)
    return { id: 'mock-card', shareUrl: data.qrText || 'https://bizfast.app/s/mock' }
  }
  // M8-01 生成成果分享卡片
  return api.post<{ id: string; shareUrl: string }>('/api/share/card', data)
}

export async function trackShare(cardId: string | null, channel: string): Promise<{ ok: boolean }> {
  if (USE_MOCK) {
    await delay(100)
    return { ok: true }
  }
  // M8-02 分享行为埋点
  return api.post<{ ok: boolean }>('/api/share/track', { cardId, channel })
}

// ---------------- 首屏配置（M1） ----------------
export async function getHomeConfig(): Promise<HomeConfig> {
  if (USE_MOCK) {
    await delay(100)
    return {
      capitals: [
        { label: '1万以下', value: 1 },
        { label: '1–5万', value: 2 },
        { label: '5–20万', value: 3 },
        { label: '20万以上', value: 4 }
      ],
      dailyHours: [
        { label: '兼职（每天约2小时）', value: 2 },
        { label: '全职（每天8小时以上）', value: 8 }
      ],
      cityVersion: '2026.1'
    }
  }
  return api.get<HomeConfig>('/api/home/config')
}
