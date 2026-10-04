// M3-06 横向对比「导出图片」：用 Canvas 在本地画一张表格图，交给 saveDataUrl 下载/存相册。
// 为什么不引第三方截图库：依赖白名单只允许 MIT/Apache/BSD/LGPL，而 Canvas 2D 是各端原生能力，
// H5 / 小程序 / App 都能跑，零额外依赖。
// 配色与设计令牌保持一致（藏蓝底 + 蓝紫主色）。

export interface CompareRow {
  label: string
  /** 与 headers 一一对应；空字符串表示该方案没有这项数据。 */
  values: string[]
}

export interface CompareImageInput {
  title: string
  /** 副信息，例如「上海 · 5–20万 · 全职」。 */
  subtitle: string
  /** 列头（各商机名称），长度 2–3。 */
  headers: string[]
  rows: CompareRow[]
  footer: string
}

const W = 750 // 逻辑宽度（按常见手机屏宽出图）
const PAD = 36
const LABEL_W = 148
const COL_GAP = 12
const DPR = 2
const LINE = 34
const ROW_PAD_Y = 16

const FONT = {
  title: 'bold 34px -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif',
  sub: '22px -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif',
  head: 'bold 24px -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif',
  label: '22px -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif',
  value: 'bold 24px -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif',
  foot: '20px -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif'
}

/** 逐字符换行：中文没有空格，按字符断行最稳。 */
function wrap(ctx: CanvasRenderingContext2D, text: string, maxWidth: number, font: string): string[] {
  ctx.font = font
  const raw = text || '—'
  if (ctx.measureText(raw).width <= maxWidth) return [raw]
  const lines: string[] = []
  let line = ''
  for (const ch of raw) {
    const next = line + ch
    if (line && ctx.measureText(next).width > maxWidth) {
      lines.push(line)
      line = ch
    } else {
      line = next
    }
  }
  if (line) lines.push(line)
  return lines
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  const rr = Math.min(r, h / 2, w / 2)
  ctx.beginPath()
  ctx.moveTo(x + rr, y)
  ctx.lineTo(x + w - rr, y)
  ctx.arcTo(x + w, y, x + w, y + rr, rr)
  ctx.lineTo(x + w, y + h - rr)
  ctx.arcTo(x + w, y + h, x + w - rr, y + h, rr)
  ctx.lineTo(x + rr, y + h)
  ctx.arcTo(x, y + h, x, y + h - rr, rr)
  ctx.lineTo(x, y + rr)
  ctx.arcTo(x, y, x + rr, y, rr)
  ctx.closePath()
}

/**
 * 生成对比表图片，返回 PNG dataURL；环境不支持 Canvas 时返回空串（调用方据此降级提示）。
 */
export function renderCompareImage(input: CompareImageInput): string {
  if (typeof document === 'undefined') return ''
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')
  if (!ctx) return ''

  const cols = input.headers.length
  const colW = (W - PAD * 2 - LABEL_W - COL_GAP * (cols - 1)) / cols
  const colX = (i: number) => PAD + LABEL_W + COL_GAP * (i + 1) + colW * i

  // 先把所有文字断行算出来：测量与绘制共用同一份结果，避免两遍算法不一致。
  const headLines = input.headers.map((h) => wrap(ctx, h, colW - 20, FONT.head))
  const headH = Math.max(...headLines.map((l) => l.length)) * LINE + ROW_PAD_Y * 2

  const rows = input.rows.map((r) => {
    const labelLines = wrap(ctx, r.label, LABEL_W - 20, FONT.label)
    const valueLines = r.values.map((v) => wrap(ctx, v, colW - 20, FONT.value))
    const n = Math.max(labelLines.length, ...valueLines.map((l) => l.length))
    return { label: r.label, labelLines, valueLines, height: n * LINE + ROW_PAD_Y * 2 }
  })

  const footLines = wrap(ctx, input.footer, W - PAD * 2, FONT.foot)
  const height =
    PAD + 44 + 30 + 26 + headH + rows.reduce((s, r) => s + r.height, 0) + 8 + footLines.length * 30 + PAD

  canvas.width = W * DPR
  canvas.height = Math.round(height) * DPR
  ctx.scale(DPR, DPR)
  ctx.textBaseline = 'top'

  // 背景：藏蓝渐变
  const bg = ctx.createLinearGradient(0, 0, W, height)
  bg.addColorStop(0, '#0b1026')
  bg.addColorStop(1, '#1a1140')
  ctx.fillStyle = bg
  ctx.fillRect(0, 0, W, height)

  let y = PAD

  ctx.fillStyle = '#e8ecff'
  ctx.font = FONT.title
  ctx.fillText(input.title, PAD, y)
  y += 44

  ctx.fillStyle = '#8b93b8'
  ctx.font = FONT.sub
  ctx.fillText(input.subtitle, PAD, y)
  y += 30 + 26

  // 表头
  const headGrad = ctx.createLinearGradient(0, 0, W, 0)
  headGrad.addColorStop(0, 'rgba(91,108,255,0.30)')
  headGrad.addColorStop(1, 'rgba(155,92,255,0.30)')
  ctx.fillStyle = headGrad
  roundRect(ctx, PAD, y, W - PAD * 2, headH, 14)
  ctx.fill()

  ctx.font = FONT.head
  ctx.fillStyle = '#c9ccff'
  ctx.fillText('对比项', PAD + 14, y + ROW_PAD_Y)
  headLines.forEach((lines, i) => {
    let ly = y + ROW_PAD_Y
    lines.forEach((ln) => {
      ctx.fillText(ln, colX(i) + 8, ly)
      ly += LINE
    })
  })
  y += headH

  // 数据行
  rows.forEach((r) => {
    ctx.font = FONT.label
    ctx.fillStyle = '#8b93b8'
    let ly = y + ROW_PAD_Y
    r.labelLines.forEach((ln) => {
      ctx.fillText(ln, PAD + 14, ly)
      ly += LINE
    })

    ctx.font = FONT.value
    ctx.fillStyle = '#e8ecff'
    r.valueLines.forEach((lines, ci) => {
      let vy = y + ROW_PAD_Y
      lines.forEach((ln) => {
        ctx.fillText(ln, colX(ci) + 8, vy)
        vy += LINE
      })
    })

    ctx.strokeStyle = 'rgba(139,147,184,0.16)'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(PAD, y + r.height)
    ctx.lineTo(W - PAD, y + r.height)
    ctx.stroke()

    y += r.height
  })

  // 页脚（含产品名，卡片外发也有出处）
  y += 8
  ctx.font = FONT.foot
  ctx.fillStyle = '#8b93b8'
  footLines.forEach((ln) => {
    ctx.fillText(ln, PAD, y)
    y += 30
  })

  try {
    return canvas.toDataURL('image/png')
  } catch {
    return ''
  }
}
