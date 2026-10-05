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
  getMyPackages,
  getPackage,
  getPackageProgress,
  packageItemUrl,
  packageZipUrl,
  regeneratePackage,
  type PackageProgress
} from '@/services/bApi'
import type { DeliverableFile, PackageResult } from '@/types'
import './index.scss'

// m4_delivery 启动包生成与交付 | 负责人: B | 优先级: P0
// 需求点：
//   M4-01 异步生成（消息队列 + 前端轮询真实进度，≤3 分钟）
//   M4-02 进度展示「已完成 x/10」+ 正在生成的文件名（进度真实不造假）
//   M4-03 10 件交付物打包 ZIP 一键下载（包内中文命名）
//   M4-04 单件下载 + 在线预览 PDF / 图片（预览不产生额外费用）
//   M4-05 云端永久保存，换端登录后可重新下载
//   M4-06 重新生成（会员免费，单次购买可用 1 次，规则界面明示）
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

/** M4-04：PDF 与图片支持在线预览；其余格式直接下载。 */
function canPreview(t: string): boolean {
  return t === 'pdf' || t === 'png' || t === 'svg'
}

/** 文件中文命名：生意快启_交付物名称_生成日期（PRD 3.7）。 */
function downloadName(item: DeliverableFile, suffix?: string): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  const date = `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}`
  return `生意快启_${item.name}${suffix || ''}_${date}.${FILE_EXT[item.fileType] || 'file'}`
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
  const pollRef = useRef<any>(null)

  const stopPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const pollProgress = useCallback(
    (id: string) => {
      stopPoll()
      const tick = async () => {
        try {
          const p = await getPackageProgress(id)
          setProgress(p)
          if (p.status === 'delivered') {
            stopPoll()
            const detail = await getPackage(id)
            setPkg(detail)
            return
          }
          if (p.status === 'failed') {
            stopPoll()
            setError(
              p.failReason || '生成失败了，系统已自动重试 2 次仍未成功，我们将全额退款并第一时间通知你'
            )
            return
          }
        } catch (e: any) {
          // 单次轮询失败不中断：提示可重试，不伪造进度
          setError(e?.message || '进度查询失败，请重试')
          stopPoll()
        }
      }
      void tick()
      pollRef.current = setInterval(tick, 2000)
    },
    [getPackage, stopPoll]
  )

  /** M4-01：创建生成任务（幂等）→ 轮询真实进度直到 已交付 / 失败。 */
  const startGenerate = useCallback(
    async (id: string) => {
      setError('')
      setLoading(true)
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
  /** Mock 模式下条目自带 data URL（离线可打开）；真实模式按后端路径取。 */
  const itemUrl = (item: DeliverableFile) =>
    item.url && item.url.startsWith('data:') ? item.url : packageItemUrl(orderId, item.code)

  const downloadItem = (item: DeliverableFile) => {
    saveFile(itemUrl(item), downloadName(item))
  }

  const downloadZip = () => {
    if (!pkg) return
    const d = new Date()
    const pad = (n: number) => String(n).padStart(2, '0')
    const date = `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}`
    saveFile(pkg.zipUrl, `生意快启_完整启动包10件_${date}.zip`)
  }

  const openPreview = (item: DeliverableFile) => {
    const url = itemUrl(item)
    if (item.fileType === 'png' || item.fileType === 'svg') {
      setPreview({ url, name: item.name })
      return
    }
    // PDF 在线预览（浏览器原生渲染；预览不产生额外费用 M4-04）
    if (typeof window !== 'undefined') {
      window.open(url, '_blank')
    }
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
                <Text className='m4-pg__tag'>{FILE_LABEL[it.fileType] || ''}</Text>
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

        {/* M4-03/04：10 张文件卡片网格 */}
        <View className='m4-grid'>
          {pkg.items.map((it) => (
            <View key={it.code} className='bf-card m4-file'>
              <View className='m4-file__head'>
                <Text className='m4-file__code'>{it.code}</Text>
                <Text className={`m4-file__fmt m4-file__fmt--${it.fileType}`}>
                  {FILE_LABEL[it.fileType] || it.fileType}
                </Text>
              </View>
              <Text className='m4-file__name'>{it.name}</Text>
              <View className='m4-file__actions'>
                {canPreview(it.fileType) && (
                  <View className='m4-file__act' onClick={() => openPreview(it)}>
                    预览
                  </View>
                )}
                <View className='m4-file__act m4-file__act--main' onClick={() => downloadItem(it)}>
                  下载
                </View>
              </View>
            </View>
          ))}
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

        {/* 终值体验（PRD 5.6.5 / 6.3）：温度文案 + 生成开业喜报 */}
        <View className='m4-end'>
          <Text className='m4-end__text'>
            祝你开业大吉，生意兴隆。
            {'\n'}
            遇到问题随时回来找我们。
          </Text>
          <View
            className='bf-btn bf-btn--ghost m4-end__btn'
            onClick={() => Taro.navigateTo({ url: '/pages/m8_share/index' })}
          >
            生成我的开业喜报
          </View>
        </View>

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

/** 十件交付物清单（D01–D10，用于进度页逐项打勾展示）。 */
const ALL_ITEMS: DeliverableFile[] = [
  { code: 'D01', name: '最佳商机可行性评分卡', fileType: 'pdf', url: '' },
  { code: 'D02', name: '回本测算表', fileType: 'excel', url: '' },
  { code: 'D03', name: '客户画像与获客清单', fileType: 'pdf', url: '' },
  { code: 'D04', name: '供应商线索与询价话术', fileType: 'pdf', url: '' },
  { code: 'D05', name: '定价建议与开业活动方案', fileType: 'pdf', url: '' },
  { code: 'D06', name: '开店流程清单', fileType: 'pdf', url: '' },
  { code: 'D07', name: '获客文案模板10条', fileType: 'word', url: '' },
  { code: 'D08', name: '店名与宣传物料', fileType: 'png', url: '' },
  { code: 'D09', name: '30天行动日历', fileType: 'pdf', url: '' },
  { code: 'D10', name: '风险清单与止损线', fileType: 'pdf', url: '' }
]
