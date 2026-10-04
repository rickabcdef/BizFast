// 分享工具（M8）：复制链接、保存图片、脱敏、生成分享卡片。
// Web 端优先使用浏览器能力；小程序/App 走 Taro 适配（见 utils/platform.ts）。
import Taro from '@tarojs/taro'

// 内容脱敏（M8-06）：分享前自动去除手机号/订单号/邮箱等隐私信息
export function desensitize(text: string): string {
  return text
    .replace(/1[3-9]\d{9}/g, '138****8888')
    .replace(/订单[号]?[:：]?\s*[A-Za-z0-9_-]{6,}/g, '订单号: ****')
    .replace(/[\w.+-]+@[\w.-]+\.\w+/g, '***@***')
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await Taro.setClipboardData({ data: text })
    return true
  } catch {
    return false
  }
}

// 将 dataURL 下载为图片；非 Web 端提示长按保存
export function downloadDataURL(dataUrl: string, fileName: string): void {
  if (Taro.getEnv() === Taro.ENV_TYPE.WEB && typeof document !== 'undefined') {
    const a = document.createElement('a')
    a.href = dataUrl
    a.download = fileName
    a.click()
    return
  }
  Taro.showToast({ title: '请长按图片保存', icon: 'none' })
}

// 在 ctx 上绘制一个占位二维码（真实二维码应由后端 /api/qrcode 下发，此处仅视觉占位）
function paintQR(ctx: CanvasRenderingContext2D, text: string, ox: number, oy: number, size: number): void {
  let seed = 0
  for (let i = 0; i < text.length; i++) seed = (seed * 31 + text.charCodeAt(i)) >>> 0
  const cells = 11
  const cell = size / cells
  ctx.fillStyle = '#0B1026'
  for (let y = 0; y < cells; y++) {
    for (let x = 0; x < cells; x++) {
      seed = (seed * 1103515245 + 12345) >>> 0
      if ((seed >> 16) % 2 === 0) ctx.fillRect(ox + x * cell, oy + y * cell, cell, cell)
    }
  }
  const drawEye = (ex: number, ey: number) => {
    ctx.fillStyle = '#0B1026'
    ctx.fillRect(ex, ey, cell * 3, cell * 3)
    ctx.fillStyle = '#fff'
    ctx.fillRect(ex + cell * 0.5, ey + cell * 0.5, cell * 2, cell * 2)
    ctx.fillStyle = '#0B1026'
    ctx.fillRect(ex + cell, ey + cell, cell, cell)
  }
  drawEye(ox, oy)
  drawEye(ox + size - cell * 3, oy)
  drawEye(ox, oy + size - cell * 3)
}

export function placeholderQR(text: string, size = 120): string {
  if (typeof document === 'undefined') return ''
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')
  if (!ctx) return ''
  ctx.fillStyle = '#fff'
  ctx.fillRect(0, 0, size, size)
  paintQR(ctx, text, 0, 0, size)
  return canvas.toDataURL('image/png')
}

// 将分享卡片绘制为图片并返回 dataURL（保存图片功能使用）
export function buildShareCardCanvas(data: {
  productName: string
  subtitle: string
  lines: string[]
  qrText: string
}): string {
  if (typeof document === 'undefined') return ''
  const W = 640
  const H = 880
  const canvas = document.createElement('canvas')
  canvas.width = W
  canvas.height = H
  const ctx = canvas.getContext('2d')
  if (!ctx) return ''
  const g = ctx.createLinearGradient(0, 0, W, H)
  g.addColorStop(0, '#0B1026')
  g.addColorStop(1, '#1A1140')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, W, H)

  ctx.fillStyle = '#E8ECFF'
  ctx.font = 'bold 40px sans-serif'
  ctx.fillText(data.productName, 40, 90)
  ctx.fillStyle = '#8B93B8'
  ctx.font = '24px sans-serif'
  ctx.fillText(data.subtitle, 40, 130)

  ctx.fillStyle = '#E8ECFF'
  ctx.font = '26px sans-serif'
  let y = 200
  for (const line of data.lines.slice(0, 8)) {
    ctx.fillText('• ' + line, 40, y)
    y += 44
  }

  paintQR(ctx, data.qrText, W - 220, H - 220, 160)
  ctx.fillStyle = '#8B93B8'
  ctx.font = '20px sans-serif'
  ctx.fillText('长按识别 · 生意快启', W - 220, H - 30)
  return canvas.toDataURL('image/png')
}
