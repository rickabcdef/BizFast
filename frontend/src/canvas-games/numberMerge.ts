/**
 * M7-02 数字合成 · 纯前端 Canvas 自研引擎
 * - 4×4 滑动合并数字（原创命名，不沿用「2048」等名称，规避商标争议）
 * - 支持键盘方向键与手势滑动；方块平滑位移动画，rAF 驱动 ≥50FPS（M7-04）
 * - 纯免费、无广告、无内购、无体力限制（M7-05）
 * 负责人: C
 */

export interface NumberMergeStats {
  score: number
  best: number
  over: boolean
  won: boolean
}

/** 尊重系统「减少动态效果」设置（PRD 性能红线）：开启时方块位移即时归位，不做平滑动画 */
function prefersReducedMotion(): boolean {
  try {
    return typeof window !== 'undefined' && !!window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}

export interface NumberMergeOptions {
  onStats?: (s: NumberMergeStats) => void
  onMove?: () => void
}

interface Tile {
  id: number
  value: number
  row: number
  col: number
  x: number // 像素中心
  y: number
  scale: number // 出现/合并动画
  merging: boolean
  remove: boolean
}

const SIZE = 4

// 数字 → 配色（科技风渐变，可读性优先）
function tileColor(v: number): { bg: string; fg: string } {
  const map: Record<number, { bg: string; fg: string }> = {
    2: { bg: '#2a3360', fg: '#c9ccff' },
    4: { bg: '#343f7a', fg: '#dfe2ff' },
    8: { bg: '#5b6cff', fg: '#ffffff' },
    16: { bg: '#7b61ff', fg: '#ffffff' },
    32: { bg: '#9b5cff', fg: '#ffffff' },
    64: { bg: '#b14cff', fg: '#ffffff' },
    128: { bg: '#5b8cff', fg: '#ffffff' },
    256: { bg: '#39d9c4', fg: '#06231f' },
    512: { bg: '#39d98a', fg: '#06231a' },
    1024: { bg: '#ffb454', fg: '#3a2400' },
    2048: { bg: '#ff5c7c', fg: '#ffffff' }
  }
  return map[v] || { bg: '#ffd166', fg: '#3a2400' }
}

export class NumberMergeGame {
  private canvas: HTMLCanvasElement
  private ctx: CanvasRenderingContext2D
  private opts: Required<NumberMergeOptions>
  private tiles: Tile[] = []
  private grid: (Tile | null)[][] = []
  private score = 0
  private best = 0
  private over = false
  private won = false
  private wonNotified = false
  private dpr = 1
  private cssSize = 0
  private padding = 12
  private gap = 10
  private cell = 0
  private raf = 0
  private running = false
  private lastFrame = 0
  private nextId = 1
  private pointerStart: { x: number; y: number } | null = null
  private animating = false

  constructor(canvas: HTMLCanvasElement, opts: NumberMergeOptions = {}) {
    this.canvas = canvas
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('Canvas 2D 不支持')
    this.ctx = ctx
    this.opts = {
      onStats: opts.onStats ?? (() => {}),
      onMove: opts.onMove ?? (() => {})
    }
    this.best = this.loadBest()
    this.bindInput()
  }

  private loadBest(): number {
    try {
      return Number(localStorage.getItem('bf_num_merge_best') || '0') || 0
    } catch {
      return 0
    }
  }

  private saveBest() {
    try {
      localStorage.setItem('bf_num_merge_best', String(this.best))
    } catch {
      /* ignore */
    }
  }

  /** cssSize: 棋盘 CSS 边长（正方形） */
  resize(cssSize: number) {
    this.dpr = Math.min(window.devicePixelRatio || 1, 3)
    this.cssSize = cssSize
    this.canvas.width = Math.round(cssSize * this.dpr)
    this.canvas.height = Math.round(cssSize * this.dpr)
    this.canvas.style.width = cssSize + 'px'
    this.canvas.style.height = cssSize + 'px'
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0)
    this.cell = (cssSize - this.padding * 2 - this.gap * (SIZE - 1)) / SIZE
    for (const t of this.tiles) this.snapTile(t)
    this.render()
  }

  private cellCenter(row: number, col: number) {
    return {
      x: this.padding + col * (this.cell + this.gap) + this.cell / 2,
      y: this.padding + row * (this.cell + this.gap) + this.cell / 2
    }
  }

  private snapTile(t: Tile) {
    const c = this.cellCenter(t.row, t.col)
    t.x = c.x
    t.y = c.y
  }

  private emptyGrid() {
    this.grid = Array.from({ length: SIZE }, () => Array<Tile | null>(SIZE).fill(null))
  }

  newGame() {
    this.tiles = []
    this.score = 0
    this.over = false
    this.won = false
    this.wonNotified = false
    this.emptyGrid()
    this.addRandomTile()
    this.addRandomTile()
    this.emit()
    this.render()
  }

  private addRandomTile() {
    const empties: { row: number; col: number }[] = []
    for (let r = 0; r < SIZE; r++)
      for (let c = 0; c < SIZE; c++) if (!this.grid[r][c]) empties.push({ row: r, col: c })
    if (!empties.length) return
    const spot = empties[Math.floor(Math.random() * empties.length)]
    const value = Math.random() < 0.9 ? 2 : 4
    const tile: Tile = {
      id: this.nextId++,
      value,
      row: spot.row,
      col: spot.col,
      x: 0,
      y: 0,
      scale: 0,
      merging: false,
      remove: false
    }
    this.snapTile(tile)
    this.grid[spot.row][spot.col] = tile
    this.tiles.push(tile)
    this.animating = true
  }

  private bindInput() {
    window.addEventListener('keydown', this.onKey)
    this.canvas.addEventListener('pointerdown', this.onPointerDown)
    this.canvas.addEventListener('pointerup', this.onPointerUp)
  }

  private onKey = (e: KeyboardEvent) => {
    if (this.over) return
    const map: Record<string, 'up' | 'down' | 'left' | 'right'> = {
      ArrowUp: 'up',
      ArrowDown: 'down',
      ArrowLeft: 'left',
      ArrowRight: 'right',
      w: 'up',
      s: 'down',
      a: 'left',
      d: 'right'
    }
    const dir = map[e.key]
    if (!dir) return
    e.preventDefault()
    this.move(dir)
  }

  private onPointerDown = (e: PointerEvent) => {
    const rect = this.canvas.getBoundingClientRect()
    this.pointerStart = { x: e.clientX - rect.left, y: e.clientY - rect.top }
  }

  private onPointerUp = (e: PointerEvent) => {
    if (!this.pointerStart || this.over) {
      this.pointerStart = null
      return
    }
    const rect = this.canvas.getBoundingClientRect()
    const dx = e.clientX - rect.left - this.pointerStart.x
    const dy = e.clientY - rect.top - this.pointerStart.y
    this.pointerStart = null
    const ax = Math.abs(dx)
    const ay = Math.abs(dy)
    if (Math.max(ax, ay) < 24) return
    if (ax > ay) this.move(dx > 0 ? 'right' : 'left')
    else this.move(dy > 0 ? 'down' : 'up')
  }

  /** 执行一次移动；返回是否发生变化 */
  move(dir: 'up' | 'down' | 'left' | 'right') {
    if (this.over || this.animating) return
    const traversals = this.buildTraversals(dir)
    const vec = { up: [-1, 0], down: [1, 0], left: [0, -1], right: [0, 1] }[dir]
    let moved = false
    const mergedThisMove: Tile[] = []

    for (const r of traversals.rows) {
      for (const c of traversals.cols) {
        const tile = this.grid[r][c]
        if (!tile) continue
        const { farthest, next } = this.findFarthest(r, c, vec)
        const nextTile = next ? this.grid[next.row][next.col] : null
        if (nextTile && nextTile.value === tile.value && !mergedThisMove.includes(nextTile)) {
          // 合并
          const merged: Tile = {
            id: this.nextId++,
            value: tile.value * 2,
            row: next.row,
            col: next.col,
            x: this.cellCenter(next.row, next.col).x,
            y: this.cellCenter(next.row, next.col).y,
            scale: 1.2,
            merging: true,
            remove: false
          }
          this.grid[next.row][next.col] = merged
          this.grid[r][c] = null
          // 原两块向合并点移动后移除
          tile.row = next.row
          tile.col = next.col
          tile.remove = true
          nextTile.remove = true
          this.tiles.push(merged)
          mergedThisMove.push(merged)
          this.score += merged.value
          if (merged.value >= 2048 && !this.won) {
            this.won = true
          }
          moved = true
        } else if (farthest.row !== r || farthest.col !== c) {
          this.grid[farthest.row][farthest.col] = tile
          this.grid[r][c] = null
          tile.row = farthest.row
          tile.col = farthest.col
          moved = true
        }
      }
    }

    if (moved) {
      this.animating = true
      if (this.score > this.best) {
        this.best = this.score
        this.saveBest()
      }
      this.addRandomTile()
      this.opts.onMove()
      this.emit()
      if (!this.movesAvailable()) {
        this.over = true
        this.emit()
      }
    }
  }

  private buildTraversals(dir: string) {
    const rows = [0, 1, 2, 3]
    const cols = [0, 1, 2, 3]
    if (dir === 'down') rows.reverse()
    if (dir === 'right') cols.reverse()
    return { rows, cols }
  }

  private findFarthest(r: number, c: number, vec: number[]) {
    let prev: { row: number; col: number }
    let cur = { row: r, col: c }
    do {
      prev = cur
      cur = { row: prev.row + vec[0], col: prev.col + vec[1] }
    } while (this.inBounds(cur.row, cur.col) && !this.grid[cur.row][cur.col])
    return { farthest: prev, next: this.inBounds(cur.row, cur.col) ? cur : null }
  }

  private inBounds(r: number, c: number) {
    return r >= 0 && r < SIZE && c >= 0 && c < SIZE
  }

  private movesAvailable(): boolean {
    for (let r = 0; r < SIZE; r++)
      for (let c = 0; c < SIZE; c++) {
        if (!this.grid[r][c]) return true
        const v = this.grid[r][c]!.value
        if (c + 1 < SIZE && this.grid[r][c + 1]?.value === v) return true
        if (r + 1 < SIZE && this.grid[r + 1][c]?.value === v) return true
      }
    return false
  }

  private emit() {
    this.opts.onStats({ score: this.score, best: this.best, over: this.over, won: this.won && !this.wonNotified })
    if (this.won) this.wonNotified = true
  }

  start() {
    if (this.running) return
    this.running = true
    if (!this.tiles.length) this.newGame()
    this.lastFrame = performance.now()
    const loop = (now: number) => {
      if (!this.running) return
      const dt = Math.min(0.05, (now - this.lastFrame) / 1000)
      this.lastFrame = now
      this.update(dt)
      this.render()
      this.raf = requestAnimationFrame(loop)
    }
    this.raf = requestAnimationFrame(loop)
  }

  private update(dt: number) {
    if (prefersReducedMotion()) {
      // 减少动态效果：即时归位，不做插值动画
      for (const t of this.tiles) {
        const target = this.cellCenter(t.row, t.col)
        t.x = target.x
        t.y = target.y
        t.scale = 1
      }
      this.tiles = this.tiles.filter((t) => !t.remove)
      this.animating = false
      return
    }
    let stillAnim = false
    for (const t of this.tiles) {
      const target = this.cellCenter(t.row, t.col)
      const k = Math.min(1, dt * 14)
      t.x += (target.x - t.x) * k
      t.y += (target.y - t.y) * k
      if (t.scale !== 1) {
        t.scale += (1 - t.scale) * Math.min(1, dt * 10)
        if (Math.abs(1 - t.scale) < 0.02) t.scale = 1
        stillAnim = true
      }
      if (Math.abs(target.x - t.x) > 0.5 || Math.abs(target.y - t.y) > 0.5) stillAnim = true
    }
    // 移除已合并的旧方块
    this.tiles = this.tiles.filter((t) => !t.remove || Math.abs(this.cellCenter(t.row, t.col).x - t.x) > 1)
    if (!stillAnim && this.animating) {
      this.animating = false
      // 收敛像素位置
      for (const t of this.tiles) this.snapTile(t)
      this.tiles = this.tiles.filter((t) => !t.remove)
    }
  }

  private render() {
    const { ctx, cssSize } = this
    ctx.clearRect(0, 0, cssSize, cssSize)
    // 棋盘底
    ctx.fillStyle = 'rgba(255,255,255,0.05)'
    this.roundRect(0, 0, cssSize, cssSize, 16)
    ctx.fill()
    // 空格
    for (let r = 0; r < SIZE; r++) {
      for (let c = 0; c < SIZE; c++) {
        const x = this.padding + c * (this.cell + this.gap)
        const y = this.padding + r * (this.cell + this.gap)
        ctx.fillStyle = 'rgba(255,255,255,0.04)'
        this.roundRect(x, y, this.cell, this.cell, 10)
        ctx.fill()
      }
    }
    // 方块
    for (const t of this.tiles) {
      const col = tileColor(t.value)
      const s = t.scale
      const size = this.cell * s
      ctx.save()
      ctx.translate(t.x, t.y)
      ctx.shadowColor = 'rgba(91,108,255,0.35)'
      ctx.shadowBlur = t.merging ? 18 : 8
      ctx.fillStyle = col.bg
      this.roundRect(-size / 2, -size / 2, size, size, 10)
      ctx.fill()
      ctx.shadowBlur = 0
      ctx.fillStyle = col.fg
      ctx.font = `700 ${Math.round(this.cell * (t.value >= 1024 ? 0.34 : t.value >= 128 ? 0.4 : 0.46))}px sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText(String(t.value), 0, 2)
      ctx.restore()
    }
  }

  private roundRect(x: number, y: number, w: number, h: number, r: number) {
    const ctx = this.ctx
    ctx.beginPath()
    ctx.moveTo(x + r, y)
    ctx.arcTo(x + w, y, x + w, y + h, r)
    ctx.arcTo(x + w, y + h, x, y + h, r)
    ctx.arcTo(x, y + h, x, y, r)
    ctx.arcTo(x, y, x + w, y, r)
    ctx.closePath()
  }

  destroy() {
    this.running = false
    cancelAnimationFrame(this.raf)
    window.removeEventListener('keydown', this.onKey)
    this.canvas.removeEventListener('pointerdown', this.onPointerDown)
    this.canvas.removeEventListener('pointerup', this.onPointerUp)
  }
}

export default NumberMergeGame
