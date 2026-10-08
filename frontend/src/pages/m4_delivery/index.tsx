import { useCallback, useEffect, useRef, useState } from 'react'
import { View, Text, Image } from '@tarojs/components'
import Taro from '@tarojs/taro'
import ErrorTip from '@/components/ErrorTip'
import Loading from '@/components/Loading'
import { getPageParams } from '@/utils/query'
import { saveFile } from '@/utils/platform'
import { useAppStore } from '@/store'
import {
  createPackage,
  createReport,
  getMyPackages,
  getPackage,
  getPackageProgress,
  getReportTemplates,
  getToolAccess,
  packageItemUrl,
  packageZipUrl,
  regeneratePackage,
  trackEvent,
  type PackageProgress,
  type ShareReport,
  type ToolAccess
} from '@/services/bApi'
import type { DeliverableFile, DeliverableFormat, PackageResult } from '@/types'
import './index.scss'

// m4_delivery 启动包生成与交付 | 负责人: B | 优先级: P0
// 需求点：
//   M4-01 异步生成（消息队列 + 前端轮询真实进度，≤3 分钟）
//   M4-02 进度展示「已完成 x/10」+ 正在生成的文件名（进度真实不造假）
//   M4-03 10 件交付物打包 ZIP 一键下载（包内中文命名）
//   M4-04 单件下载 + 在线预览 PDF / 图片（预览不产生额外费用）
//   M4-05 云端永久保存，换端登录后可重新下载
//   M4-06 重新生成（会员免费，单次购买可用 1 次，规则界面明示）
//   M4-07 生成完成通知（网页端：浏览器桌面通知；离开页面仍可收到）
//   M4-08 失败自动重试 2 次；仍失败全额退款并提示（失败必有补偿）
// 页面承载 P07 生成进度页 + P08 启动包交付页两个状态。

const FILE_EXT: Record<string, string> = {
  pdf: 'pdf',
  excel: 'xlsx',
  word: 'docx',
  png: 'png',
  svg: 'svg',
  txt: 'txt',
  zip: 'zip'
}
const FILE_LABEL: Record<string, string> = {
  pdf: 'PDF',
  excel: 'Excel',
  word: 'Word',
  png: 'PNG',
  svg: 'SVG',
  txt: 'TXT',
  zip: 'ZIP'
}

/** 一件交付物的全部格式（formats 缺省时按单一主格式处理）。 */
function itemFormats(item: DeliverableFile): DeliverableFormat[] {
  return item.formats && item.formats.length ? item.formats : [{ fileType: item.fileType, url: item.url }]
}

/** 格式标签列表（如 D03 → ['PDF', 'Word']）。 */
function fmtLabels(item: DeliverableFile): string[] {
  return itemFormats(item).map((f) => FILE_LABEL[f.fileType] || f.fileType)
}

/** M4-04：PDF 与图片支持在线预览；其余格式直接下载。 */
function canPreview(t: string): boolean {
  return t === 'pdf' || t === 'png' || t === 'svg'
}

/**
 * V5.0 需求 3.3「交付峰值体验」：每个文件旁边直接挂配套小工具入口，
 * 用户拿到文件的那一刻就知道下一步怎么发朋友圈 / 怎么打印 / 怎么改文案 / 怎么做收款码。
 * 工具随开业礼包赠送使用权（30 天），点击直接跳工具箱对应功能。
 */
const TOOL_QUICK: Record<string, { tool: string; label: string }[]> = {
  D06: [{ tool: 'pdf', label: '合并所有 PDF 一键打印' }],
  D07: [{ tool: 'copy', label: '一键改写成适合我的版本' }],
  D08: [
    { tool: 'image', label: '一键压缩图片发朋友圈' },
    { tool: 'qrcode', label: '自定义我的收款码' }
  ]
}

/** V5.0 需求 3.3：⭐ 标记核心高价值文件（一眼看到最值钱的那件）。 */
const CORE_CODES = new Set(['D01'])

