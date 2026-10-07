import { useCallback, useEffect, useRef, useState } from 'react'
import { View, Text, Image } from '@tarojs/components'
import Taro from '@tarojs/taro'
import ErrorTip from '@/components/ErrorTip'
import NotifyEntry from '@/components/NotifyEntry'
import { canNativeShare, copyText, nativeShare, saveFile } from '@/utils/platform'
import { getPageParams } from '@/utils/query'
import { useAppStore } from '@/store'
import {
  getDiagnoseResult,
  getShareCard,
  heatmapSrc,
  pollDiagnose,
  shareCardSrc,
  type DiagnoseExtra,
  type DiagnoseProgress,
  type DiagnoseResult,
  type ShareCardData
} from '@/services/aApi'
import './index.scss'

// m2_diagnose 生意诊断 | 负责人: A | 优先级: P0
// 需求点：M2-01 打标 / M2-02 进度真实不造假 / M2-03 等待小游戏入口 / M2-04 热度图 /
//        M2-05 分享（微信/保存/复制链接，卡片含产品名与二维码）/
//        M2-06 24h 缓存 / M2-07 补充问答回显 / M2-08 AI 降级
export default function M2Diagnose() {
  const taskId = useAppStore((s) => s.taskId)
  const [progress, setProgress] = useState<DiagnoseProgress | null>(null)
  const [result, setResult] = useState<DiagnoseResult | null>(null)
  const [error, setError] = useState('')
  const [running, setRunning] = useState(false)
  const [activeTaskId, setActiveTaskId] = useState('')
  const [unreadTick, setUnreadTick] = useState(0)
  const [gameOpen, setGameOpen] = useState(false)
  const [shareOpen, setShareOpen] = useState(false)
  const [share, setShare] = useState<ShareCardData | null>(null)
  const startedRef = useRef(false)

  const run = useCallback(async (id: string) => {
    if (!id) return
    setRunning(true)
    setError('')
    try {
      const p = await pollDiagnose(id, setProgress)
      if (p.status === 'failed') {
        setError('诊断失败，请点击重试')
        return
      }
      const r = await getDiagnoseResult(id)
      setResult(r)
    } catch (e: any) {
      setError(e?.message || '服务开小差了，请重试')
    } finally {
      setRunning(false)
      setUnreadTick((n) => n + 1)
    }
  }, [])

  useEffect(() => {
    const id = getPageParams().taskId || taskId || ''
    setActiveTaskId(id)
    if (!id) {
      setError('没有找到诊断任务，请先回到首页填写你的三个条件')
      return
    }
    if (startedRef.current) return
    startedRef.current = true
    run(id)
  }, [taskId, run])

  const doneCount = progress?.doneStages?.length ?? 0
  // 首帧兜底文案：真实阶段文案由后端 progress.stages 下发（含真实案例数），
  // 这里只做「轮询还没回来」时的占位，因此**不写任何具体数字**（避免虚假宣传）。
  const stages = progress?.stages ?? [
    '正在扫描你所在城市的热门赛道',
    '正在比对你的条件与真实小生意案例',
    '正在计算回本周期与毛利率',
    '正在筛选真实成功案例',
    '正在生成你所在城市的机会热度图'
  ]
  const percent = progress?.percent ?? 0

  const saveHeatmap = () => {
    if (!result) return
    Taro.showToast({ title: '正在保存热度图…', icon: 'none' })
    saveFile(heatmapSrc(result.taskId), `生意快启_机会热度图_${result.city}.png`)
  }

  // ---------- M2-05 分享 ----------
  const openShare = async () => {
    if (!result) return
    setShareOpen(true)
    if (!share) {
      try {
        setShare(await getShareCard(result.taskId))
      } catch (e: any) {
        Taro.showToast({ title: e?.message || '分享卡片加载失败，请重试', icon: 'none' })
      }
    }
  }

  const saveShareCard = () => {
    if (!share) return
    saveFile(shareCardSrc(share.taskId), `生意快启_机会热度图_分享卡.png`)
    Taro.showToast({ title: '分享卡片已保存', icon: 'none' })
  }

  const copyLink = async () => {
    if (!share) return
    const ok = await copyText(`${share.shareText} ${share.shareUrl}`)
    Taro.showToast({ title: ok ? '链接已复制，发给朋友就行' : '复制失败，请长按图片保存', icon: 'none' })
  }

  const shareToFriend = async () => {
    if (!share) return
    if (canNativeShare()) {
      const ok = await nativeShare({ title: share.title, text: share.shareText, url: share.shareUrl })
      if (ok) return
    }
    // Web 端无法直接调起微信：如实告知并给出可行替代，不假装成功
    const res = await Taro.showModal({
      title: '网页版分享说明',
      content:
        '网页版无法直接调起微信。已为你复制链接，粘贴到微信里即可发送；也可以先保存分享卡片再发图片。',
      confirmText: '复制链接',
      cancelText: '保存图片'
    })
    if (res.confirm) await copyLink()
    else saveShareCard()
  }

  const extraSummary = renderExtra(result?.extra)

  return (
    <View className='page m2-diagnose'>
      <View className='m2-head bf-row'>
        <View>
          <Text className='m2-head__title'>生意诊断</Text>
          <Text className='m2-head__sub bf-muted'>
            {result ? `${result.city} · 已完成` : running ? '正在为你计算，请稍候' : '准备中'}
          </Text>
        </View>
        <NotifyEntry refreshKey={unreadTick} />
      </View>

      {error && <ErrorTip message={error} onRetry={() => run(activeTaskId)} />}

      {/* ---------- 阶段进度（M2-02：percent 来自后端真实阶段数） ---------- */}
      {!result && !error && (
        <>
          <View className='bf-card m2-progress'>
            <View className='bf-row'>
              <Text className='bf-card__title'>{progress?.message || '正在排队诊断'}</Text>
              <Text className='m2-progress__num'>{percent}%</Text>
            </View>
            <View className='m2-bar'>
              <View className='m2-bar__fill' style={{ width: `${percent}%` }} />
            </View>
            <View className='m2-stages'>
              {stages.map((label, i) => {
                const done = i < doneCount
                const active = !done && i === doneCount
                return (
                  <View key={label} className='m2-stage'>
                    <Text className={`m2-stage__mark ${done ? 'is-done' : ''} ${active ? 'is-active' : ''}`}>
                      {done ? '✓' : active ? '◍' : '○'}
                    </Text>
                    <Text className={`m2-stage__text ${done ? 'is-done' : ''}`}>{label}</Text>
                  </View>
                )
              })}
            </View>
          </View>

          {/* M2-03：右下角气泡入口，点开小游戏（不阻塞后台诊断任务） */}
          <View className='m2-bubble' onClick={() => setGameOpen(true)}>
            <Text className='m2-bubble__emoji'>🎯</Text>
            <Text className='m2-bubble__text'>等得无聊？</Text>
            <Text className='m2-bubble__text'>玩 10 秒指尖解压</Text>
          </View>
        </>
      )}

      {/* M2-03：小游戏浮层，退出后仍在等待页，诊断继续 */}
      {gameOpen && <MiniGame onClose={() => setGameOpen(false)} progress={percent} />}

      {/* ---------- 诊断结果 ---------- */}
      {result && result.tags && (
        <>
          {result.cached && (
            <View className='m2-tip bf-muted'>
              相同条件的诊断结果 24 小时内可直接复用（M2-06），已为你秒出。
            </View>
          )}
          {result.degraded && (
            <View className='m2-tip m2-tip--warn'>
              AI 服务暂时不可用，已切换备用模型（本地规则引擎），诊断结果不受影响。
            </View>
          )}

          <View className='bf-card'>
            <Text className='bf-card__title'>你的专属标签</Text>
            <View className='m2-tags'>
              {result.tags.labels.map((t) => (
                <Text key={t} className='bf-tag'>
                  {t}
                </Text>
              ))}
              {/* M2-07：补充问答产生的偏好标签 */}
              {(result.tags.preferenceLabels || []).map((t) => (
                <Text key={t} className='bf-tag bf-tag--accent'>
                  {t}
                </Text>
              ))}
            </View>
            {extraSummary && <Text className='bf-muted m2-meta'>补充问答：{extraSummary}</Text>}
            <Text className='bf-muted m2-meta'>
              已比对 {result.caseCount} 个小生意案例 · 用时 {(result.elapsedMs / 1000).toFixed(1)}s
            </Text>
          </View>

          <View className='bf-card'>
            <View className='bf-row'>
              <Text className='bf-card__title'>{result.city} 机会热度图</Text>
              <View className='m2-actions'>
                <View className='bf-btn bf-btn--sm bf-btn--ghost' onClick={saveHeatmap}>
                  保存图片
                </View>
                <View className='bf-btn bf-btn--sm' onClick={openShare}>
                  分享
                </View>
              </View>
            </View>
            <Image className='m2-heatmap' src={heatmapSrc(result.taskId)} mode='widthFix' />
            <Text className='bf-muted m2-meta'>
              这是你的第一份可带走成果，30 秒内生成，可直接发朋友圈。
            </Text>
          </View>

          <View className='bf-card'>
            <Text className='bf-card__title'>热度最高的 3 个方向</Text>
            <View className='m2-dirs'>
              {result.directions.map((d) => (
                <View key={d.name} className='m2-dir'>
                  <View className='bf-row'>
                    <Text className='m2-dir__name'>{d.name}</Text>
                    <Text className='m2-dir__heat'>{d.heat}</Text>
                  </View>
                  <View className='m2-bar m2-bar--slim'>
                    <View className='m2-bar__fill' style={{ width: `${d.heat}%` }} />
                  </View>
                  <Text className='bf-muted m2-dir__reason'>{d.reason}</Text>
                </View>
              ))}
            </View>
          </View>

          <View
            className='bf-btn m2-cta'
            onClick={() =>
              Taro.redirectTo({ url: `/pages/m3_match/index?taskId=${result.taskId}` })
            }
          >
            看看为你匹配的生意 →
          </View>
        </>
      )}

      {/* ---------- M2-05 分享面板 ---------- */}
      {shareOpen && (
        <View className='m2-mask' onClick={() => setShareOpen(false)}>
          <View className='m2-modal' onClick={(e) => e.stopPropagation()}>
            <Text className='m2-modal__title'>分享这份热度图</Text>
            {share ? (
              <>
                <Image className='m2-modal__img' src={shareCardSrc(share.taskId)} mode='widthFix' />
                <Text className='bf-muted m2-modal__sub'>卡片含产品名与二维码，别人扫码就能自己测一次。</Text>
                <View className='m2-modal__grid'>
                  <View className='bf-btn m2-modal__item' onClick={shareToFriend}>
                    分享给好友
                  </View>
                  <View className='bf-btn bf-btn--ghost m2-modal__item' onClick={saveShareCard}>
                    保存图片
                  </View>
                  <View className='bf-btn bf-btn--ghost m2-modal__item' onClick={copyLink}>
                    复制链接
                  </View>
                </View>
                <Text className='bf-muted m2-modal__tip'>
                  网页版受浏览器限制无法直接调起微信，可用「复制链接」或「保存图片」。
                </Text>
              </>
            ) : (
              <Text className='bf-muted m2-modal__loading'>正在生成分享卡片…</Text>
            )}
            <View className='m2-modal__close' onClick={() => setShareOpen(false)}>
              关闭
            </View>
          </View>
        </View>
      )}
    </View>
  )
}

