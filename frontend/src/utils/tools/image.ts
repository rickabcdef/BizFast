/**
 * M6-01 图片压缩与格式转换 · 纯前端本地处理（不上传，保护隐私）
 * 基于 Canvas，支持 JPG/PNG/WebP 互转与按质量压缩。负责人: C
 */
export type ImageFormat = 'keep' | 'jpeg' | 'png' | 'webp'

export interface CompressResult {
  blob: Blob
  dataUrl: string
  width: number
  height: number
  size: number
  mime: string
}

const MAX_SIDE = 4096 // 超大雨图等比缩小，避免画布超限

function resolveMime(file: File, format: ImageFormat): string {
  if (format === 'keep') {
    if (file.type === 'image/jpeg' || file.type === 'image/png' || file.type === 'image/webp') return file.type
    return 'image/png'
  }
  return `image/${format}`
}

export async function compressImage(
  file: File,
  opts: { quality: number; format: ImageFormat }
): Promise<CompressResult> {
  if (file.size > 20 * 1024 * 1024) {
    throw new Error('单张图片不能超过 20MB，请换一张')
  }
  const mime = resolveMime(file, opts.format)
  const dataUrl = await readAsDataURL(file)
  const img = await loadImage(dataUrl)
  let { width, height } = img
  if (width > MAX_SIDE || height > MAX_SIDE) {
    const ratio = Math.min(MAX_SIDE / width, MAX_SIDE / height)
    width = Math.round(width * ratio)
    height = Math.round(height * ratio)
  }
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('当前浏览器不支持图片处理')
  // PNG 透明底转 JPG 需铺白底
  if (mime === 'image/jpeg') {
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, width, height)
  }
  ctx.drawImage(img, 0, 0, width, height)
  const quality = mime === 'image/png' ? undefined : Math.min(1, Math.max(0.1, opts.quality / 100))
  const blob = await canvasToBlob(canvas, mime, quality)
  const outDataUrl = canvas.toDataURL(mime, quality)
  return { blob, dataUrl: outDataUrl, width, height, size: blob.size, mime }
}

function readAsDataURL(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const fr = new FileReader()
    fr.onload = () => resolve(fr.result as string)
    fr.onerror = () => reject(new Error('图片读取失败，请重试'))
    fr.readAsDataURL(file)
  })
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('图片解析失败，请换一张'))
    img.src = src
  })
}

function canvasToBlob(canvas: HTMLCanvasElement, mime: string, quality?: number): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (b) => (b ? resolve(b) : reject(new Error('图片生成失败，请重试'))),
      mime,
      quality
    )
  })
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}
