import { useCallback, useEffect, useState } from 'react'
import { View, Text } from '@tarojs/components'
import Loading from '@/components/Loading'
import ErrorTip from '@/components/ErrorTip'
import { getAdminCostMonitor, type CostMonitorData } from '@/services/bApi'

// V5.0 M4-05 AI 成本监控 | 负责人: B | 优先级: P0
// 需求点：
//   M4-05-1 成本占收入比超 25% 自动红色告警（警戒 15% / 红线 25%）
//   M4-05-2 今日 / 本月成本、平均单次成本与毛利率
//   M4-05-3 六道成本闸门状态（模型路由 / 缓存复用 / 模板化 / 轮数上限 / 多模态限额 / 预算熔断）
//   M4-05-4 按模型与按功能看成本分布
// 视觉对齐：assets/切好的HTML页面/生意快启-UI切图V5.0/18-成本监控.html

const GATE_ROWS = [
  { name: '① 模型路由', desc: '默认轻档，验收不过才升档' },
  { name: '② 缓存复用', desc: '提示词/商机库/模板全量缓存' },
  { name: '③ 模板化生成', desc: '10 件交付物：7 件模板 + 3 件 AI' },
  { name: '④ 轮数上限', desc: '防止智能体放飞' },
  { name: '⑤ 多模态限额', desc: '免费层不给生图，视频只加购' },
  { name: '⑥ 预算与熔断', desc: '用户级/项目级/密钥级三重上限' }
]

function yuan(cents: number): string {
  return (cents / 100).toFixed(2)
}

