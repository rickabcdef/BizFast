/**
 * M6-02 PDF 合并与拆分 · 纯前端本地解析（不上传）
 * 基于 pdf-lib（MIT），不含「转 Word」以规避高风险依赖。负责人: C
 */
import { PDFDocument } from 'pdf-lib'

const MAX_FILE = 50 * 1024 * 1024
const MAX_PAGES = 100

/**
 * pdf-lib 的 save() 返回 Uint8Array；新版 TS 的 BlobPart 只接受
 * ArrayBuffer 后端的视图（SharedArrayBuffer 会被判为不兼容），
 * 这里显式拷贝一份 ArrayBuffer 再交给 Blob，类型与运行期都稳妥。
 */
function pdfBlob(data: Uint8Array): Blob {
  const buffer = new ArrayBuffer(data.byteLength)
  new Uint8Array(buffer).set(data)
  return new Blob([buffer], { type: 'application/pdf' })
}

export async function mergePdfs(files: File[]): Promise<Blob> {
  if (!files.length) throw new Error('请先选择至少一个 PDF 文件')
  const merged = await PDFDocument.create()
  for (const file of files) {
    if (file.size > MAX_FILE) throw new Error(`「${file.name}」超过 50MB，无法处理`)
    const bytes = await file.arrayBuffer()
    let doc: PDFDocument
    try {
      doc = await PDFDocument.load(bytes)
    } catch {
      throw new Error(`「${file.name}」解析失败，请确认是有效的 PDF`)
    }
    if (doc.getPageCount() > MAX_PAGES) throw new Error(`「${file.name}」超过 100 页，暂不支持`)
    const pages = await merged.copyPages(doc, doc.getPageIndices())
    pages.forEach((p) => merged.addPage(p))
  }
  const out = await merged.save()
  return pdfBlob(out)
}

/**
 * 拆分：ranges 为 1-based 页码区间，如 "1-3,5,8-10"；按区间分别导出多个 PDF。
 * 返回 [{ name, blob }]
 */
export async function splitPdf(file: File, rangesText: string): Promise<{ name: string; blob: Blob }[]> {
  if (file.size > MAX_FILE) throw new Error('文件超过 50MB，无法处理')
  const ranges = parseRanges(rangesText)
  if (!ranges.length) throw new Error('请输入正确的页码范围，例如 1-3,5,8-10')
  const bytes = await file.arrayBuffer()
  let src: PDFDocument
  try {
    src = await PDFDocument.load(bytes)
  } catch {
    throw new Error('PDF 解析失败，请确认文件有效')
  }
  const total = src.getPageCount()
  if (total > MAX_PAGES) throw new Error('PDF 超过 100 页，暂不支持')

  const results: { name: string; blob: Blob }[] = []
  for (const range of ranges) {
    const indices: number[] = []
    for (let p = range.start; p <= range.end; p++) {
      if (p >= 1 && p <= total) indices.push(p - 1)
    }
    if (!indices.length) continue
    const out = await PDFDocument.create()
    const pages = await out.copyPages(src, indices)
    pages.forEach((pg) => out.addPage(pg))
    const data = await out.save()
    results.push({
      name: `生意快启_拆分_第${range.start}-${range.end}页.pdf`,
      blob: pdfBlob(data)
    })
  }
  if (!results.length) throw new Error('页码范围超出文档页数，请检查')
  return results
}

function parseRanges(text: string): { start: number; end: number }[] {
  const out: { start: number; end: number }[] = []
  for (const part of text.split(/[,，]/)) {
    const t = part.trim()
    if (!t) continue
    const m = t.match(/^(\d+)\s*-\s*(\d+)$/)
    if (m) {
      const a = Number(m[1])
      const b = Number(m[2])
      if (a > 0 && b >= a) out.push({ start: a, end: b })
    } else if (/^\d+$/.test(t)) {
      const a = Number(t)
      if (a > 0) out.push({ start: a, end: a })
    } else {
      return []
    }
  }
  return out
}
