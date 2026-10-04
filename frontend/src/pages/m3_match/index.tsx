import { useCallback, useEffect, useRef, useState } from 'react'
import { View, Text, Image } from '@tarojs/components'
import Taro from '@tarojs/taro'
import ErrorTip from '@/components/ErrorTip'
import Loading from '@/components/Loading'
import NotifyEntry from '@/components/NotifyEntry'
import { getPageParams } from '@/utils/query'
import { saveDataUrl } from '@/utils/platform'
import { renderCompareImage, type CompareRow } from '@/utils/compareImage'
import { useAppStore } from '@/store'
import {
  createDiagnose,
  getMatchDetail,
  getMatchList,
  toggleFavorite,
  type MatchList,
  type OpportunityCard,
  type OpportunityDetail
} from '@/services/aApi'
import './index.scss'

// m3_match 商机匹配 | 负责人: A | 优先级: P0
// 需求点：M3-01 三个强相关商机 / M3-02 五要素数字卡 / M3-03 详情 /
//        M3-04 真实案例≥2 / M3-05 风险≥3+止损 / M3-06 收藏+横向对比+导出图片 /
//        M3-07 第 4 个锁定商机付费拦截 / M3-08 重新诊断（不消耗免费额度）
const COMPARE_MAX = 3

const CAPITAL_LABEL: Record<number, string> = {
  1: '1万以下',
  2: '1–5万',
  3: '5–20万',
  4: '20万以上'
}
const TIME_LABEL: Record<number, string> = {
  2: '兼职',
  8: '全职'
}