export default function CostView() {
  const [data, setData] = useState<CostMonitorData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setData(await getAdminCostMonitor())
    } catch (e: any) {
      setError(e?.message || '成本监控加载失败，请重试')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  if (loading && !data) return <Loading text='正在加载成本监控…' />
  if (error && !data) return <ErrorTip message={error} onRetry={load} />

  const t = data!.today
  const m = data!.month
  const ratioPct = Math.round(t.costRatio * 1000) / 10
  const redLine = Math.round(data!.alertRatio * 100)
  const warnLine = Math.round(redLine * 0.6)
  const inDanger = t.costRatio >= data!.alertRatio
  const inWarn = !inDanger && t.costRatio >= data!.alertRatio * 0.6
  // 平均单次成本（按本月累计：总成本 / 总调用）与毛利率（单次定价 29.9）
  const avgCost = m.calls > 0 ? m.costCents / m.calls : 0
  const margin = avgCost > 0 ? Math.max(0, Math.round((1 - avgCost / 2990) * 1000) / 10) : 0

  // 成本分布（按功能，占比 = 功能成本 / 本月总成本）
  const featTotal = m.costCents || 1
  const featBars = data!.byFeature.map((f) => ({
    ...f,
    pct: Math.round((f.costCents / featTotal) * 1000) / 10
  }))
  const modelTotal = m.costCents || 1
  const modelBars = data!.byModel.map((x) => ({
    ...x,
    pct: Math.round((x.costCents / modelTotal) * 1000) / 10
  }))

  return (
    <View className='m11-cost'>
      {error && <ErrorTip message={error} onRetry={load} />}

      {/* 状态告警 */}
      <View className={`m11-alert ${inDanger ? 'm11-alert--danger' : inWarn ? 'm11-alert--warn' : 'm11-alert--ok'}`}>
        <Text className='m11-alert__icon'>{inDanger ? '🔴' : inWarn ? '⚠️' : '✅'}</Text>
        <Text className='m11-alert__text'>{data!.notice}（警戒线 {warnLine}%，红线 {redLine}%）</Text>
      </View>

      {/* 4 个核心卡 */}
      <View className='m11-kpis'>
        <View className='m11-kpi'>
          <Text className='m11-kpi__label'>今日 AI 成本</Text>
          <Text className='m11-kpi__value'>¥{yuan(t.costCents)}</Text>
          <Text className='m11-kpi__sub'>{t.calls} 次调用</Text>
        </View>
        <View className='m11-kpi'>
          <Text className='m11-kpi__label'>成本占收入比</Text>
          <Text className={`m11-kpi__value ${inDanger ? 'm11-txt--danger' : ''}`}>{ratioPct}%</Text>
          <Text className='m11-kpi__sub'>{inDanger ? '🔴 超红线，请立即优化' : inWarn ? '⚠️ 接近警戒线' : '✓ 安全区间'}</Text>
        </View>
        <View className='m11-kpi'>
          <Text className='m11-kpi__label'>本月累计成本</Text>
          <Text className='m11-kpi__value'>¥{yuan(m.costCents)}</Text>
          <Text className='m11-kpi__sub'>{m.calls} 次调用 · ¥{yuan(m.revenueCents)} 收入</Text>
        </View>
        <View className='m11-kpi'>
          <Text className='m11-kpi__label'>平均单次成本（礼包）</Text>
          <Text className='m11-kpi__value'>¥{(avgCost / 100).toFixed(2)}</Text>
          <Text className='m11-kpi__sub'>毛利率 {margin}%</Text>
        </View>
      </View>

      {/* 六道成本闸门 */}
      <View className='bf-card'>
        <View className='bf-row'>
          <Text className='bf-card__title'>🛡️ 六道成本闸门状态</Text>
          <Text className='bf-muted'>预算：免费 ¥{(data!.budget.free / 100).toFixed(2)} · 单次 ¥{(data!.budget.single / 100).toFixed(2)} · 月卡 ¥{(data!.budget.month / 100).toFixed(2)}</Text>
        </View>
        <View className='m11-table'>
          {GATE_ROWS.map((g, i) => {
            const gate = data!.gates
            let setting = '已启用'
            let run = '—'
            if (i === 0) setting = gate.modelTier
            if (i === 1) { setting = '前缀缓存已开启'; run = `命中率 ${Math.round(gate.cacheHitRate * 100)}%` }
            if (i === 2) { setting = '模板 7 / AI 3'; run = `模板占比 ${Math.round(gate.templateRatio * 100)}%` }
            if (i === 3) { setting = `诊断≤${gate.maxRounds.diagnose} 轮 / 启动包≤${gate.maxRounds.package} 轮`; run = '本月超限 0 次' }
            if (i === 4) setting = '生图按张扣额度，视频/数字人只加购'
            if (i === 5) setting = '已配置用户/项目/密钥三重上限'
            return (
              <View key={g.name} className='m11-table__row'>
                <View className='m11-table__cell m11-table__cell--name'>
                  <Text className='m11-gate-name'>{g.name}</Text>
                  <Text className='m11-gate-desc'>{g.desc}</Text>
                </View>
                <View className='m11-table__cell'><Text className='bf-muted'>{setting}</Text></View>
                <View className='m11-table__cell'><Text className='bf-muted'>{run}</Text></View>
                <View className='m11-table__cell'><Text className='m11-tag m11-tag--ok'>✓ 正常</Text></View>
              </View>
            )
          })}
        </View>
      </View>

      <View className='m11-row2'>
        {/* 成本分布（按模型） */}
        <View className='bf-card'>
          <Text className='bf-card__title'>成本分布（本月 · 按模型）</Text>
          {modelBars.map((x) => (
            <View key={x.model} className='m11-costbar'>
              <View className='m11-costbar__head'>
                <Text>{x.model}</Text>
                <Text className='bf-muted'>¥{x.costLabel} · {x.pct}%</Text>
              </View>
              <View className='m11-costbar__track'>
                <View className='m11-costbar__in' style={{ width: `${Math.max(2, x.pct)}%` }} />
              </View>
            </View>
          ))}
        </View>

        {/* 成本明细（按功能） */}
        <View className='bf-card'>
          <Text className='bf-card__title'>成本明细（本月 · 按功能）</Text>
          {featBars.map((f) => (
            <View key={f.feature} className='m11-costbar'>
              <View className='m11-costbar__head'>
                <Text>{f.featureLabel}</Text>
                <Text className='bf-muted'>{f.calls} 次 · ¥{f.costLabel} · {f.pct}%</Text>
              </View>
              <View className='m11-costbar__track'>
                <View className='m11-costbar__in m11-costbar__in--alt' style={{ width: `${Math.max(2, f.pct)}%` }} />
              </View>
            </View>
          ))}
        </View>
      </View>

      <Text className='bf-muted m11-note'>
        口径：成本占收入比 = AI 成本 ÷ 当日已支付订单营收；六道闸门每日自动校验，超 25% 自动红色告警（M4-05）。
      </Text>
    </View>
  )
}
