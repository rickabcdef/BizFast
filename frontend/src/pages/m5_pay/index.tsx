import { useCallback, useEffect, useState } from 'react'
import { View, Text, Input } from '@tarojs/components'
import Taro from '@tarojs/taro'
import ErrorTip from '@/components/ErrorTip'
import Loading from '@/components/Loading'
import NotifyEntry from '@/components/NotifyEntry'
import { getPlatform, payChannelFor } from '@/utils/platform'
import { getPageParams } from '@/utils/query'
import { useAppStore } from '@/store'
import type { Plan } from '@/types'
import {
  cancelSubscription,
  createOrder,
  getCoupons,
  getOrder,
  getPlans,
  getSubscription,
  payCallback,
  refundOrder,
  setAutoRenew as setAutoRenewApi,
  validateCoupon,
  type CouponItem,
  type CouponValidateOut,
  type OrderCreateOut,
  type OrderView,
  type PlanOption,
  type SubscriptionView
} from '@/services/aApi'
import './index.scss'

// m5_pay 付费与订单 | 负责人: A | 优先级: P0
// 需求点：M5-03 三档价格同屏 / M5-04 按端适配支付渠道 / M5-05 订单状态机（每态带时间戳）
//        M5-06 回调 + 主动查单双保险 / M5-07 7 天无理由退款，24h 到账
//        M5-08 自动续费（续费前 3 天提醒 / 取消不超过 3 步）/ M5-09 优惠券与邀请码（不可叠加、规则明示）
//        M5-10 风控命中转人工审核（如实告知，不偷偷拦截）
const CHANNEL_LABELS: Record<string, string> = {
  alipay: '支付宝',
  wechat: '微信支付',
  apple: 'Apple 支付',
  huawei: '华为支付'
}

const PLATFORM_LABELS: Record<string, string> = {
  web: '网页版',
  weapp: '微信小程序',
  android: '安卓 App',
  ios: 'iOS App',
  harmony: '鸿蒙 App',
  win: 'Windows 桌面端',
  mac: 'macOS 桌面端'
}

/** M5-08：只有会员制（月/年）才谈自动续费，单次购买没有续费概念。 */
function isSubscriptionPlan(plan: Plan): boolean {
  return plan === 'month' || plan === 'year'
}