export default function M3Match() {
  const storeTaskId = useAppStore((s) => s.taskId)
  const lastInput = useAppStore((s) => s.input)
  const saveTaskId = useAppStore((s) => s.setTaskId)
  const [taskId, setTaskId] = useState('')
  const [list, setList] = useState<MatchList | null>(null)
  const [detail, setDetail] = useState<OpportunityDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [paywall, setPaywall] = useState<OpportunityCard | null>(null)
  const [error, setError] = useState('')
  // M3-06 横向对比
  const [compareMode, setCompareMode] = useState(false)
  const [picked, setPicked] = useState<string[]>([])
  const [compareOpen, setCompareOpen] = useState(false)
  const [compareImg, setCompareImg] = useState('')
  // M3-08 重新诊断
  const [redoOpen, setRedoOpen] = useState(false)
  const [redoBusy, setRedoBusy] = useState(false)

  const load = useCallback(async (id: string) => {
    if (!id) {
      setError('没有找到诊断结果，请先完成一次生意诊断')
      return
    }
    setError('')
    try {
      const data = await getMatchList(id)
      setList(data)
    } catch (e: any) {
      setError(e?.message || '服务开小差了，请重试')
    }
  }, [])

  useEffect(() => {
    const id = getPageParams().taskId || storeTaskId || ''
    setTaskId(id)
    load(id)
  }, [storeTaskId, load])

  const openDetail = async (card: OpportunityCard) => {
    setDetailLoading(true)
    try {
      const d = await getMatchDetail(card.id, taskId)
      setDetail(d)
    } catch (e: any) {
      // M3-07：锁定商机未解锁 → 40301，拉起付费弹窗（不暴露英文错误）
      if (e?.code === 40301) setPaywall(card)
      else setError(e?.message || '服务开小差了，请重试')
    } finally {
      setDetailLoading(false)
    }
  }

  const favorite = async (id: string) => {
    try {
      const r = await toggleFavorite(id)
      Taro.showToast({ title: r.favorited ? '已收藏' : '已取消收藏', icon: 'none' })
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '操作失败，请重试', icon: 'none' })
    }
  }

  const goPay = (plan: 'single' | 'year', matchId?: string) => {
    setPaywall(null)
    Taro.navigateTo({
      url: `/pages/m5_pay/index?plan=${plan}${matchId ? `&matchId=${matchId}` : ''}`
    })
  }

  // ---------- M3-06 横向对比 ----------
  const togglePick = (id: string) => {
    setPicked((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id)
      if (prev.length >= COMPARE_MAX) {
        Taro.showToast({ title: `最多同时对比 ${COMPARE_MAX} 个方案`, icon: 'none' })
        return prev
      }
      return [...prev, id]
    })
  }

  const exitCompare = () => {
    setCompareMode(false)
    setPicked([])
    setCompareImg('')
  }

  const pickedCards = (list?.free || []).filter((c) => picked.includes(c.id))

  const inputSummary = lastInput
    ? `${CAPITAL_LABEL[lastInput.capital] || ''} · ${TIME_LABEL[lastInput.dailyHours] || ''}`
    : ''

  const compareRows = (cards: OpportunityCard[]): CompareRow[] => [
    {
      label: '启动资金',
      values: cards.map((c) => `约 ${(c.metrics.capitalAmountYuan / 10000).toFixed(1)} 万元`)
    },
    { label: '资金区间', values: cards.map((c) => c.fiveElements.capital) },
    { label: '回本周期', values: cards.map((c) => `${c.metrics.paybackMonths} 个月`) },
    { label: '毛利率', values: cards.map((c) => `${c.metrics.marginPercent}%`) },
    {
      label: '上手难度',
      values: cards.map(
        (c) => `${'★'.repeat(Math.max(1, c.metrics.difficultyStars))} ${c.fiveElements.difficulty.replace(/^[⭐★\s]+/, '')}`
      )
    },
    { label: '匹配度', values: cards.map((c) => `${c.recommendScore} 分`) },
    { label: '第一个客户', values: cards.map((c) => c.fiveElements.firstCustomer) },
    { label: '最大的坑', values: cards.map((c) => c.risks[0] || '') }
  ]

  const exportCompareImage = () => {
    const cards = pickedCards
    if (cards.length < 2) return
    const url = renderCompareImage({
      title: '生意快启 · 商机横向对比',
      subtitle: [list?.city, inputSummary].filter(Boolean).join(' · '),
      headers: cards.map((c) => c.title),
      rows: compareRows(cards),
      footer: '由「生意快启 BizFast」生成 · 数据来自案例库与公开行业数据，仅供决策参考'
    })
    if (!url) {
      Taro.showToast({ title: '当前环境不支持导出图片，可长按截图保存', icon: 'none' })
      return
    }
    setCompareImg(url)
    const ok = saveDataUrl(url, `生意快启_商机对比_${list?.city || '方案'}.png`)
    Taro.showToast({ title: ok ? '对比图已导出' : '导出失败，可长按图片保存', icon: 'none' })
  }

  // ---------- M3-08 重新诊断 ----------
  /** 条件不变重跑：命中 M2-06 的 24h 缓存会直接复用同一结果，因此不消耗免费额度。 */
  const redoWithSameInput = async () => {
    if (!lastInput) {
      Taro.reLaunch({ url: '/pages/m1_home/index?redo=1' })
      return
    }
    setRedoBusy(true)
    try {
      const r = await createDiagnose({
        capital: lastInput.capital,
        dailyHours: lastInput.dailyHours,
        city: lastInput.city,
        extra: lastInput.extra || { skipped: true }
      })
      setTaskId(r.taskId)
      saveTaskId(r.taskId)
      setRedoOpen(false)
      Taro.showToast({
        title: r.cached ? '条件没变，已复用 24 小时内的结果' : '已重新诊断',
        icon: 'none'
      })
      if (r.taskId !== taskId) {
        Taro.redirectTo({ url: `/pages/m2_diagnose/index?taskId=${r.taskId}` })
      } else {
        await load(r.taskId)
      }
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '重新诊断失败，请重试', icon: 'none' })
    } finally {
      setRedoBusy(false)
    }
  }

  const redoWithNewInput = () => {
    setRedoOpen(false)
    Taro.reLaunch({ url: '/pages/m1_home/index?redo=1' })
  }

  if (detail) {
    return (
      <OpportunityDetailView
        detail={detail}
        onBack={() => setDetail(null)}
        onFavorite={favorite}
        onPay={() => goPay('single', detail.id)}
      />
    )
  }

  return (
    <View className='page m3-match'>
      <View className='bf-row m3-head'>
        <View className='m3-head__left'>
          <Text className='m3-head__title'>为你匹配的生意</Text>
          <Text className='bf-muted m3-head__sub'>
            {list ? `${list.city} · 已比对 ${list.caseCount} 个案例` : '正在为你计算'}
          </Text>
        </View>
        <View className='m3-head__right'>
          {list && (
            <View
              className='bf-btn bf-btn--sm bf-btn--ghost'
              onClick={() => (compareMode ? exitCompare() : setCompareMode(true))}
            >
              {compareMode ? '退出对比' : '对比'}
            </View>
          )}
          <View className='bf-btn bf-btn--sm bf-btn--ghost' onClick={() => setRedoOpen(true)}>
            重新诊断
          </View>
          <NotifyEntry />
        </View>
      </View>

      {error && <ErrorTip message={error} onRetry={() => load(taskId)} />}
      {!list && !error && <Loading text='正在为你匹配最合适的生意…' />}
      {detailLoading && <Loading text='正在打开详情…' />}

      {list && (
        <>
          <Text className='bf-muted m3-note'>
            以下 3 个方案与你的资金 / 时间 / 城市强相关，看不懂的名词都已经换成大白话。
          </Text>

          {compareMode && (
            <View className='m3-cmpbar'>
              <Text className='m3-cmpbar__text'>
                勾选 2–{COMPARE_MAX} 个方案，一键生成对比表并可导出图片。已选 {picked.length} 个。
              </Text>
            </View>
          )}

          {list.free.map((card) => (
            <OpportunityCardView
              key={card.id}
              card={card}
              rank={card.rank}
              compareMode={compareMode}
              picked={picked.includes(card.id)}
              onToggleCompare={() => togglePick(card.id)}
              onOpen={() => openDetail(card)}
              onFavorite={() => favorite(card.id)}
            />
          ))}

          {/* M3-07：第 4 个「最佳匹配」锁定卡 */}
          <OpportunityCardView
            card={list.locked}
            rank={4}
            locked
            compareMode={compareMode}
            picked={false}
            onToggleCompare={() =>
              Taro.showToast({ title: '该方案解锁后才能加入对比', icon: 'none' })
            }
            onOpen={() => setPaywall(list.locked)}
            onFavorite={() => favorite(list.locked.id)}
          />
        </>
      )}

      {/* M3-06：底部操作条 */}
      {compareMode && !compareOpen && (
        <View className='m3-comparebar'>
          <Text className='m3-comparebar__count'>
            已选 <Text className='m3-comparebar__num'>{picked.length}</Text> / {COMPARE_MAX}
          </Text>
          <View className='m3-comparebar__actions'>
            <View className='bf-btn bf-btn--sm bf-btn--ghost' onClick={exitCompare}>
              退出
            </View>
            <View
              className={`bf-btn bf-btn--sm ${picked.length >= 2 ? '' : 'bf-btn--disabled'}`}
              onClick={() => picked.length >= 2 && setCompareOpen(true)}
            >
              开始对比
            </View>
          </View>
        </View>
      )}

      {/* M3-06：对比表弹窗 + 导出图片 */}
      {compareOpen && (
        <View className='m3-mask' onClick={() => setCompareOpen(false)}>
          <View className='m3-modal m3-cmpmodal' onClick={(e) => e.stopPropagation()}>
            <Text className='m3-modal__title'>商机横向对比</Text>
            <Text className='bf-muted m3-modal__sub'>
              {[list?.city, inputSummary].filter(Boolean).join(' · ')} · 共 {pickedCards.length} 个方案
            </Text>

            <View className='m3-cmptable'>
              <View className='m3-cmptable__row m3-cmptable__row--head'>
                <Text className='m3-cmptable__label'>对比项</Text>
                {pickedCards.map((c) => (
                  <Text key={c.id} className='m3-cmptable__head'>
                    {c.title}
                  </Text>
                ))}
              </View>
              {compareRows(pickedCards).map((r) => (
                <View key={r.label} className='m3-cmptable__row'>
                  <Text className='m3-cmptable__label'>{r.label}</Text>
                  {r.values.map((v, i) => (
                    <Text key={`${r.label}-${pickedCards[i]?.id}`} className='m3-cmptable__value'>
                      {v || '—'}
                    </Text>
                  ))}
                </View>
              ))}
            </View>

            <View className='m3-modal__list'>
              <Text className='m3-modal__li'>· 回本周期越短、毛利率越高，通常风险越低</Text>
              <Text className='m3-modal__li'>· 匹配度是基于你的资金 / 时间 / 城市算出来的贴合程度</Text>
            </View>

            {compareImg && <Image className='m3-cmpimg' src={compareImg} mode='widthFix' />}

            <View className='bf-btn m3-modal__btn' onClick={exportCompareImage}>
              {compareImg ? '重新导出对比图' : '导出对比图（可发朋友圈/存手机）'}
            </View>
            <View className='bf-btn bf-btn--ghost m3-modal__btn' onClick={() => setCompareOpen(false)}>
              关闭
            </View>
          </View>
        </View>
      )}

      {/* M3-08：重新诊断入口 */}
      {redoOpen && (
        <View className='m3-mask' onClick={() => setRedoOpen(false)}>
          <View className='m3-modal' onClick={(e) => e.stopPropagation()}>
            <Text className='m3-modal__title'>重新诊断</Text>
            <Text className='bf-muted m3-modal__sub'>
              重新诊断不会消耗你的免费额度，3 个免费方案依旧可以看。
            </Text>
            <View className='m3-modal__list'>
              <Text className='m3-modal__li'>
                · 当前条件：{[list?.city, inputSummary].filter(Boolean).join(' · ') || '（已丢失）'}
              </Text>
              <Text className='m3-modal__li'>· 「条件不变」会优先复用 24 小时内的结果，秒出</Text>
              <Text className='m3-modal__li'>· 「改条件」会带回原条件，你只改想改的那一项</Text>
            </View>
            <View
              className={`bf-btn m3-modal__btn ${redoBusy ? 'bf-btn--disabled' : ''}`}
              onClick={() => !redoBusy && redoWithSameInput()}
            >
              {redoBusy ? '正在重跑…' : '条件不变，重新跑一次'}
            </View>
            <View className='bf-btn bf-btn--ghost m3-modal__btn' onClick={redoWithNewInput}>
              改条件重新诊断
            </View>
            <View className='bf-btn bf-btn--ghost m3-modal__btn' onClick={() => setRedoOpen(false)}>
              取消
            </View>
          </View>
        </View>
      )}

      {paywall && (
        <PaywallModal
          card={paywall}
          onClose={() => setPaywall(null)}
          onSingle={() => goPay('single', paywall.id)}
          onYear={() => goPay('year', paywall.id)}
        />
      )}
    </View>
  )
}