function renderExtra(extra?: DiagnoseExtra | null): string {
  if (!extra || extra.skipped) return ''
  const map: Record<string, string> = {
    none: '零经验',
    some: '有相关经验',
    pro: '做过同样的生意',
    offline: '只做实体',
    online: '只做线上',
    both: '线上线下都行',
    cost: '最在意少投入',
    profit: '最在意多赚点',
    balance: '想平衡投入与回报'
  }
  return [extra.experience, extra.mode, extra.priority]
    .filter(Boolean)
    .map((k) => map[String(k)] || String(k))
    .join(' · ')
}

/** M2-03：等待期间的小游戏，降低等待焦虑（纯前端，不阻塞后台诊断任务）。 */
function MiniGame({ onClose, progress }: { onClose: () => void; progress: number }) {
  const [active, setActive] = useState(-1)
  const [score, setScore] = useState(0)
  const [miss, setMiss] = useState(0)
  const [left, setLeft] = useState(10)

  useEffect(() => {
    const timer = setInterval(() => setActive(Math.floor(Math.random() * 9)), 850)
    const tick = setInterval(() => setLeft((n) => (n <= 1 ? 0 : n - 1)), 1000)
    return () => {
      clearInterval(timer)
      clearInterval(tick)
    }
  }, [])

  useEffect(() => {
    if (left === 0) onClose()
  }, [left, onClose])

  const hit = (i: number) => {
    if (i === active) {
      setScore((s) => s + 1)
      setActive(-1)
    } else {
      setMiss((m) => m + 1)
    }
  }

  return (
    <View className='m2-mask' onClick={onClose}>
      <View className='m2-modal m2-game-modal' onClick={(e) => e.stopPropagation()}>
        <View className='bf-row'>
          <Text className='m2-modal__title'>10 秒指尖解压</Text>
          <Text className='m2-modal__timer'>剩余 {left}s</Text>
        </View>
        <Text className='bf-muted m2-modal__sub'>
          诊断在后台照常进行（当前 {progress}%），玩完会自动回到等待页。
        </Text>
        <View className='bf-row m2-game__scorebar'>
          <Text className='bf-muted m2-game__score'>得分 {score}</Text>
          <Text className='bf-muted m2-game__score'>失手 {miss}</Text>
        </View>
        <View className='m2-game__grid'>
          {Array.from({ length: 9 }).map((_, i) => (
            <View
              key={i}
              className={`m2-game__cell ${i === active ? 'is-active' : ''}`}
              onClick={() => hit(i)}
            >
              {i === active ? '🪙' : ''}
            </View>
          ))}
        </View>
        <View className='bf-btn bf-btn--ghost m2-modal__close' onClick={onClose}>
          退出，回到等待页
        </View>
      </View>
    </View>
  )
}
