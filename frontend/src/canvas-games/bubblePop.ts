/**
 * M7-01 指尖解压 · 纯前端 Canvas 自研引擎
 * - 点击/触摸气泡即破，带缩放、粒子爆裂与冲击波反馈
 * - 音效由 WebAudio 实时合成（无第三方素材，等价 CC0/自录）
 * - requestAnimationFrame 驱动，移动端稳定 50FPS+（M7-04）
 * 负责人: C
 */

export interface BubblePopStats {
  popped: number
  total: number
  elapsedSec: number
}

export interface BubblePopOptions {
  cols?: number
  rows?: number
  onStats?: (s: BubblePopStats) => void
  onComplete?: (elapsedSec: number) => void
}

/** 尊重系统「减少动态效果」设置（PRD 性能红线）：开启时降级为无粒子/无冲击波的轻反馈 */
function prefersReducedMotion(): boolean {
  try {
    return typeof window !== 'undefined' && !!window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}

interface Bubble {
  x: number
  y: number
  r: number
  popped: boolean
  popT: number // 0..1 爆破动画进度
  hue: number
  press: number // 按压反馈 0..1
}

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  life: number
  maxLife: number
  size: number
  hue: number
}

interface Shock {
  x: number
  y: number
  r: number
  maxR: number
  life: number
}

const PALETTE_HUES = [232, 268, 210, 290, 250] // 蓝紫色系

export class BubblePopGame {
  private canvas: HTMLCanvasElement
  private ctx: CanvasRenderingContext2D
  private opts: Required<BubblePopOptions>
  private bubbles: Bubble[] = []
  private particles: Particle[] = []
  private shocks: Shock[] = []
  private raf = 0
  private running = false
  private dpr = 1
  private width = 0
  private height = 0
  private popped = 0
  private total = 0
  private startTs: number | null = null
  private muted = false
  private audioCtx: AudioContext | null = null
  private dirty = true
  private lastFrame = 0

  constructor(canvas: HTMLCanvasElement, opts: BubblePopOptions = {}) {
    this.canvas = canvas
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('Canvas 2D 不支持')
    this.ctx = ctx
    this.opts = {
      cols: opts.cols ?? 5,
      rows: opts.rows ?? 6,
      onStats: opts.onStats ?? (() => {}),
      onComplete: opts.onComplete ?? (() => {})
    }
    this.total = this.opts.cols * this.opts.rows
    this.bindEvents()
  }

  setMuted(m: boolean) {
    this.muted = m
  }

