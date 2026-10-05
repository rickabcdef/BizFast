import { useCallback, useEffect, useState } from 'react'
import { View, Text } from '@tarojs/components'
import Loading from '@/components/Loading'
import ErrorTip from '@/components/ErrorTip'
import { getAdminDashboard, type DashboardKpis, type DashboardTrend } from '@/services/bApi'

// M11-05 数据看板：核心指标实时看板（数据延迟 ≤ 5 分钟）
export default function DashboardView() {
  const [kpis, setKpis] = useState<DashboardKpis | null>(null)
  const [trend, setTrend] = useState<DashboardTrend[]>([])
  const [refreshAt, setRefreshAt] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const d = await getAdminDashboard()
      setKpis(d.kpis)
      setTrend(d.trend)
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

  const maxOrders = Math.max(1, ...trend.map((t) => t.orders))
  const maxRevenue = Math.max(1, ...trend.map((t) => t.revenue))

  const cards = kpis
    ? [
        { label: '诊断完成数', value: String(kpis.diagnoseCount), unit: '人' },
        { label: '付费单数', value: String(kpis.payCount), unit: '单' },
        { label: '总收入', value: `¥${kpis.revenueYuan}`, unit: '' },
        { label: '付费转化率', value: kpis.conversionRate, unit: '' },
        { label: '交付成功率', value: kpis.packageDoneRate, unit: '' },
        { label: '退款率', value: kpis.refundRate, unit: '' },
        { label: '客单价', value: `¥${kpis.avgOrderYuan}`, unit: '' }
      ]
    : []

  return (
    <View className='m11-dash'>
      {error && <ErrorTip message={error} onRetry={load} />}

      {/* 核心 KPI 卡片 */}
      <View className='m11-kpis'>
        {cards.map((c) => (
          <View key={c.label} className='m11-kpi'>
            <Text className='m11-kpi__label'>{c.label}</Text>
            <Text className='m11-kpi__value'>
              {c.value}
              {c.unit && <Text className='m11-kpi__unit'>{c.unit}</Text>}
            </Text>
          </View>
        ))}
      </View>

      {/* 近 7 天趋势（订单数 + 收入，纯 CSS 绘制，无第三方图表依赖） */}
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

      <Text className='bf-muted m11-note'>
        口径：付费转化率 = 支付成功人数 ÷ 诊断完成人数；数据延迟 ≤ 5 分钟（M11-05）。
      </Text>
    </View>
  )
}
