// 数据层（D 端）：封装 api 调用，并在无后端时提供 Mock 数据，便于网页端联调与演示。
// 真实接口路径见 docs/api-contract.md；USE_MOCK 由构建常量控制（开发默认开，生产设 false）。
import { api } from '@/services/api'
import type {
  StartupInput,
  PackageResult,
  DeliverableFile,
  UserProfile,
  OrderView,
  Membership,
  InviteInfo,
  ShareStatsRow
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

const MOCK_SHARE_STATS: ShareStatsRow[] = [
  { channel: '微信好友', clicks: 1280, registers: 86, pays: 12 },
  { channel: '朋友圈', clicks: 3420, registers: 210, pays: 31 },
  { channel: '抖音', clicks: 980, registers: 40, pays: 5 },
  { channel: '小红书', clicks: 1560, registers: 95, pays: 14 },
  { channel: '复制链接', clicks: 760, registers: 33, pays: 4 }
]

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
  return api.post<{ taskId: string }>('/api/diagnose/start', input)
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
  return api.get<OrderView[]>('/api/orders')
}

export async function getMembership(): Promise<Membership> {
  if (USE_MOCK) {
    await delay(200)
    return MOCK_MEMBERSHIP
  }
  return api.get<Membership>('/api/membership')
}

export async function getShareStats(): Promise<ShareStatsRow[]> {
  if (USE_MOCK) {
    await delay(400)
    return MOCK_SHARE_STATS
  }
  return api.get<ShareStatsRow[]>('/api/admin/share-stats')
}

export async function getInviteInfo(): Promise<InviteInfo> {
  if (USE_MOCK) {
    await delay(200)
    return MOCK_INVITE
  }
  return api.get<InviteInfo>('/api/invite')
}

export async function phoneLogin(phone: string, code: string): Promise<UserProfile> {
  if (USE_MOCK) {
    await delay(500)
    return { isGuest: false, phone, plan: 'single', inviteCode: 'BF-7Q2X9' }
  }
  return api.post<UserProfile>('/api/auth/phone-login', { phone, code })
}

export async function wechatLogin(): Promise<UserProfile> {
  if (USE_MOCK) {
    await delay(500)
    return { isGuest: false, plan: 'month', inviteCode: 'BF-7Q2X9' }
  }
  return api.post<UserProfile>('/api/auth/wechat-login', {})
}