// ---------------------------------------------------------------- 卡片（M3-02）
function OpportunityCardView({
  card,
  rank,
  locked = false,
  compareMode = false,
  picked = false,
  onToggleCompare,
  onOpen,
  onFavorite
}: {
  card: OpportunityCard
  rank: number
  locked?: boolean
  compareMode?: boolean
  picked?: boolean
  onToggleCompare?: () => void
  onOpen: () => void
  onFavorite: () => void
}) {
  // 对比模式下点卡片即勾选，避免误触付费弹窗（锁定卡单独处理）
  const handleClick = () => (compareMode && onToggleCompare ? onToggleCompare() : onOpen())

  return (
    <View
      className={`bf-card m3-card ${locked ? 'is-locked' : ''} ${picked ? 'is-picked' : ''}`}
      onClick={handleClick}
    >
      <View className='bf-row'>
        <View className='m3-card__titlebox'>
          {compareMode ? (
            <Text className={`m3-pick ${picked ? 'is-on' : ''}`}>{picked ? '✓' : '+'}</Text>
          ) : (
            <Text className='m3-card__rank'>#{rank}</Text>
          )}
          <Text className='m3-card__icon'>{card.icon}</Text>
          <Text className='m3-card__title'>{card.title}</Text>
        </View>
        {!compareMode && (
          <View
            className='m3-card__fav'
            onClick={(e) => {
              e.stopPropagation()
              onFavorite()
            }}
          >
            ☆
          </View>
        )}
        {compareMode && locked && <Text className='bf-muted m3-card__locktip'>需解锁</Text>}
      </View>

      <Text className='bf-muted m3-card__summary'>{card.summary}</Text>

      <FiveElementsGrid card={card} blurred={locked} />

      <View className='m3-card__foot bf-row'>
        <View className='m3-card__tags'>
          {card.tags.slice(0, 3).map((t) => (
            <Text key={t} className='bf-tag'>
              {t}
            </Text>
          ))}
        </View>
        <Text className='m3-card__score'>匹配度 {card.recommendScore}</Text>
      </View>

      {locked && (
        <View className='m3-lock'>
          <Text className='m3-lock__text'>
            🔒 为你匹配的最佳方案，解锁后可查看完整启动方案
          </Text>
          <Text className='m3-lock__cta'>解锁 →</Text>
        </View>
      )}
    </View>
  )
}