  /** 调整画布尺寸（CSS 像素），并重新布局气泡 */
  resize(cssW: number, cssH: number) {
    this.dpr = Math.min(window.devicePixelRatio || 1, 3)
    this.width = cssW
    this.height = cssH
    this.canvas.width = Math.round(cssW * this.dpr)
    this.canvas.height = Math.round(cssH * this.dpr)
    this.canvas.style.width = cssW + 'px'
    this.canvas.style.height = cssH + 'px'
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0)
    this.layout()
    this.dirty = true
  }

  private layout() {
    const { cols, rows } = this.opts
    const pad = 14
    const gap = 12
    const availW = this.width - pad * 2
    const availH = this.height - pad * 2
    const cellW = availW / cols
    const cellH = availH / rows
    const r = Math.min(cellW, cellH) / 2 - gap / 2
    this.bubbles = []
    for (let i = 0; i < rows; i++) {
      for (let j = 0; j < cols; j++) {
        this.bubbles.push({
          x: pad + cellW * (j + 0.5),
          y: pad + cellH * (i + 0.5),
          r,
          popped: false,
          popT: 0,
          hue: PALETTE_HUES[(i + j) % PALETTE_HUES.length],
          press: 0
        })
      }
    }
  }

  private bindEvents() {
    this.canvas.addEventListener('pointerdown', this.onPointerDown)
  }

  private onPointerDown = (e: PointerEvent) => {
    const rect = this.canvas.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    let hit: Bubble | null = null
    for (const b of this.bubbles) {
      if (b.popped) continue
      const dx = x - b.x
      const dy = y - b.y
      if (dx * dx + dy * dy <= b.r * b.r) {
        hit = b
        break
      }
    }
    if (hit) this.pop(hit)
  }

  private pop(b: Bubble) {
    b.popped = true
    b.popT = prefersReducedMotion() ? 1 : 0 // 减少动态效果：跳过缩放动画，立即移除
    this.popped++
    if (this.startTs == null) this.startTs = performance.now()
    if (!prefersReducedMotion()) {
      this.spawnParticles(b)
      this.shocks.push({ x: b.x, y: b.y, r: b.r * 0.6, maxR: b.r * 2.4, life: 1 })
    }
    this.beep()
    this.emitStats()
    this.dirty = true
    if (this.popped >= this.total) {
      const elapsed = (performance.now() - (this.startTs as number)) / 1000
      this.opts.onComplete(elapsed)
    }
  }

  private spawnParticles(b: Bubble) {
    const n = 14
    for (let i = 0; i < n; i++) {
      const ang = (Math.PI * 2 * i) / n + Math.random() * 0.5
      const sp = 1.5 + Math.random() * 3
      this.particles.push({
        x: b.x,
        y: b.y,
        vx: Math.cos(ang) * sp,
        vy: Math.sin(ang) * sp,
        life: 1,
        maxLife: 0.5 + Math.random() * 0.3,
        size: 2 + Math.random() * 3,
        hue: b.hue
      })
    }
  }

  private beep() {
    if (this.muted) return
    try {
      if (!this.audioCtx) {
        const AC = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
        this.audioCtx = new AC()
      }
      const ctx = this.audioCtx
      if (ctx.state === 'suspended') void ctx.resume()
      const t = ctx.currentTime
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = 'sine'
      osc.frequency.setValueAtTime(620 + Math.random() * 240, t)
      osc.frequency.exponentialRampToValueAtTime(180, t + 0.09)
      gain.gain.setValueAtTime(0.0001, t)
      gain.gain.exponentialRampToValueAtTime(0.22, t + 0.01)
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.12)
      osc.connect(gain).connect(ctx.destination)
      osc.start(t)
      osc.stop(t + 0.14)
    } catch {
      /* 音频不可用时静默降级 */
    }
  }

  private emitStats() {
    const elapsed = this.startTs == null ? 0 : (performance.now() - this.startTs) / 1000
    this.opts.onStats({ popped: this.popped, total: this.total, elapsedSec: Math.floor(elapsed) })
  }

  start() {
    if (this.running) return
    this.running = true
    this.lastFrame = performance.now()
    const loop = (now: number) => {
      if (!this.running) return
      const dt = Math.min(0.05, (now - this.lastFrame) / 1000)
      this.lastFrame = now
      this.update(dt)
      if (this.dirty || this.particles.length > 0 || this.shocks.length > 0 || this.hasActivePop()) {
        this.render()
        this.dirty = false
      }
      this.raf = requestAnimationFrame(loop)
    }
    this.raf = requestAnimationFrame(loop)
    this.emitStats()
    this.render()
  }

  private hasActivePop() {
    return this.bubbles.some((b) => b.popped && b.popT < 1)
  }

  reset() {
    this.popped = 0
    this.startTs = null
    this.particles = []
    this.shocks = []
    for (const b of this.bubbles) {
      b.popped = false
      b.popT = 0
      b.press = 0
    }
    this.dirty = true
    this.emitStats()
    this.render()
  }

  private update(dt: number) {
    for (const b of this.bubbles) {
      if (b.popped && b.popT < 1) b.popT = Math.min(1, b.popT + dt * 5)
      if (b.press > 0) b.press = Math.max(0, b.press - dt * 4)
    }
    for (const p of this.particles) {
      p.x += p.vx
      p.y += p.vy
      p.vy += 0.08
      p.vx *= 0.98
      p.life -= dt / p.maxLife
    }
    this.particles = this.particles.filter((p) => p.life > 0)
    for (const s of this.shocks) {
      s.life -= dt * 2.2
      s.r += (s.maxR - s.r) * Math.min(1, dt * 8)
    }
    this.shocks = this.shocks.filter((s) => s.life > 0)
    if (this.startTs != null) this.emitStats()
  }

  private render() {
    const { ctx, width, height } = this
    ctx.clearRect(0, 0, width, height)
    for (const s of this.shocks) {
      ctx.beginPath()
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2)
      ctx.strokeStyle = `hsla(268,90%,70%,${s.life * 0.5})`
      ctx.lineWidth = 2
      ctx.stroke()
    }
    for (const b of this.bubbles) {
      this.drawBubble(b)
    }
    for (const p of this.particles) {
      ctx.beginPath()
      ctx.arc(p.x, p.y, p.size * Math.max(0, p.life), 0, Math.PI * 2)
      ctx.fillStyle = `hsla(${p.hue},85%,68%,${Math.max(0, p.life)})`
      ctx.fill()
    }
  }

  private drawBubble(b: Bubble) {
    const { ctx } = this
    const squish = b.popped ? 1 - b.popT * 0.25 : 1 - b.press * 0.12
    const r = Math.max(0.5, b.r * squish)
    ctx.save()
    ctx.translate(b.x, b.y)
    if (b.popped) {
      ctx.globalAlpha = Math.max(0, 1 - b.popT)
      ctx.beginPath()
      ctx.arc(0, 0, r, 0, Math.PI * 2)
      ctx.fillStyle = 'rgba(255,255,255,0.06)'
      ctx.fill()
      ctx.restore()
      return
    }
    const g = ctx.createRadialGradient(-r * 0.3, -r * 0.35, r * 0.1, 0, 0, r)
    g.addColorStop(0, `hsla(${b.hue},95%,80%,0.95)`)
    g.addColorStop(1, `hsla(${b.hue},80%,55%,0.95)`)
    ctx.beginPath()
    ctx.arc(0, 0, r, 0, Math.PI * 2)
    ctx.fillStyle = g
    ctx.shadowColor = `hsla(${b.hue},90%,60%,0.5)`
    ctx.shadowBlur = 12
    ctx.fill()
    ctx.shadowBlur = 0
    ctx.beginPath()
    ctx.ellipse(-r * 0.3, -r * 0.4, r * 0.22, r * 0.14, -0.5, 0, Math.PI * 2)
    ctx.fillStyle = 'rgba(255,255,255,0.75)'
    ctx.fill()
    ctx.restore()
  }

  destroy() {
    this.running = false
    cancelAnimationFrame(this.raf)
    this.canvas.removeEventListener('pointerdown', this.onPointerDown)
    if (this.audioCtx) void this.audioCtx.close().catch(() => {})
  }
}

export default BubblePopGame
