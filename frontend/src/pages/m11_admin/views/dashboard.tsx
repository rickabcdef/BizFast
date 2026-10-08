import { useCallback, useEffect, useRef, useState } from 'react'
import { View, Text } from '@tarojs/components'
import Loading from '@/components/Loading'
import ErrorTip from '@/components/ErrorTip'
import {
  getAdminDashboard,
  getAdminAlerts,
  getAdminDailyReports,
  type DashboardKpis,
  type DashboardTrend,
  type AdminAlertItem,
  type DailyReportItem
} from '@/services/bApi'

// V5.0 M4-01 现金流看板（数据看板改版） | 负责人: B | 优先级: P0
// 需求点：
//   M4-01-1 今日营收 / 今日订单数 / 今日新增用户 / 付费率 / 退款率 / AI 成本 / 净现金流
//   M4-01-2 7 日营收趋势；数字跳动动画；红色告警异常指标；3 秒见当日数据
//   M4-01-3 运营自动化入口：最新告警 + 每日数据日报
// 视觉对齐：assets/切好的HTML页面/生意快启-UI切图V5.0/13-管理后台.html

/** 数字跳动动画：目标值在 ~900ms 内从 0 递增（M4-01-2）。 */
function AnimatedNumber({ value, prefix = '', suffix = '', decimals = 0 }: { value: number; prefix?: string; suffix?: string; decimals?: number }) {
  const [display, setDisplay] = useState(0)
  const frame = useRef(0)

  useEffect(() => {
    const start = Date.now()
    const duration = 900
    const from = 0
    const to = value
    const step = () => {
      const p = Math.min(1, (Date.now() - start) / duration)
      const eased = 1 - Math.pow(1 - p, 3)
      setDisplay(from + (to - from) * eased)
      if (p < 1) frame.current = requestAnimationFrame(step)
    }
    frame.current = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame.current)
  }, [value])

  return (
    <Text>
      {prefix}
      {display.toFixed(decimals)}
      {suffix}
    </Text>
  )
}

function fmt(cents: number): string {
  const v = cents / 100
  return v >= 1000 ? `${(v / 1000).toFixed(2)}k` : v.toFixed(0)
}