/** 五要素数字卡（M3-02）：数字滚动 + 逐格浮现，全部说人话。 */
function FiveElementsGrid({ card, blurred }: { card: OpportunityCard; blurred: boolean }) {
  const m = card.metrics
  // 万元保留 1 位小数 → 以「千元」为整数单位做滚动，避免浮点抖动
  const capWanX10 = useCountUp(Math.round(m.capitalAmountYuan / 1000), 0)
  const payback = useCountUp(m.paybackMonths, 120)
  const margin = useCountUp(m.marginPercent, 240)
  const stars = useCountUp(m.difficultyStars, 360)
  const difficultyText = card.fiveElements.difficulty.replace(/^[⭐\s]+/, '')

  const cells = [
    { label: '启动资金', value: `${(capWanX10 / 10).toFixed(1)} 万元左右` },
    { label: '回本周期', value: `${payback} 个月` },
    { label: '毛利率', value: `${margin}%` },
    { label: '第一个客户', value: card.fiveElements.firstCustomer },
    { label: '上手难度', value: `${'⭐'.repeat(Math.max(1, stars))} ${difficultyText}` }
  ]

  return (
    <View className={`m3-five ${blurred ? 'is-blurred' : ''}`}>
      {cells.map((c, i) => (
        <View key={c.label} className='m3-five__cell' style={{ animationDelay: `${i * 90}ms` }}>
          <Text className='m3-five__label'>{c.label}</Text>
          <Text className='m3-five__value'>{c.value}</Text>
        </View>
      ))}
    </View>
  )
}

