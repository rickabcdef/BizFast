/**
 * M6-03 二维码生成 · 纯前端本地渲染（不上传）
 * 基于 qrcode（MIT）自研渲染，支持自定义颜色与中心 Logo、高清导出。负责人: C
 */
import QRCode from 'qrcode'

export interface QROptions {
  text: string
  color: string // 前景色
  bgColor?: string
  size?: number // 导出像素边长
  logoFile?: File | null
}

export async function generateQR(opts: QROptions): Promise<string> {
  const text = (opts.text || '').trim()
  if (!text) throw new Error('请输入链接或文字内容')
  const size = opts.size || 512
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  await QRCode.toCanvas(canvas, text, {
    width: size,
    margin: 1,
    errorCorrectionLevel: 'H',
    color: { dark: opts.color, light: opts.bgColor || '#ffffff' }
  })
  if (opts.logoFile) {
    await drawLogo(canvas, opts.logoFile, size)
  }
  return canvas.toDataURL('image/png')
}

async function drawLogo(canvas: HTMLCanvasElement, file: File, size: number) {
  const dataUrl = await new Promise<string>((resolve, reject) => {
    const fr = new FileReader()
    fr.onload = () => resolve(fr.result as string)
    fr.onerror = () => reject(new Error('Logo 读取失败'))
    fr.readAsDataURL(file)
  })
  const img = await new Promise<HTMLImageElement>((resolve, reject) => {
    const i = new Image()
    i.onload = () => resolve(i)
    i.onerror = () => reject(new Error('Logo 解析失败'))
    i.src = dataUrl
  })
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const logoSize = Math.round(size * 0.22)
  const x = (size - logoSize) / 2
  const y = (size - logoSize) / 2
  // 白色圆角底，避免 Logo 与码点粘连影响识别
  const pad = Math.round(logoSize * 0.12)
  ctx.fillStyle = '#ffffff'
  roundRect(ctx, x - pad, y - pad, logoSize + pad * 2, logoSize + pad * 2, Math.round(logoSize * 0.18))
  ctx.fill()
  ctx.drawImage(img, x, y, logoSize, logoSize)
}

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number
) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}