/** 文件中文命名：生意快启_交付物名称_生成日期（PRD 3.7）；多格式同名不同扩展名区分。 */
function downloadName(item: DeliverableFile, fmt: DeliverableFormat): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  const date = `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}`
  return `生意快启_${item.name}_${date}.${FILE_EXT[fmt.fileType] || 'file'}`
}

/** M4-07：生成完成桌面通知（网页端；页面不可见时提醒，用户离开后仍能收到）。 */
function ensureNotifyPermission(): void {
  if (typeof window === 'undefined' || typeof Notification === 'undefined') return
  if (Notification.permission === 'default') {
    try {
      void Notification.requestPermission()
    } catch {
      /* 忽略：用户拒绝或环境不支持时静默降级 */
    }
  }
}

function notifyDone(orderId: string): void {
  if (typeof window === 'undefined' || typeof Notification === 'undefined') return
  if (Notification.permission !== 'granted' || !document.hidden) return
  try {
    const n = new Notification('生意快启 · 启动包已生成', {
      body: `订单 ${orderId} 的 10 件交付物已就绪，点击查看与下载`
    })
    n.onclick = () => {
      window.focus()
      window.location.hash = `#/pages/m4_delivery/index?orderId=${orderId}`
    }
  } catch {
    /* 忽略：部分环境禁止脚本创建通知 */
  }
}