export default function M5Pay() {
  const setOrderId = useAppStore((s) => s.setOrderId)
  const [platform] = useState(() => getPlatform())
  const [plans, setPlans] = useState<PlanOption[]>([])
  const [plan, setPlan] = useState<Plan>('single')
  const [matchId, setMatchId] = useState<string | null>(null)
  const [paying, setPaying] = useState<OrderCreateOut | null>(null)
  const [order, setOrder] = useState<OrderView | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  // M5-09 优惠券 / 邀请码
  const [coupon, setCoupon] = useState('')
  const [couponInfo, setCouponInfo] = useState<CouponValidateOut | null>(null)
  const [couponErr, setCouponErr] = useState('')
  const [couponList, setCouponList] = useState<CouponItem[]>([])
  const [couponRules, setCouponRules] = useState('')
  const [couponHint, setCouponHint] = useState('')
  const [couponOpen, setCouponOpen] = useState(false)
  // M5-08 自动续费
  const [autoRenew, setAutoRenew] = useState(false)
  const [sub, setSub] = useState<SubscriptionView | null>(null)
  const [subBusy, setSubBusy] = useState(false)

  useEffect(() => {
    const params = getPageParams()
    if (params.plan === 'month' || params.plan === 'year' || params.plan === 'single') {
      setPlan(params.plan)
    }
    setMatchId(params.matchId || null)
    if (params.orderId) {
      setOrderId(params.orderId)
      loadOrder(params.orderId)
    }
    getPlans()
      .then((d) => setPlans(d.plans))
      .catch((e: any) => setError(e?.message || '服务开小差了，请重试'))
    // 券清单与订阅状态属于「锦上添花」，失败不影响下单主流程，因此各自静默兜底
    getCoupons()
      .then((d) => {
        setCouponList(d.items)
        setCouponRules(d.rules)
        setCouponHint(d.hint)
      })
      .catch(() => undefined)
    loadSubscription()
  }, [setOrderId])

  const loadSubscription = useCallback(async () => {
    try {
      setSub(await getSubscription())
    } catch {
      /* 未登录/网络异常时不打断购买流程 */
    }
  }, [])

  /** M5-09：只做预校验，能减多少当场告诉用户；核销发生在真正下单时。 */
  const applyCoupon = useCallback(
    async (code: string, targetPlan: Plan) => {
      const c = code.trim()
      setCouponErr('')
      if (!c) {
        setCouponInfo(null)
        return
      }
      try {
        const r = await validateCoupon(c, targetPlan)
        setCouponInfo(r)
        setCoupon(r.code)
        setCouponOpen(false)
      } catch (e: any) {
        setCouponInfo(null)
        setCouponErr(e?.message || '这个券码用不了，请检查后重试')
      }
    },
    []
  )

  // 切换套餐后原来的券可能不再适用（plan_scope / 门槛会变），自动复检一次
  useEffect(() => {
    if (couponInfo) applyCoupon(couponInfo.code, plan)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plan])

  const clearCoupon = () => {
    setCoupon('')
    setCouponInfo(null)
    setCouponErr('')
  }

  const loadOrder = useCallback(async (id: string): Promise<any | undefined> => {
    try {
      const o = await getOrder(id)
      setOrder(o)
      setOrderId(o.id)
      return o
    } catch (e: any) {
      setError(e?.message || '服务开小差了，请重试')
      return undefined
    }
  }, [setOrderId])

  /** 创建订单 → 拉起支付（M5-04 按端适配渠道）。 */
  const startPay = async () => {
    setLoading(true)
    setError('')
    try {
      const created = await createOrder({
        plan,
        platform,
        matchId,
        couponCode: couponInfo?.code || null,
        autoRenew: isSubscriptionPlan(plan) ? autoRenew : null
      })
      setPaying(created)
      setOrderId(created.orderId)
    } catch (e: any) {
      setError(e?.message || '支付未成功，请重新支付')
    } finally {
      setLoading(false)
    }
  }

  /** 模拟渠道回调（本地联调；真实环境由渠道异步回调，前端只负责查单）。 */
  const confirmPaid = async () => {
    if (!paying) return
    setLoading(true)
    try {
      await payCallback(paying.channel, paying.orderId)
      const fresh = await loadOrder(paying.orderId)
      setPaying(null)
      Taro.showToast({ title: '支付成功', icon: 'success' })
      // M4-01 衔接（负责人 B）：支付成功后进入生成进度页，由 m4 页轮询真实进度
      if (fresh && (fresh.status === 'generating' || fresh.status === 'delivered' || fresh.status === 'paid')) {
        setTimeout(() => {
          Taro.redirectTo({
            url: `/pages/m4_delivery/index?orderId=${fresh.id}&matchId=${matchId || ''}`
          })
        }, 1500)
      }
    } catch (e: any) {
      setError(e?.message || '支付未成功，请重新支付')
    } finally {
      setLoading(false)
    }
  }

  /** M5-06 主动查单兜底：不依赖回调也能拿到最终状态。 */
  const refreshOrder = async () => {
    if (!order) return
    setLoading(true)
    try {
      await loadOrder(order.id)
      Taro.showToast({ title: '已刷新订单状态', icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  const doRefund = async () => {
    if (!order) return
    const res = await Taro.showModal({
      title: '申请退款',
      content: `将原路退还 ¥${order.amountLabel}，24 小时内到账。确认申请吗？`
    })
    if (!res.confirm) return
    setLoading(true)
    try {
      const r = await refundOrder(order.id, '用户主动申请')
      Taro.showToast({ title: r.message, icon: 'none' })
      await loadOrder(order.id)
    } catch (e: any) {
      setError(e?.message || '退款失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  const channel = CHANNEL_LABELS[paying?.channel || 'alipay'] || '在线支付'
  // M5-04：本端可用渠道（与 utils/platform 中的端适配规则保持一致）
  const localChannel = CHANNEL_LABELS[payChannelFor(platform)] || '在线支付'
  const current = plans.find((p) => p.plan === plan)
  const orderChannelLabel = order ? CHANNEL_LABELS[order.channel] || order.channel : ''

  // M5-09：金额预览。有券就显示券后价，没有就显示原价——绝不先显示低价再在支付时加回去。
  const listLabel = current?.priceLabel || '9.9'
  const finalLabel = couponInfo ? couponInfo.finalLabel : listLabel

  /** M5-08：开关自动续费（开与关都只需一步，不设障碍）。 */
  const toggleAutoRenew = async () => {
    if (!sub?.isMember || subBusy) return
    setSubBusy(true)
    try {
      const next = await setAutoRenewApi(!sub.autoRenew)
      setSub(next)
      Taro.showToast({ title: next.autoRenew ? '已开启自动续费' : '已关闭自动续费', icon: 'none' })
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '操作失败，请重试', icon: 'none' })
    } finally {
      setSubBusy(false)
    }
  }

  /** M5-08：一键取消。路径 = 本页 → 点这个按钮 → 确认，共 2 步，不做挽留、不藏入口。 */
  const doCancelSubscription = async () => {
    if (!sub || subBusy) return
    const res = await Taro.showModal({
      title: '取消自动续费',
      content: sub.daysLeft
        ? `取消后将不再自动扣费，你仍可使用到 ${formatDay(sub.expireAt)}（还剩 ${sub.daysLeft} 天）。`
        : '取消后将不再自动扣费，当前会员到期后自动失效。',
      confirmText: '确认取消',
      cancelText: '再想想'
    })
    if (!res.confirm) return
    setSubBusy(true)
    try {
      const next = await cancelSubscription()
      setSub(next)
      Taro.showToast({ title: '已取消自动续费', icon: 'none' })
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '取消失败，请重试', icon: 'none' })
    } finally {
      setSubBusy(false)
    }
  }

  return (
    <View className='page m5-pay'>
      <View className='bf-row m5-head'>
        <View>
          <Text className='m5-head__title'>{order ? '我的订单' : '解锁完整启动包'}</Text>
          <Text className='bf-muted m5-head__sub'>
            {order ? order.planName : `${PLATFORM_LABELS[platform] || platform} · 支付渠道自动适配`}
          </Text>
        </View>
        <NotifyEntry />
      </View>

      {error && <ErrorTip message={error} onRetry={() => (order ? refreshOrder() : startPay())} />}

      {/* ---------- 订单详情（M5-05 / M5-06 / M5-07） ---------- */}
      {order ? (
        <>
          <View className='bf-card'>
            <View className='bf-row'>
              <Text className='bf-card__title'>{order.statusLabel}</Text>
              <Text className='m5-order__amount'>¥{order.amountLabel}</Text>
            </View>
            <Text className='bf-muted m5-order__id'>订单号 {order.id}</Text>
            <Text className='bf-muted m5-order__id'>支付渠道 {orderChannelLabel}</Text>

            {/* M5-09：金额明细（原价 / 减免 / 实付），让用户对得上账 */}
            {order.discountCents > 0 && (
              <View className='m5-amounts'>
                <View className='bf-row m5-amounts__row'>
                  <Text className='bf-muted m5-amounts__k'>原价</Text>
                  <Text className='m5-amounts__orig'>¥{order.originalLabel}</Text>
                </View>
                <View className='bf-row m5-amounts__row'>
                  <Text className='bf-muted m5-amounts__k'>
                    优惠{order.couponCode ? `（${order.couponCode}）` : ''}
                  </Text>
                  <Text className='m5-amounts__off'>-¥{order.discountLabel}</Text>
                </View>
                <View className='bf-row m5-amounts__row'>
                  <Text className='bf-muted m5-amounts__k'>实付</Text>
                  <Text className='m5-amounts__final'>¥{order.amountLabel}</Text>
                </View>
              </View>
            )}

            <View className='m5-timeline'>
              {order.timeline.map((t) => (
                <View key={t.status} className='m5-tl'>
                  <View className='m5-tl__left'>
                    <Text className={`m5-tl__dot ${t.done ? 'is-done' : ''} ${t.active ? 'is-active' : ''}`}>
                      {t.done ? '●' : '○'}
                    </Text>
                    <View className='m5-tl__line' />
                  </View>
                  <View className='m5-tl__body'>
                    <Text className={`m5-tl__label ${t.done ? 'is-done' : ''}`}>{t.label}</Text>
                    <Text className='bf-muted m5-tl__time'>{formatTime(t.at)}</Text>
                  </View>
                </View>
              ))}
            </View>
          </View>

          {order.status === 'delivered' && (
            <View className='bf-card'>
              <Text className='bf-card__title'>启动包已生成</Text>
              <Text className='bf-muted m5-order__hint'>
                10 件交付物已全部生成（D01–D10）。交付物下载由「我的启动包」模块提供。
              </Text>
            </View>
          )}

          {order.status === 'generating' && (
            <View className='bf-card'>
              <Text className='bf-card__title'>正在生成你的启动包…</Text>
              <Text className='bf-muted m5-order__hint'>
                生成完成后会在这里和消息中心同时提醒你，可以先去忙别的。
              </Text>
            </View>
          )}

          {order.status === 'refunded' && (
            <View className='m5-tip'>
              退款已受理，将在 24 小时内原路退还 ¥{order.amountLabel}。
            </View>
          )}

          {order.status === 'closed' && (
            <View className='m5-tip m5-tip--muted'>
              订单已关闭（超时未支付）。需要的话可以重新下单。
            </View>
          )}

          {/* M5-10：命中风控时如实告知「已转人工审核」，不静默拦截、不假装成功 */}
          {order.risk?.flagged && <View className='m5-tip m5-tip--warn'>{order.risk.notice}</View>}

          <View className='bf-row m5-actions'>
            <View className='bf-btn bf-btn--ghost m5-actions__btn' onClick={refreshOrder}>
              刷新订单状态
            </View>
            {order.canRefund && (
              <View className='bf-btn bf-btn--ghost m5-actions__btn' onClick={doRefund}>
                7 天无理由退款
              </View>
            )}
          </View>

          {(order.status === 'closed' || order.status === 'refunded') && (
            <View className='bf-btn m5-paybtn' onClick={() => setOrder(null)}>
              重新购买
            </View>
          )}

          <Text className='bf-muted m5-foot'>
            支付回调与主动查单双保险（M5-06），不会漏单。退款 24 小时内到账（M5-07）。
          </Text>
        </>
      ) : (
        <>
          {/* ---------- M5-03：三档价格同屏 ---------- */}
          {plans.length === 0 && !error && <Loading text='正在获取价格…' />}

          <View className='m5-plans'>
            {plans.map((p) => (
              <View
                key={p.plan}
                className={`m5-plan ${plan === p.plan ? 'is-active' : ''} ${p.highlight ? 'is-hot' : ''}`}
                onClick={() => setPlan(p.plan)}
              >
                {p.highlight && <Text className='m5-plan__badge'>{p.badge}</Text>}
                <Text className='m5-plan__name'>{p.name}</Text>
                <View className='m5-plan__price'>
                  <Text className='m5-plan__cur'>¥</Text>
                  <Text className='m5-plan__num'>{p.priceLabel}</Text>
                  <Text className='m5-plan__unit'>/{p.unitLabel}</Text>
                </View>
                {!p.highlight && <Text className='m5-plan__badge m5-plan__badge--plain'>{p.badge}</Text>}
              </View>
            ))}
          </View>

          {/* 三档权益清单（M5-03：同屏对比） */}
          <View className='bf-card'>
            <Text className='bf-card__title'>已选：{current?.name || '单次启动包'}</Text>
            <View className='m5-rights'>
              {(current?.rights || []).map((r) => (
                <View key={r} className='m5-right'>
                  <Text className='m5-right__check'>✓</Text>
                  <Text className='m5-right__text'>{r}</Text>
                </View>
              ))}
            </View>
          </View>

          {/* ---------- M5-09 优惠券 / 邀请码 ---------- */}
          <View className='bf-card'>
            <View className='bf-row'>
              <Text className='bf-card__title'>优惠券 / 邀请码</Text>
              {couponInfo && (
                <Text className='m5-coupon__clear' onClick={clearCoupon}>
                  清除
                </Text>
              )}
            </View>

            <View className='m5-coupon__inputrow'>
              <Input
                className='bf-input m5-coupon__input'
                type='text'
                value={coupon}
                placeholder='输入券码或邀请码（如 WELCOME5）'
                placeholderClass='bf-muted'
                maxlength={32}
                onInput={(e) => {
                  setCoupon(e.detail.value)
                  setCouponErr('')
                }}
              />
              <View
                className='bf-btn bf-btn--sm bf-btn--ghost m5-coupon__apply'
                onClick={() => applyCoupon(coupon, plan)}
              >
                校验
              </View>
            </View>

            {couponErr && <Text className='m5-coupon__err'>{couponErr}</Text>}

            {couponInfo && (
              <View className='m5-coupon__ok'>
                <Text className='m5-coupon__oktitle'>
                  {couponInfo.title} · {couponInfo.code}
                </Text>
                <Text className='bf-muted m5-coupon__oktext'>
                  原价 ¥{couponInfo.originalLabel}，优惠 ¥{couponInfo.discountLabel}，到手 ¥
                  {couponInfo.finalLabel}
                </Text>
              </View>
            )}

            {/* PRD M5-09：规则必须在页面上明示，不能藏在协议里 */}
            <Text className='bf-muted m5-coupon__rules'>
              {couponInfo?.rules || couponRules || '优惠券不可叠加，同一订单只能使用一张。'}
            </Text>

            {couponList.length > 0 && (
              <>
                <Text className='m5-coupon__more' onClick={() => setCouponOpen(!couponOpen)}>
                  {couponOpen ? '收起可用券 ︿' : `查看可用券（${couponList.length}）﹀`}
                </Text>
                {couponOpen && (
                  <View className='m5-coupon__list'>
                    {couponList.map((c) => (
                      <View
                        key={c.code}
                        className={`m5-coupon__item ${c.usable ? '' : 'is-dead'}`}
                        onClick={() => c.usable && applyCoupon(c.code, plan)}
                      >
                        <View className='bf-row'>
                          <Text className='m5-coupon__code'>{c.code}</Text>
                          <Text className='m5-coupon__value'>{c.discountLabel}</Text>
                        </View>
                        <Text className='bf-muted m5-coupon__title'>{c.title}</Text>
                        <Text className='bf-muted m5-coupon__cond'>
                          {c.planScopeLabel}
                          {c.minAmount > 0 ? ` · 满 ¥${(c.minAmount / 100).toFixed(0)} 可用` : ''}
                          {c.usable ? '' : ` · ${c.reason}`}
                        </Text>
                      </View>
                    ))}
                  </View>
                )}
                {couponHint && <Text className='bf-muted m5-coupon__rules'>{couponHint}</Text>}
              </>
            )}
          </View>

          {/* ---------- M5-08 自动续费 ---------- */}
          {isSubscriptionPlan(plan) && (
            <View className='bf-card'>
              <Text className='bf-card__title'>自动续费（可选）</Text>
              <View className='bf-row m5-renew__row' onClick={() => setAutoRenew(!autoRenew)}>
                <View className='m5-renew__left'>
                  <Text className='m5-renew__label'>到期自动续费</Text>
                  <Text className='bf-muted m5-renew__desc'>
                    开启后到期前 3 天会提醒你一次，不想续了随时可以在本页一键关闭。
                  </Text>
                </View>
                <View className={`m5-switch ${autoRenew ? 'is-on' : ''}`}>
                  <View className='m5-switch__dot' />
                </View>
              </View>
            </View>
          )}

          {/* ---------- M5-08 我的会员与续费管理 ---------- */}
          <View className='bf-card'>
            <View className='bf-row'>
              <Text className='bf-card__title'>我的会员</Text>
              <Text className={`bf-tag ${sub?.isMember ? 'bf-tag--good' : ''}`}>
                {sub?.isMember ? sub.planName : '非会员'}
              </Text>
            </View>

            {sub?.isMember ? (
              <>
                <Text className='bf-muted m5-order__hint'>
                  到期时间 {formatDay(sub.expireAt)}
                  {sub.daysLeft !== null ? ` · 还剩 ${sub.daysLeft} 天` : ''}
                </Text>
                <Text className='bf-muted m5-order__hint'>
                  自动续费：{sub.autoRenew ? '已开启' : '已关闭'}
                  {sub.autoRenew && sub.renewAt ? ` · 下次扣费 ${formatDay(sub.renewAt)}` : ''}
                </Text>
                {sub.notice ? <Text className='bf-muted m5-order__hint'>{sub.notice}</Text> : null}
                <View className='bf-row m5-actions'>
                  <View
                    className='bf-btn bf-btn--ghost bf-btn--sm m5-actions__btn'
                    onClick={toggleAutoRenew}
                  >
                    {sub.autoRenew ? '关闭自动续费' : '开启自动续费'}
                  </View>
                  {sub.autoRenew && (
                    <View
                      className='bf-btn bf-btn--ghost bf-btn--sm m5-actions__btn'
                      onClick={doCancelSubscription}
                    >
                      一键取消续费
                    </View>
                  )}
                </View>
              </>
            ) : (
              <Text className='bf-muted m5-order__hint'>
                {sub?.message ||
                  '你现在还不是会员。购买月度/年度会员时可以选择自动续费，续费前 3 天会先提醒你，取消入口就在本页，不超过 3 步。'}
              </Text>
            )}
          </View>

          <View className='bf-card'>
            <Text className='bf-card__title'>本端支付方式</Text>
            <Text className='bf-muted m5-order__hint'>
              {PLATFORM_LABELS[platform] || platform} 将使用<span className='m5-em'>{localChannel}</span>。
              同一账号在各端的会员权益互通。
            </Text>
          </View>

          {/* 金额预览：券后价写在按钮上，避免支付时金额跳变 */}
          {couponInfo && (
            <View className='bf-row m5-amountbar'>
              <Text className='bf-muted m5-amountbar__k'>已优惠 ¥{couponInfo.discountLabel}</Text>
              <Text className='m5-amountbar__v'>
                原价 <Text className='m5-amountbar__orig'>¥{couponInfo.originalLabel}</Text> → ¥
                {couponInfo.finalLabel}
              </Text>
            </View>
          )}

          <View
            className={`bf-btn m5-paybtn ${loading ? 'bf-btn--disabled' : ''}`}
            onClick={() => !loading && startPay()}
          >
            {loading ? '正在下单…' : `支付 ¥${finalLabel}`}
          </View>

          <Text className='bf-muted m5-foot'>
            支持 7 天无理由退款，24 小时内原路到账。支付成功后立即开始生成 10 件交付物。
          </Text>
        </>
      )}

      {/* ---------- 支付弹窗 ---------- */}
      {paying && (
        <View className='m5-mask' onClick={() => setPaying(null)}>
          <View className='m5-modal' onClick={(e) => e.stopPropagation()}>
            <Text className='m5-modal__title'>请使用{channel}完成支付</Text>
            <Text className='m5-modal__amount'>¥{paying.amountLabel}</Text>
            <View className='m5-modal__qr'>
              <Text className='m5-modal__qrtext'>{(paying.payParams.qrContent || 'bizfast://pay').slice(0, 34)}</Text>
            </View>
            <Text className='bf-muted m5-modal__notice'>{paying.payParams.notice}</Text>
            {paying.risk?.flagged && <Text className='m5-modal__risk'>{paying.risk.notice}</Text>}
            <View className='bf-btn m5-modal__btn' onClick={confirmPaid}>
              我已完成支付
            </View>
            <View
              className='bf-btn bf-btn--ghost m5-modal__btn'
              onClick={() => {
                setPaying(null)
                loadOrder(paying.orderId)
              }}
            >
              稍后再付 / 查看订单
            </View>
          </View>
        </View>
      )}
    </View>
  )
}

function formatTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

/** M5-08：续费日期只需到天，避免用户误以为精确到秒的扣费时刻。 */
function formatDay(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