/** 数字滚动（跨端安全：用定时器而非 requestAnimationFrame）。 */
function useCountUp(target: number, delayMs = 0, steps = 16, stepMs = 38) {
  const [value, setValue] = useState(0)
  const timerRef = useRef<any>(null)

  useEffect(() => {
    let count = 0
    const start = () => {
      timerRef.current = setInterval(() => {
        count += 1
        setValue(count >= steps ? target : Math.round((target * count) / steps))
        if (count >= steps && timerRef.current) {
          clearInterval(timerRef.current)
          timerRef.current = null
        }
      }, stepMs)
    }
    const delay = setTimeout(start, delayMs)
    return () => {
      clearTimeout(delay)
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
  }, [target, delayMs, steps, stepMs])

  return value
}

// ---------------------------------------------------------------- 详情（M3-03/04/05）
function OpportunityDetailView({
  detail,
  onBack,
  onFavorite,
  onPay
}: {
  detail: OpportunityDetail
  onBack: () => void
  onFavorite: (id: string) => void
  onPay: () => void
}) {
  return (
    <View className='page m3-match m3-detail'>
      <View className='bf-row m3-detail__bar'>
        <View className='bf-btn bf-btn--sm bf-btn--ghost' onClick={onBack}>
          ← 返回
        </View>
        <View className='bf-btn bf-btn--sm bf-btn--ghost' onClick={() => onFavorite(detail.id)}>
          ☆ 收藏
        </View>
      </View>

      <View className='bf-card'>
        <Text className='m3-detail__title'>
          {detail.icon} {detail.title}
        </Text>
        <Text className='bf-muted m3-detail__intro'>{detail.intro}</Text>
        <View className='m3-card__tags'>
          {detail.tags.map((t) => (
            <Text key={t} className='bf-tag'>
              {t}
            </Text>
          ))}
        </View>
      </View>

      <View className='bf-card'>
        <Text className='bf-card__title'>五个关键数字</Text>
        <FiveElementsGrid card={detail} blurred={false} />
      </View>

      <Section title='投入构成'>
        <Table rows={detail.costBreakdown.map((c) => ({ a: c.item, b: c.amount, note: c.note }))} />
      </Section>

      <Section title='收益测算'>
        <Table rows={detail.revenueEstimate.map((c) => ({ a: c.item, b: c.value, note: c.note }))} />
      </Section>

      <Section title='谁来买你的东西'>
        <Text className='m3-detail__p'>{detail.targetCustomers}</Text>
        <Text className='m3-detail__p'>获客渠道：{detail.channels}</Text>
        <Text className='m3-detail__p'>需要的能力：{detail.skillRequired}</Text>
      </Section>

      {/* M3-04：真实案例 ≥2 */}
      <Section title={`真实案例（${detail.cases.length} 个）`}>
        {detail.cases.map((c) => (
          <View key={c.title} className='m3-case'>
            <Text className='m3-case__title'>{c.title}</Text>
            <Text className='m3-case__highlight'>{c.highlight}</Text>
            <Text className='bf-muted m3-case__src'>
              来源：{c.source} · {c.time}
            </Text>
          </View>
        ))}
      </Section>

      {/* M3-05：风险 ≥3 + 止损线 */}
      <Section title={`必须知道的风险（${detail.risks.length} 条）`}>
        {detail.risks.map((r, i) => (
          <View key={r} className='m3-risk'>
            <Text className='m3-risk__no'>{i + 1}</Text>
            <Text className='m3-risk__text'>{r}</Text>
          </View>
        ))}
        <View className='m3-stoploss'>
          <Text className='m3-stoploss__label'>止损线</Text>
          <Text className='m3-stoploss__text'>{detail.stopLoss}</Text>
        </View>
      </Section>

      <Section title='上手步骤'>
        {detail.steps.map((s, i) => (
          <View key={s} className='m3-step'>
            <Text className='m3-step__no'>{i + 1}</Text>
            <Text className='m3-step__text'>{s}</Text>
          </View>
        ))}
      </Section>

      <View className='bf-btn m3-detail__cta' onClick={onPay}>
        生成这个方案的完整启动包
      </View>
    </View>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View className='bf-card'>
      <Text className='bf-card__title'>{title}</Text>
      {children}
    </View>
  )
}

function Table({ rows }: { rows: { a: string; b: string; note: string }[] }) {
  return (
    <View className='m3-table'>
      {rows.map((r) => (
        <View key={r.a} className='m3-table__row'>
          <View className='bf-row'>
            <Text className='m3-table__a'>{r.a}</Text>
            <Text className='m3-table__b'>{r.b}</Text>
          </View>
          {r.note ? <Text className='bf-muted m3-table__note'>{r.note}</Text> : null}
        </View>
      ))}
    </View>
  )
}

// ---------------------------------------------------------------- 付费弹窗（M3-07）
function PaywallModal({
  card,
  onClose,
  onSingle,
  onYear
}: {
  card: OpportunityCard
  onClose: () => void
  onSingle: () => void
  onYear: () => void
}) {
  return (
    <View className='m3-mask' onClick={onClose}>
      <View className='m3-modal' onClick={(e) => e.stopPropagation()}>
        <Text className='m3-modal__title'>解锁「{card.title}」完整方案</Text>
        <Text className='bf-muted m3-modal__sub'>
          这份方案与你的三个条件匹配度最高（{card.recommendScore} 分），包含 10 件可直接使用的文件。
        </Text>
        <View className='m3-modal__list'>
          <Text className='m3-modal__li'>· 投入构成与收益测算，一分钱花在哪都写清楚</Text>
          <Text className='m3-modal__li'>· 真实案例 + 风险清单 + 止损线</Text>
          <Text className='m3-modal__li'>· 30 天行动日历与获客文案模板</Text>
        </View>
        <View className='bf-btn m3-modal__btn' onClick={onSingle}>
          9.9 元，只买这一个方案
        </View>
        <View className='bf-btn bf-btn--ghost m3-modal__btn' onClick={onYear}>
          199 元/年，全年不限次（最划算）
        </View>
        <Text className='bf-muted m3-modal__tip'>7 天无理由退款，24 小时内到账。</Text>
      </View>
    </View>
  )
}