export default function M4Delivery() {
  const setStoreOrderId = useAppStore((s) => s.setOrderId)
  const [orderId, setOrderId] = useState('')
  const [matchId, setMatchId] = useState<string | null>(null)
  const [pkg, setPkg] = useState<PackageResult | null>(null)
  const [progress, setProgress] = useState<PackageProgress | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [history, setHistory] = useState<PackageResult[]>([])
  // M4-06 重新生成
  const [redoOpen, setRedoOpen] = useState(false)
  const [redoBusy, setRedoBusy] = useState(false)
  // M4-04 预览
  const [preview, setPreview] = useState<{ url: string; name: string } | null>(null)
  // V5.0 M3-06 / M5-02 开业喜报
  const [reportOpen, setReportOpen] = useState(false)
  const [report, setReport] = useState<ShareReport | null>(null)
  const [reportBusy, setReportBusy] = useState(false)
  const [reportTpl, setReportTpl] = useState(1)
  const [templates, setTemplates] = useState<{ id: number; name: string }[]>([])
  // V5.0 M8 工具箱权益（开业礼包赠 2 个工具 30 天 / 会员全部）
  const [toolAccess, setToolAccess] = useState<ToolAccess | null>(null)
  const pollRef = useRef<{ stop: () => void } | null>(null)
  // 同步闸门：createPackage 是异步的（await 期间 pollRef 还没赋值），
  // 开发模式 StrictMode 双挂载 / 重复点击时两次请求都会穿过 pollRef 的幂等判断，
  // 这里用同步 ref 立刻占位，保证同一订单只会向后台发一次生成请求。
  const creatingRef = useRef<string | null>(null)

  const stopPoll = useCallback(() => {
    if (pollRef.current) {
      pollRef.current.stop()
      pollRef.current = null
    }
  }, [])

  const pollProgress = useCallback(
    (id: string) => {
      // 幂等：同步阶段已有轮询则不重复启动（双 effect / 重复挂载只保留一个轮询，
      // 避免旧轮询在失败分支后继续 tick 覆盖状态）
      if (pollRef.current) return
      stopPoll()
      // 局部 interval 句柄：tick 内用局部 stop 精确清理自己注册的轮询，
      // 不依赖 pollRef（页面被重复挂载/重复启动时不会泄漏第二个轮询）。
      let timer: any = null
      let stopped = false
      const stop = () => {
        stopped = true
        if (timer) {
          clearInterval(timer)
          timer = null
        }
        // 若 pollRef 指向当前轮询则一并清空，避免 startGenerate 的幂等防护误判
        if (pollRef.current && pollRef.current.stop === stop) pollRef.current = null
      }
      const tick = async () => {
        try {
          const p = await getPackageProgress(id)
          if (stopped) return
          if (p.status === 'failed') {
            // M4-08：失败态（自动重试 2 次由后端完成），页面给出补偿说明与重试入口
            stop()
            setProgress(p)
            setError(p.failReason || '生成失败了，系统已自动重试 2 次仍未成功，我们将全额退款并第一时间通知你')
            return
          }
          if (p.status === 'delivered') {
            stop()
            setProgress(p)
            notifyDone(id) // M4-07：页面不可见时发桌面通知
            const detail = await getPackage(id)
            setPkg(detail)
            return
          }
          setProgress(p)
        } catch (e: any) {
          if (stopped) return
          // 单次轮询失败不中断：提示可重试，不伪造进度
          stop()
          setError(e?.message || '进度查询失败，请重试')
        }
      }
      void tick()
      timer = setInterval(tick, 2000)
      pollRef.current = { stop }
    },
    [getPackage, stopPoll]
  )

  /** M4-01：创建生成任务（幂等）→ 轮询真实进度直到 已交付 / 失败。
   *  幂等防护：已有轮询在跑时不重复启动（页面重复挂载 / 双 effect 只走一轮）。 */
  const startGenerate = useCallback(
    async (id: string) => {
      if (pollRef.current) return
      if (creatingRef.current === id) return // 已发起过（含 StrictMode 双挂载）
      creatingRef.current = id
      setError('')
      setLoading(true)
      ensureNotifyPermission() // M4-07：进入生成流程时申请通知权限（用户拒绝则静默降级）
      try {
        // 已存在则直接返回 orderId；不存在则由后端入队（重复请求后端返回 40901 同样可轮询）
        await createPackage({ orderId: id, matchId })
        setLoading(false)
        pollProgress(id)
      } catch (e: any) {
        if (e?.code === 40901) {
          // 订单正在生成中（幂等冲突）：直接开始轮询
          setLoading(false)
          pollProgress(id)
          return
        }
        setLoading(false)
        creatingRef.current = null // 真正的失败才允许用户重试
        setError(e?.message || '启动生成失败，请重试')
      }
    },
    [matchId, pollProgress]
  )

  const loadPackage = useCallback(
    async (id: string) => {
      setOrderId(id)
      setStoreOrderId(id)
      try {
        const detail = await getPackage(id)
        setPkg(detail)
        return
      } catch (e: any) {
        if (e?.code === 40401) {
          // 尚未生成：创建任务并进入进度页（M4-01）
          await startGenerate(id)
          return
        }
        setError(e?.message || '加载启动包失败，请重试')
      }
    },
    [setStoreOrderId, startGenerate]
  )

  const loadHistory = useCallback(async () => {
    try {
      setHistory(await getMyPackages())
    } catch (e: any) {
      setError(e?.message || '加载历史启动包失败，请重试')
    }
  }, [])

  useEffect(() => {
    const params = getPageParams()
    const id = params.orderId || ''
    setMatchId(params.matchId || null)
    if (id) {
      void loadPackage(id)
    } else {
      // M4-05：没有指定订单时展示「我的启动包」云端列表
      void loadHistory()
    }
    return stopPoll
  }, [loadPackage, loadHistory, stopPoll])

  // ---------------- M4-06 重新生成 ----------------
  const doRegenerate = async () => {
    if (redoBusy) return
    setRedoBusy(true)
    try {
      const r = await regeneratePackage(orderId)
      setRedoOpen(false)
      setPkg(null)
      setProgress(null)
      Taro.showToast({ title: '已开始重新生成', icon: 'none' })
      pollProgress(orderId)
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '重新生成失败，请重试', icon: 'none' })
    } finally {
      setRedoBusy(false)
    }
  }

  // ---------------- 下载与预览 ----------------
  /** Mock 模式下条目自带 data URL（离线可打开）；真实模式按后端路径取（可带 format 选择格式）。 */
  const itemUrl = (item: DeliverableFile, fmt?: DeliverableFormat, download = false) => {
    if (fmt && fmt.url)
      return fmt.url.startsWith('data:')
        ? fmt.url
        : packageItemUrl(orderId, item.code, fmt.fileType, download)
    return item.url && item.url.startsWith('data:')
      ? item.url
      : packageItemUrl(orderId, item.code, undefined, download)
  }

  const downloadItem = (item: DeliverableFile, fmt?: DeliverableFormat) => {
    const f = fmt || itemFormats(item)[0]
    // M2-05（V5.0）：下载会打上「已获取」标记，之后的退款走人工审核
    saveFile(itemUrl(item, f, true), downloadName(item, f))
  }

  const downloadZip = () => {
    if (!pkg) return
    const d = new Date()
    const pad = (n: number) => String(n).padStart(2, '0')
    const date = `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}`
    saveFile(pkg.zipUrl, `生意快启_完整启动包10件_${date}.zip`)
  }

  const openPreview = (item: DeliverableFile, fmt?: DeliverableFormat) => {
    const f = fmt || itemFormats(item)[0]
    const url = itemUrl(item, f)
    if (f.fileType === 'png' || f.fileType === 'svg') {
      setPreview({ url, name: item.name })
      return
    }
    // PDF 在线预览（浏览器原生渲染；预览不产生额外费用 M4-04）
    if (typeof window !== 'undefined') {
      window.open(url, '_blank')
      return
    }
    // 小程序端：下载临时文件后用 openDocument 预览（支持 PDF/Office）
    const DOC_TYPE: Record<string, 'pdf' | 'docx' | 'xlsx'> = { pdf: 'pdf', word: 'docx', excel: 'xlsx' }
    const docType = DOC_TYPE[f.fileType]
    if (!docType) {
      Taro.showToast({ title: '该格式暂不支持预览', icon: 'none' })
      return
    }
    Taro.downloadFile({
      url,
      success: (r) => Taro.openDocument({ filePath: r.tempFilePath, fileType: docType }),
      fail: () => Taro.showToast({ title: '预览文件加载失败', icon: 'none' })
    })
  }

  // ---------------- V5.0 M3-06 / M5-02 开业喜报 + M8 工具箱权益 ----------------
  useEffect(() => {
    getReportTemplates()
      .then((d) => setTemplates(d.templates || []))
      .catch(() => {})
    getToolAccess()
      .then(setToolAccess)
      .catch(() => {})
  }, [])

  const genReport = async (tpl: number) => {
    if (reportBusy) return
    setReportBusy(true)
    setReportTpl(tpl)
    try {
      const r = await createReport(orderId || null, tpl)
      setReport(r)
      // M5-04 分享埋点
      trackEvent('share_report', '交付页').catch(() => {})
      Taro.showToast({ title: '喜报已生成', icon: 'none' })
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '喜报生成失败，请重试', icon: 'none' })
    } finally {
      setReportBusy(false)
    }
  }

  /** M3-06：喜报 10 秒内产出，可直接保存到手机/电脑。 */
  const saveReport = () => {
    if (!report?.imageUrl) return
    saveFile(report.imageUrl, `生意快启_开业喜报_${report.templateName || '喜报'}.png`)
    trackEvent('share_report_save', '交付页').catch(() => {})
  }

  const openHistory = (p: PackageResult) => {
    setOrderId(p.orderId)
    setStoreOrderId(p.orderId)
    setPkg(p)
    setProgress(null)
    setHistory([])
  }

  // ================= 生成进度页（P07，M4-01/02） =================
  if (progress && progress.status === 'generating') {
    return (
      <View className='page m4-delivery m4-progress'>
        <View className='m4-pg__title'>正在生成你的生意启动包</View>
        <Text className='bf-muted m4-pg__sub'>AI 正在为你准备 10 件可直接开干的文件</Text>

        {error && <ErrorTip message={error} onRetry={() => pollProgress(orderId)} />}

        {/* M4-02：真实进度条（蓝紫渐变 + 流光） */}
        <View className='m4-pg__bar'>
          <View className='m4-pg__fill' style={{ width: `${progress.percent}%` }} />
        </View>
        <View className='bf-row m4-pg__meta'>
          <Text className='m4-pg__count'>已完成 {progress.done}/{progress.total}</Text>
          <Text className='m4-pg__pct'>{progress.percent}%</Text>
        </View>
        <Text className='m4-pg__stage'>{progress.stage}</Text>

        {/* M4-02：正在生成的文件名 + 已完成清单打勾 */}
        <View className='bf-card m4-pg__list'>
          {progress.currentItem && (
            <View className='m4-pg__now'>
              <Text className='m4-pg__nowdot'>●</Text>
              <Text className='m4-pg__nowtext'>{progress.currentItem}</Text>
            </View>
          )}
          {ALL_ITEMS.map((it, i) => {
            const done = i < progress.done
            const doing = i === progress.done - 1 && progress.done < progress.total
            return (
              <View key={it.code} className={`m4-pg__item ${done ? 'is-done' : ''}`}>
                <Text className='m4-pg__check'>{done ? '✓' : doing ? '◐' : '○'}</Text>
                <Text className='m4-pg__name'>{it.code} {it.name}</Text>
                <Text className='m4-pg__tag'>{fmtLabels(it).join(' · ')}</Text>
              </View>
            )
          })}
        </View>

        {/* M2-03 / PRD 5.6.2：等待小游戏入口气泡（小游戏不阻塞后台任务，退出后回到本页） */}
        <View className='m4-pg__game' onClick={() => Taro.navigateTo({ url: '/pages/m7_games/index' })}>
          <Text className='m4-pg__gameemoji'>🫧</Text>
          <Text className='m4-pg__gametext'>等得无聊？玩 10 秒指尖解压</Text>
        </View>

        {/* M4-08：失败必有补偿（自动重试 2 次 / 全额退款） */}
        <Text className='bf-muted m4-pg__foot'>
          生成失败会自动重试 2 次；仍失败将全额退款并第一时间通知你。你可以先离开本页，稍后再回来看。
        </Text>
      </View>
    )
  }

  // ================= 生成失败态（M4-08：失败必有补偿） =================
  if (progress && progress.status === 'failed') {
    return (
      <View className='page m4-delivery m4-progress'>
        <View className='m4-pg__title'>启动包生成失败了</View>
        <Text className='bf-muted m4-pg__sub'>
          系统已自动重试 2 次仍未成功。别担心，钱不会丢：我们会按规则全额退款，并在 24 小时内到账。
        </Text>
        {error && <ErrorTip message={error} onRetry={() => startGenerate(orderId)} />}
        <View className='bf-card m4-pg__fail'>
          <Text className='m4-pg__failitem'>· 已自动重试 2 次（M4-08）</Text>
          <Text className='m4-pg__failitem'>· 仍失败则全额退款，到账 ≤ 24 小时</Text>
          <Text className='m4-pg__failitem'>· 你也可以稍后回到「我的启动包」重新发起</Text>
        </View>
        <View className='bf-btn m4-pg__retry' onClick={() => startGenerate(orderId)}>
          重新尝试生成
        </View>
        <Text className='bf-muted m4-pg__foot'>退款无需申请：失败确认后系统自动原路退回。</Text>
      </View>
    )
  }

  // ================= 启动包交付页（P08） =================
  if (pkg && pkg.status === 'delivered') {
    return (
      <View className='page m4-delivery'>
        <View className='m4-done'>
          <Text className='m4-done__title'>🎉 你的生意启动包已生成</Text>
          <Text className='bf-muted m4-done__sub'>
            订单 {pkg.orderId} · 10 件文件已全部就绪，永久保存在云端（M4-05）
          </Text>
          <View className='bf-btn m4-done__zip' onClick={downloadZip}>
            一键打包下载（ZIP）
          </View>
          <Text className='bf-muted m4-done__tip'>包内文件均为中文命名，可直接保存、打印、发给合作伙伴</Text>
        </View>

        {/* M4-03/04：10 张文件卡片网格（多格式交付物每格式一行：预览/下载） */}
        <View className='m4-grid'>
          {pkg.items.map((it) => (
            <View key={it.code} className='bf-card m4-file'>
              <View className='m4-file__head'>
                <Text className='m4-file__code'>
                  {CORE_CODES.has(it.code) ? '⭐ ' : ''}
                  {it.code}
                </Text>
                <Text className='m4-file__fmt'>{fmtLabels(it).join(' · ')}</Text>
              </View>
              <Text className='m4-file__name'>{it.name}</Text>
              <View className='m4-file__rows'>
                {itemFormats(it).map((f, fi) => (
                  <View key={fi} className='m4-file__row'>
                    <Text className='m4-file__rowfmt'>{FILE_LABEL[f.fileType] || f.fileType}</Text>
                    {canPreview(f.fileType) && (
                      <View className='m4-file__act' onClick={() => openPreview(it, f)}>
                        预览
                      </View>
                    )}
                    <View className='m4-file__act m4-file__act--main' onClick={() => downloadItem(it, f)}>
                      下载
                    </View>
                  </View>
                ))}
              </View>

              {/* V5.0 需求 3.3：文件旁边直接挂配套小工具入口（随礼包赠使用权） */}
              {TOOL_QUICK[it.code] && (
                <View className='m4-file__tools'>
                  {TOOL_QUICK[it.code].map((t) => (
                    <View
                      key={t.tool}
                      className='m4-file__tool'
                      onClick={() => Taro.navigateTo({ url: `/pages/m6_tools/index?tool=${t.tool}` })}
                    >
                      {t.label} →
                    </View>
                  ))}
                </View>
              )}
            </View>
          ))}
        </View>

        {/* V5.0 M8 / 需求 3.3：工具已嵌入上方文件卡片，这里只说明赠送权益与工具箱入口 */}
        <View className='bf-card m4-tools'>
          <Text className='bf-card__title'>🛠️ 配套工具已随礼包开通</Text>
          <Text className='bf-muted m4-tools__sub'>
            {toolAccess?.desc || '工具已嵌入交付流程，直接点开文件旁的按钮就能用'}
          </Text>
          <View
            className='bf-btn bf-btn--sm bf-btn--ghost m4-tools__all'
            onClick={() => Taro.navigateTo({ url: '/pages/m6_tools/index' })}
          >
            打开工具箱看全部工具
          </View>
        </View>

        {/* 重新生成（M4-06）与云端保存说明 */}
        <View className='bf-card m4-extra'>
          <View className='bf-row'>
            <Text className='bf-card__title'>重新生成</Text>
            <View className='bf-btn bf-btn--sm bf-btn--ghost' onClick={() => setRedoOpen(true)}>
              换条件重做
            </View>
          </View>
          <Text className='bf-muted m4-extra__text'>
            会员可无限次重新生成；单次购买用户可使用 1 次。重新生成会基于最新诊断条件产出新方案。
          </Text>
        </View>

        {/* 终值体验（V5.0 M3-06 / M5-02）：温度文案 + 生成开业喜报（3 种模板可选） */}
        <View className='m4-end'>
          <Text className='m4-end__text'>
            祝你开业大吉，生意兴隆。
            {'\n'}
            遇到问题随时回来找我们。
          </Text>
          <View
            className='bf-btn bf-btn--ghost m4-end__btn'
            onClick={() => {
              setReport(null)
              setReportOpen(true)
            }}
          >
            📱 生成我的开业喜报
          </View>
          <Text className='bf-muted m4-end__tip'>
            生成一张可发朋友圈的喜报图，带品牌标识、不带硬广，10 秒内出图。
          </Text>
        </View>

        {/* M3-06 / M5-02 开业喜报弹窗：3 种以上模板可选 */}
        {reportOpen && (
          <View className='m4-mask' onClick={() => setReportOpen(false)}>
            <View className='m4-modal m4-report' onClick={(e) => e.stopPropagation()}>
              <Text className='m4-modal__title'>生成我的开业喜报</Text>

              {!report ? (
                <>
                  <Text className='bf-muted m4-report__tip'>
                    选一个你喜欢的样式，生成后可直接保存到手机发朋友圈。
                  </Text>
                  <View className='m4-report__tpls'>
                    {(templates.length
                      ? templates
                      : [
                          { id: 1, name: '科技蓝紫' },
                          { id: 2, name: '开业红金' },
                          { id: 3, name: '简约白蓝' }
                        ]
                    ).map((t) => (
                      <View
                        key={t.id}
                        className={`m4-report__tpl ${reportTpl === t.id ? 'is-active' : ''}`}
                        onClick={() => setReportTpl(t.id)}
                      >
                        <Text>{t.name}</Text>
                      </View>
                    ))}
                  </View>
                  <View
                    className={`bf-btn m4-modal__btn ${reportBusy ? 'bf-btn--disabled' : ''}`}
                    onClick={() => !reportBusy && genReport(reportTpl)}
                  >
                    {reportBusy ? '正在生成…' : '立即生成喜报'}
                  </View>
                </>
              ) : (
                <>
                  {report.imageUrl ? (
                    <Image className='m4-report__img' src={report.imageUrl} mode='widthFix' />
                  ) : null}
                  <Text className='m4-report__title'>{report.title}</Text>
                  <Text className='m4-report__sub'>{report.subtitle}</Text>
                  <View className='m4-report__lines'>
                    {(report.lines || []).map((l, i) => (
                      <Text key={i} className='m4-report__line'>
                        · {l}
                      </Text>
                    ))}
                  </View>
                  <Text className='bf-muted m4-report__brand'>
                    {report.brand} · {report.slogan}
                  </Text>
                  <View className='bf-btn m4-modal__btn' onClick={saveReport}>
                    保存喜报图片
                  </View>
                </>
              )}

              <View
                className='bf-btn bf-btn--ghost m4-modal__btn'
                onClick={() => setReportOpen(false)}
              >
                {report ? '完成' : '关闭'}
              </View>
            </View>
          </View>
        )}

        {/* M4-06 重新生成确认弹窗 */}
        {redoOpen && (
          <View className='m4-mask' onClick={() => setRedoOpen(false)}>
            <View className='m4-modal' onClick={(e) => e.stopPropagation()}>
              <Text className='m4-modal__title'>重新生成启动包</Text>
              <View className='m4-modal__list'>
                <Text className='m4-modal__li'>· 会员：免费无限次重新生成</Text>
                <Text className='m4-modal__li'>· 单次购买：可使用 1 次重新生成机会</Text>
                <Text className='m4-modal__li'>· 重新生成会覆盖当前版本，云端只保留最新一版</Text>
              </View>
              <View
                className={`bf-btn m4-modal__btn ${redoBusy ? 'bf-btn--disabled' : ''}`}
                onClick={() => !redoBusy && doRegenerate()}
              >
                {redoBusy ? '正在重新生成…' : '确认重新生成'}
              </View>
              <View className='bf-btn bf-btn--ghost m4-modal__btn' onClick={() => setRedoOpen(false)}>
                先不重做
              </View>
            </View>
          </View>
        )}

        {/* M4-04：图片预览弹窗 */}
        {preview && (
          <View className='m4-mask' onClick={() => setPreview(null)}>
            <View className='m4-modal m4-preview' onClick={(e) => e.stopPropagation()}>
              <Text className='m4-modal__title'>{preview.name}</Text>
              <Image className='m4-preview__img' src={preview.url} mode='widthFix' showMenuByLongpress />
              <View className='bf-btn bf-btn--ghost m4-modal__btn' onClick={() => setPreview(null)}>
                关闭
              </View>
            </View>
          </View>
        )}
      </View>
    )
  }

  // ================= 无订单：我的启动包（云端永久保存列表 M4-05） =================
  return (
    <View className='page m4-delivery'>
      <View className='bf-row m4-head'>
        <View>
          <Text className='m4-head__title'>我的启动包</Text>
          <Text className='bf-muted m4-head__sub'>云端永久保存，换设备登录后随时可下载</Text>
        </View>
        <View
          className='bf-btn bf-btn--sm bf-btn--ghost'
          onClick={() => Taro.reLaunch({ url: '/pages/m1_home/index' })}
        >
          去诊断
        </View>
      </View>

      {loading && <Loading text='正在加载…' />}
      {error && (
        <ErrorTip message={error} onRetry={() => (orderId ? loadPackage(orderId) : loadHistory())} />
      )}

      {!loading && !error && history.length === 0 && (
        <View className='m4-empty'>
          <Text className='m4-empty__title'>还没有生成过的启动包</Text>
          <Text className='bf-muted m4-empty__text'>
            完成一次诊断并付费后，10 件交付物会永久保存在这里。
          </Text>
          <View
            className='bf-btn m4-empty__btn'
            onClick={() => Taro.reLaunch({ url: '/pages/m1_home/index' })}
          >
            开始我的第一次诊断
          </View>
        </View>
      )}

      {history.map((p) => (
        <View key={p.orderId} className='bf-card m4-hist' onClick={() => openHistory(p)}>
          <View className='bf-row'>
            <Text className='bf-card__title'>订单 {p.orderId}</Text>
            <Text className='bf-tag bf-tag--good'>
              {p.status === 'delivered' ? '已交付' : p.status === 'failed' ? '生成失败' : '生成中'}
            </Text>
          </View>
          <Text className='bf-muted m4-hist__text'>{p.items.length} 件文件 · 点击查看与下载</Text>
          <View className='bf-btn bf-btn--sm m4-hist__btn'>查看交付物</View>
        </View>
      ))}
    </View>
  )
}