export default function DashboardView() {
  const [kpis, setKpis] = useState<DashboardKpis | null>(null)
  const [trend, setTrend] = useState<DashboardTrend[]>([])
  const [alerts, setAlerts] = useState<AdminAlertItem[]>([])
  const [reports, setReports] = useState<DailyReportItem[]>([])
  const [refreshAt, setRefreshAt] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [d, a, r] = await Promise.all([
        getAdminDashboard(),
        getAdminAlerts({ limit: 3 }),
        getAdminDailyReports(3)
      ])
      setKpis(d.kpis)
      setTrend(d.trend)
      setAlerts(a.items)
      setReports(r.items)
      setRefreshAt(d.refreshAt)
    } catch (e: any) {
      setError(e?.message || '看板加载失败，请重试')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  if (loading && !kpis) return <Loading text='正在加载看板…' />
  if (error && !kpis) return <ErrorTip message={error} onRetry={load} />

  const k = kpis!
  const aiCost = k.aiCostCents
  const netCash = k.netCashflowCents
  const cashOk = netCash >= 0
  const costDanger = aiCost > 0 && k.todayRevenueCents > 0 && aiCost / k.todayRevenueCents >= 0.25
  const maxOrders = Math.max(1, ...trend.map((t) => t.orders))
  const maxRevenue = Math.max(1, ...trend.map((t) => t.revenue))

  const cards = [
    { label: '今日营收（元）', node: <AnimatedNumber value={Math.round(k.todayRevenueCents / 100)} prefix='¥' />, danger: false },
    { label: '今日订单数', node: <AnimatedNumber value={k.todayOrderCount} />, danger: false },
    { label: '今日新增用户', node: <AnimatedNumber value={k.todayNewUsers} />, danger: false },
    { label: '付费转化率', node: <AnimatedNumber value={Number(k.conversionRate.replace('%', '')) || 0} suffix='%' decimals={1} />, danger: false }
  ]
  const subCards = [
    { label: '累计诊断', value: String(k.diagnoseCount) },
    { label: '累计付费', value: String(k.payCount) },
    { label: '累计营收', value: `¥${fmt(Math.round(k.revenueYuan * 100))}` },
    { label: '退款率', value: k.refundRate, bad: Number(k.refundRate.replace('%', '')) > 5 },
    { label: '交付成功率', value: k.packageDoneRate }
  ]

  return (
    <View className='m11-dash'>
      {error && <ErrorTip message={error} onRetry={load} />}

      {/* 异常告警条 */}
      <View className={`m11-alert ${alerts.some((a) => a.level === 'warning') ? 'm11-alert--warn' : 'm11-alert--ok'}`}>
        <Text className='m11-alert__icon'>{alerts.some((a) => a.level === 'warning') ? '⚠️' : '✅'}</Text>
        <Text className='m11-alert__text'>
          {alerts.length > 0
            ? alerts.slice(0, 2).map((a) => a.title).join('；')
            : '暂无待处理告警，一切正常'}
        </Text>
      </View>

      {/* 4 个核心数据卡（数字跳动动画） */}
      <View className='m11-kpis'>
        {cards.map((c) => (
          <View key={c.label} className='m11-kpi'>
            <Text className='m11-kpi__label'>{c.label}</Text>
            <Text className={`m11-kpi__value ${c.danger ? 'm11-txt--danger' : ''}`}>{c.node}</Text>
          </View>
        ))}
      </View>

      {/* 第二行数据卡 */}
      <View className='m11-kpis m11-kpis--sub'>
        {subCards.map((c) => (
          <View key={c.label} className='m11-kpi m11-kpi--flat'>
            <Text className='m11-kpi__label'>{c.label}</Text>
            <Text className={`m11-kpi__value m11-kpi__value--sm ${c.bad ? 'm11-txt--danger' : ''}`}>{c.value}</Text>
          </View>
        ))}
      </View>

      {/* 现金流卡：AI 成本 / 净现金流 */}
      <View className='m11-cash'>
        <View className={`m11-cash__cell ${costDanger ? 'm11-txt--danger' : ''}`}>
          <Text className='m11-cash__label'>今日 AI 成本</Text>
          <Text className='m11-cash__value'><AnimatedNumber value={aiCost / 100} prefix='¥' decimals={2} /></Text>
          <Text className='m11-cash__sub'>{costDanger ? '🔴 成本占收入比超 25%，请到成本监控处理' : '✓ 成本健康'}</Text>
        </View>
        <View className='m11-cash__cell'>
          <Text className='m11-cash__label'>今日净现金流</Text>
          <Text className={`m11-cash__value ${cashOk ? 'm11-txt--ok' : 'm11-txt--danger'}`}>
            <AnimatedNumber value={Math.abs(netCash) / 100} prefix={cashOk ? '¥' : '-¥'} decimals={2} />
          </Text>
          <Text className='m11-cash__sub'>= 营收 − AI 成本 − 渠道费</Text>
        </View>
      </View>

      {/* 近 7 天趋势（订单数 + 收入） */}
      <View className='bf-card'>
        <View className='bf-row'>
          <Text className='bf-card__title'>近 7 天趋势</Text>
          <Text className='bf-muted'>订单数 / 收入</Text>
        </View>
        <View className='m11-trend'>
          {trend.map((t) => (
            <View key={t.date} className='m11-trend__col'>
              <View className='m11-trend__bars'>
                <View
                  className='m11-trend__bar m11-trend__bar--rev'
                  style={{ height: `${Math.max(8, Math.round((t.revenue / maxRevenue) * 120))}rpx` }}
                />
                <View
                  className='m11-trend__bar m11-trend__bar--ord'
                  style={{ height: `${Math.max(8, Math.round((t.orders / maxOrders) * 120))}rpx` }}
                />
              </View>
              <Text className='m11-trend__date'>{t.date}</Text>
              <Text className='m11-trend__num'>{t.orders} 单</Text>
            </View>
          ))}
        </View>
        <View className='bf-row m11-trend__legend'>
          <Text className='m11-trend__leg m11-trend__leg--ord'>订单数</Text>
          <Text className='m11-trend__leg m11-trend__leg--rev'>收入</Text>
          <Text className='bf-muted'>刷新时间 {refreshAt}</Text>
        </View>
      </View>

      {/* 每日数据日报（第 8 章运营自动化 · 每天 9 点自动生成） */}
      {reports.length > 0 && (
        <View className='bf-card'>
          <View className='bf-row'>
            <Text className='bf-card__title'>每日数据日报</Text>
            <Text className='bf-muted'>每天 9:00 自动生成</Text>
          </View>
          {reports.map((r) => (
            <View key={r.id} className='m11-report'>
              <View className='m11-report__head'>
                <Text className='m11-report__date'>{r.reportDate}</Text>
                <Text className='m11-report__net'>净现金流 <Text className={Number(r.netCashCents) >= 0 ? 'm11-txt--ok' : 'm11-txt--danger'}>¥{r.netCashLabel}</Text></Text>
              </View>
              <Text className='m11-report__line'>
                营收 ¥{r.revenueLabel} · 订单 {r.orderCount} 单 · 新增 {r.newUsers} 人 · AI 成本 ¥{r.aiCostLabel} · 退款 ¥{r.refundLabel}
              </Text>
            </View>
          ))}
        </View>
      )}

      <Text className='bf-muted m11-note'>
        口径：付费转化率 = 支付成功人数 ÷ 诊断完成人数；净现金流 = 今日营收 − AI 成本；数据延迟 ≤ 5 分钟（M4-01）。
      </Text>
    </View>
  )
}
