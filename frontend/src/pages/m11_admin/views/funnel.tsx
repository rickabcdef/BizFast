import { useCallback, useEffect, useState } from 'react'
import { View, Text } from '@tarojs/components'
import Loading from '@/components/Loading'
import ErrorTip from '@/components/ErrorTip'
import { getAdminFunnel, getAdminGrowth, type FunnelData, type GrowthData } from '@/services/bApi'

// V5.0 M4-07 转化漏斗 + M4-08 裂变数据看板 | 负责人: B | 优先级: P0
// 需求点：
//   M4-07 漏斗：访问→开始诊断→完成诊断→点击付费→支付成功→下载交付物；按日/周/月；异常流失标红
//   M4-08 裂变：转发量 / 带来新用户 / 带来付费 / 单用户裂变获客成本 / K 因子实时
// 视觉对齐：assets/切好的HTML页面/生意快启-UI切图V5.0/19-转化与裂变.html

const PERIODS = [
  { key: 'day', label: '今日' },
  { key: 'week', label: '近 7 天' },
  { key: 'month', label: '近 30 天' }
]

function yuan(cents: number): string {
  return (cents / 100).toFixed(2)
}

export default function FunnelView() {
  const [period, setPeriod] = useState('day')
  const [funnel, setFunnel] = useState<FunnelData | null>(null)
  const [growth, setGrowth] = useState<GrowthData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async (p: string) => {
    setLoading(true)
    setError('')
    try {
      const [f, g] = await Promise.all([getAdminFunnel(p), getAdminGrowth()])
      setFunnel(f)
      setGrowth(g)
    } catch (e: any) {
      setError(e?.message || '转化与裂变数据加载失败，请重试')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load(period)
  }, [load, period])

  if (loading && !funnel) return <Loading text='正在加载转化与裂变数据…' />
  if (error && !funnel) return <ErrorTip message={error} onRetry={() => load(period)} />

  const f = funnel!
  const g = growth!.summary
  const top = f.steps[0]?.value || 1
  const overallPct = Math.round(f.overallConversion * 1000) / 10
  const pass = overallPct >= 3
  const kOk = g.kFactor >= 1

  return (
    <View className='m11-funnel'>
      {error && <ErrorTip message={error} onRetry={() => load(period)} />}

      {/* 状态告警 */}
      <View className={`m11-alert ${pass && !f.steps.some((s) => s.dropAlert) ? 'm11-alert--ok' : 'm11-alert--warn'}`}>
        <Text className='m11-alert__icon'>{pass ? '✅' : '⚠️'}</Text>
        <Text className='m11-alert__text'>
          {f.notice}；首单转化率 {overallPct}%（存活线 3%），K 因子 {g.kFactor}（K&gt;1 即自增长飞轮）。
        </Text>
      </View>

      {/* 周期切换 */}
      <View className='m11-periods'>
        {PERIODS.map((p) => (
          <View
            key={p.key}
            className={`m11-period ${period === p.key ? 'is-active' : ''}`}
            onClick={() => setPeriod(p.key)}
          >
            <Text>{p.label}</Text>
          </View>
        ))}
      </View>

      {/* 4 个核心 KPI */}
      <View className='m11-kpis'>
        <View className='m11-kpi'>
          <Text className='m11-kpi__label'>首单转化率</Text>
          <Text className={`m11-kpi__value ${pass ? 'm11-txt--ok' : 'm11-txt--danger'}`}>{overallPct}%</Text>
          <Text className='m11-kpi__sub'>{pass ? '✓ 达标（≥3%）' : '✗ 低于存活线'}</Text>
        </View>
        <View className='m11-kpi'>
          <Text className='m11-kpi__label'>K 因子（病毒系数）</Text>
          <Text className='m11-kpi__value'>{g.kFactor}</Text>
          <Text className='m11-kpi__sub'>每 {100} 用户带来 {Math.round(g.kFactor * 100)} 个新用户</Text>
        </View>
        <View className='m11-kpi'>
          <Text className='m11-kpi__label'>裂变获客成本</Text>
          <Text className='m11-kpi__value'>¥{g.fissionCacLabel}</Text>
          <Text className='m11-kpi__sub'>主要靠免费裂变</Text>
        </View>
        <View className='m11-kpi'>
          <Text className='m11-kpi__label'>裂变带来付费</Text>
          <Text className='m11-kpi__value'>{g.pays}</Text>
          <Text className='m11-kpi__sub'>付费用户 {g.paidInvitees} 人</Text>
        </View>
      </View>

      <View className='m11-row2'>
        {/* 转化漏斗 */}
        <View className='bf-card'>
          <View className='bf-row'>
            <Text className='bf-card__title'>转化漏斗（{PERIODS.find((p) => p.key === period)?.label}）</Text>
            <Text className='bf-muted'>看任务完成，不看打开次数</Text>
          </View>
          {f.steps.map((s, i) => {
            const width = Math.max(4, Math.round(s.rateFromTop * 100))
            const grad = ['#165DFF', '#3D7BFF', '#5A78FF', '#7B61FF', '#00B42A', '#00B42A'][i] || '#165DFF'
            return (
              <View key={s.step} className='m11-funnel__row'>
                <View className='m11-funnel__head'>
                  <Text className='m11-funnel__name'>
                    {['①', '②', '③', '④', '⑤', '⑥'][i] || ''} {s.label}
                  </Text>
                  <Text className='m11-funnel__num'>{s.value} 人</Text>
                </View>
                <View className='m11-funnel__track'>
                  <View
                    className={`m11-funnel__in ${s.dropAlert ? 'm11-funnel__in--drop' : ''}`}
                    style={{ width: `${width}%`, background: s.dropAlert ? 'linear-gradient(90deg,#F53F3F,#FF7D00)' : `linear-gradient(90deg,${grad},${grad})` }}
                  >
                    {width >= 18 ? `${Math.round(s.rateFromTop * 1000) / 10}%` : ''}
                  </View>
                </View>
                {s.dropAlert && (
                  <Text className='m11-funnel__drop'>⚠️ 此环节流失超 70%，建议检查页面引导与加载</Text>
                )}
              </View>
            )
          })}
          <Text className='bf-muted m11-note'>
            首单转化率 = 支付成功 ÷ 访问 = {overallPct}%（存活线 3%）
          </Text>
        </View>

        {/* 裂变数据 */}
        <View className='bf-card'>
          <Text className='bf-card__title'>裂变数据</Text>
          <View className='m11-growth-grid'>
            <View className='m11-growth-cell'>
              <Text className='m11-growth-label'>转发 / 保存卡片</Text>
              <Text className='m11-growth-value'>{g.shares} 次</Text>
            </View>
            <View className='m11-growth-cell'>
              <Text className='m11-growth-label'>带来新用户</Text>
              <Text className='m11-growth-value m11-txt--ok'>{g.registers} 人</Text>
            </View>
            <View className='m11-growth-cell'>
              <Text className='m11-growth-label'>邀请码分享率</Text>
              <Text className='m11-growth-value'>{Math.round(g.shareRate * 1000) / 10}%</Text>
            </View>
            <View className='m11-growth-cell'>
              <Text className='m11-growth-label'>发起邀请用户</Text>
              <Text className='m11-growth-value'>{g.uniqueInviters} 人</Text>
            </View>
          </View>
          {growth!.rows.length > 0 && (
            <View className='m11-growth-ch'>
              {growth!.rows.map((r) => {
                const pct = Math.max(4, Math.round((r.clicks / (g.shares || 1)) * 100))
                return (
                  <View key={r.channel} className='m11-costbar'>
                    <View className='m11-costbar__head'>
                      <Text>{r.channel}</Text>
                      <Text className='bf-muted'>{r.clicks} 次 · {pct}%</Text>
                    </View>
                    <View className='m11-costbar__track'>
                      <View className='m11-costbar__in m11-costbar__in--alt' style={{ width: `${pct}%` }} />
                    </View>
                  </View>
                )
              })}
            </View>
          )}
          <Text className='bf-muted m11-note'>
            口径：K 因子 = 被邀请注册数 ÷ 发起邀请人数；裂变成本 = 双方各 ¥10 邀请券 × 2 ÷ 裂变带来付费用户（M4-08）。
          </Text>
        </View>
      </View>
    </View>
  )
}