/** 十件交付物清单（D01–D10，用于进度页逐项打勾展示；格式与 PRD 4.4.1 一致，名称对齐 V5.0 需求 3.2）。 */
const ALL_ITEMS: DeliverableFile[] = [
  { code: 'D01', name: '专属商机可行性评分卡', fileType: 'pdf', url: '', formats: [{ fileType: 'pdf', url: '' }] },
  { code: 'D02', name: '回本测算 Excel 表', fileType: 'excel', url: '', formats: [{ fileType: 'excel', url: '' }] },
  { code: 'D03', name: '精准客户画像 + 首月获客清单', fileType: 'pdf', url: '', formats: [{ fileType: 'pdf', url: '' }, { fileType: 'word', url: '' }] },
  { code: 'D04', name: '本地一手供应商线索 + 询价话术', fileType: 'pdf', url: '', formats: [{ fileType: 'pdf', url: '' }] },
  { code: 'D05', name: '定价建议 + 3 套开业活动方案', fileType: 'pdf', url: '', formats: [{ fileType: 'pdf', url: '' }] },
  { code: 'D06', name: '全流程开店清单', fileType: 'pdf', url: '', formats: [{ fileType: 'pdf', url: '' }, { fileType: 'word', url: '' }] },
  { code: 'D07', name: '首月获客文案 10 条', fileType: 'word', url: '', formats: [{ fileType: 'word', url: '' }, { fileType: 'txt', url: '' }] },
  { code: 'D08', name: '开业宣传物料包（海报+二维码+门头效果图）', fileType: 'png', url: '', formats: [{ fileType: 'png', url: '' }, { fileType: 'svg', url: '' }] },
  { code: 'D09', name: '30 天逐日行动日历', fileType: 'pdf', url: '', formats: [{ fileType: 'pdf', url: '' }, { fileType: 'excel', url: '' }] },
  { code: 'D10', name: '风险清单与止损线', fileType: 'pdf', url: '', formats: [{ fileType: 'pdf', url: '' }] }
]
