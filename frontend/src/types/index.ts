// 前端共享类型：与后端 Pydantic schema（backend/app/schemas）对齐。
// 改后端契约时须同步更新此处。

export type Platform = 'web' | 'weapp' | 'android' | 'ios' | 'harmony' | 'win' | 'mac'
export type Plan = 'none' | 'single' | 'month' | 'year'
export type OrderStatus = 'pending' | 'paid' | 'generating' | 'delivered' | 'refunded' | 'closed'
export type PackageStatus = 'generating' | 'delivered' | 'failed'

// 三要素（M1）
export interface StartupInput {
  capital: number // 启动资金（档位）
  dailyHours: number // 每日可投入时间（档位）
  city: string // 城市
}

// 诊断（M2）
export interface DiagnoseTask {
  taskId: string
  stage: string
  percent: number
  message: string
  tags?: string[]
  heatmapUrl?: string
  cached?: boolean
}

// 商机（M3）
export interface Opportunity {
  id: string
  title: string
  fiveElements: {
    capital: string
    payback: string
    margin: string
    customer: string
    difficulty: string
  }
  cases: string[]
  risks: string[]
}

// 交付物（M4 / D01–D10）
export interface DeliverableFile {
  code: string // D01..D10
  name: string
  fileType: 'pdf' | 'excel' | 'word' | 'png' | 'svg' | 'txt' | 'zip'
  url: string
}

export interface PackageResult {
  orderId: string
  status: PackageStatus
  items: DeliverableFile[]
  zipUrl: string
  retryCount: number
}

// 统一响应（见 docs/api-contract.md）
export interface ApiResult<T = unknown> {
  code: number
  message: string
  data: T
  requestId: string
}

// 错误码中文提示映射（与后端 errors.py 保持一致）
export const ERROR_MESSAGES: Record<number, string> = {
  0: 'ok',
  40001: '请输入启动资金、每日时间和所在城市',
  40002: '当前城市暂不支持，请手动选择',
  40101: '登录已过期，请重新登录',
  40301: '该内容仅付费用户可生成',
  40401: '未找到对应的生意启动包',
  40901: '订单正在生成中，请稍候',
  42901: '操作过于频繁，请稍后再试',
  50001: '服务开小差了，请重试',
  50002: 'AI 服务暂时不可用，已切换备用模型',
  60001: '支付未成功，请重新支付'
}
