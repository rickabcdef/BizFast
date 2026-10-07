<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  getAdminDashboard,
  getAdminUsers,
  getAdminOrders,
  getAdminOpportunities,
  getDailyReports,
  generateDailyReport,
  getAdminAlerts,
  scanAdminAlerts,
  readAdminAlerts,
  ORDER_ABNORMAL_LABEL,
  type DashboardKpis,
  type DashboardTrend,
  type TrendGranularity,
  type AdminUser,
  type AdminOrder,
  type AdminOpportunity,
  type DailyReport,
  type AdminAlertItem
} from '@/api/adminApi'

const router = useRouter()

const granularity = ref<TrendGranularity>('day')
const kpis = ref<DashboardKpis | null>(null)
const trend = ref<DashboardTrend[]>([])
const refreshAt = ref('')
const users = ref<AdminUser[]>([])
const orders = ref<AdminOrder[]>([])
const opps = ref<AdminOpportunity[]>([])
const loading = ref(true)
// V5.0 第 8 章：异常告警 + 昨日数据日报
const alerts = ref<AdminAlertItem[]>([])
const unreadAlerts = ref(0)
const report = ref<DailyReport | null>(null)

const pushStatusText = computed(() => {
  const s = report.value?.pushStatus
  return s === 'sent' ? '已推送' : s === 'failed' ? '推送失败' : '待推送'
})

const load = async (g: TrendGranularity) => {
  loading.value = true
  try {
    const [d, u, o, p] = await Promise.all([
      getAdminDashboard(g),
      getAdminUsers({ page: 1, pageSize: 50 }),
      getAdminOrders({ page: 1, pageSize: 50 }),
      getAdminOpportunities({ page: 1, pageSize: 50 })
    ])
    kpis.value = d.kpis
    trend.value = d.trend
    refreshAt.value = d.refreshAt
    users.value = u.items
    orders.value = o.items
    opps.value = p.items
  } finally {
    loading.value = false
  }
}

/** 告警与日报独立加载：任一失败不影响主看板（各自降级为空） */
const loadAutomation = async () => {
  try {
    const [al, rp] = await Promise.all([getAdminAlerts(), getDailyReports(1)])
    alerts.value = al.items
    unreadAlerts.value = al.unread
    report.value = rp.items[0] || null
  } catch {
    /* 忽略：不阻断主看板 */
  }
}

const onScanAlerts = async () => {
  await scanAdminAlerts()
  await loadAutomation()
}

const onReadAllAlerts = async () => {
  await readAdminAlerts()
  await loadAutomation()
}

const onGenerateReport = async () => {
  report.value = await generateDailyReport()
  await loadAutomation()
}

onMounted(() => {
  load('day')
  loadAutomation()
})

// ---- 统计卡（对齐切图 13 页：4 核心 + 5 累计，数据来自 Mock 真实聚合） ----
const payUsers = computed(() => users.value.filter((u) => u.memberStatus !== 'none').length)
const totalRevenue = computed(() => Math.round(orders.value.reduce((s, o) => s + o.amountYuan, 0) * 10) / 10)
const abnormalOrders = computed(() => orders.value.filter((o) => o.abnormal).length)
const refundPending = computed(() => orders.value.filter((o) => o.refundRequested && o.status !== 'refunded').length)

const coreCards = computed(() =>
  kpis.value
    ? [
        { icon: '👤', label: '注册用户', value: String(users.value.length), trend: `付费 ${payUsers.value} 人` },
        { icon: '💳', label: '今日订单数', value: String(kpis.value.payCount), trend: '↑ 较昨日' },
        { icon: '💰', label: '今日营收（元）', value: `¥${kpis.value.revenueYuan}`, trend: '↑ 较昨日' },
        { icon: '📈', label: '付费转化率', value: kpis.value.conversionRate, trend: '↑ 较上周' }
      ]
    : []
)

const cumCards = computed(() =>
  kpis.value
    ? [
        { label: '累计诊断', value: String(kpis.value.diagnoseCount) },
        { label: '累计付费', value: String(payUsers.value) },
        { label: '累计营收', value: `¥${totalRevenue.value}` },
        { label: '退款率', value: kpis.value.refundRate, color: 'var(--bf-ok)' },
        { label: '交付成功率', value: kpis.value.packageDoneRate, color: 'var(--bf-ok)' }
      ]
    : []
)

// ---- 营收趋势（柱状图，按日/周/月） ----
const maxRevenue = () => Math.max(1, ...trend.value.map((t) => t.revenue))

// ---- 商机分类占比（环形图） ----
const CAT_COLORS = ['#165DFF', '#7B61FF', '#00B42A', '#FF7D00', '#38BDF8']
const categoryShare = computed(() => {
  const map = new Map<string, number>()
  for (const o of opps.value) map.set(o.category, (map.get(o.category) || 0) + 1)
  const entries = [...map.entries()].sort((a, b) => b[1] - a[1])
  const total = opps.value.length || 1
  let acc = 0
  const segs = entries.map(([name, count], i) => {
    const pct = Math.round((count / total) * 100)
    const from = acc
    acc += pct
    return { name, count, pct, color: CAT_COLORS[i % CAT_COLORS.length], from, to: acc }
  })
  const gradient =
    segs.length === 0
      ? '#22304a'
      : `conic-gradient(${segs
          .map((s) => `${s.color} ${s.from}% ${s.to}%`)
          .join(', ')})`
  return { segs, gradient, total: opps.value.length }
})

// ---- 热门商机 TOP（派生：回本周期×40 + 毛利率×2 作为匹配热度，稳定可复现） ----
// 数值兜底：批量导入的商机可能缺 paybackMonths / marginPercent（None / 字符串），
// 直接相乘会得到 NaN，页面上显示「NaN分」——这里统一转数字，缺省按 0 计。
const heatOf = (o: AdminOpportunity): number => {
  const payback = Number(o.paybackMonths) || 0
  const margin = Number(o.marginPercent) || 0
  return payback * 40 + margin * 2
}
const topOpps = computed(() =>
  [...opps.value]
    .map((o) => ({ name: o.title, heat: heatOf(o) }))
    .sort((a, b) => b.heat - a.heat)
    .slice(0, 8)
)
const maxHeat = computed(() => Math.max(1, ...topOpps.value.map((t) => t.heat)))

// ---- 最近订单（取前 5 笔） ----
const recentOrders = computed(() => orders.value.slice(0, 5))
const orderTag = (o: AdminOrder) => {
  if (o.abnormal) return 'tag-red'
  if (o.status === 'delivered' || o.status === 'refunded') return 'tag-green'
  if (o.status === 'generating' || o.status === 'paid') return 'tag-orange'
  return 'tag-gray'
}
const orderTagText = (o: AdminOrder) => (o.abnormal ? `⚠️ ${ORDER_ABNORMAL_LABEL[o.abnormalType || ''] || '异常'}` : o.statusLabel)
</script>

<template>
  <div>
    <!-- 异常告警（对齐切图 13 页 alert-card） -->
    <div v-if="abnormalOrders > 0 || refundPending > 0" class="alert-card alert-warning">
      <span style="font-size: 18px">⚠️</span>
      <div>
        <strong>待处理提醒：</strong>
        当前有 <strong>{{ abnormalOrders }}</strong> 笔异常订单（已支付未交付 / 支付回调缺失），
        有 <strong>{{ refundPending }}</strong> 名用户申请退款待审核。
        <a style="color: var(--bf-warn); text-decoration: underline; margin-left: 8px; cursor: pointer" @click="router.push('/orders')">立即处理 →</a>
      </div>
    </div>

    <!-- 4 个核心数据卡 -->
    <div class="admin-stats">
      <div v-for="c in coreCards" :key="c.label" class="admin-stat-card">
        <div class="stat-icon" style="background: rgba(22, 93, 255, 0.15)">{{ c.icon }}</div>
        <div class="stat-label">{{ c.label }}</div>
        <div class="stat-value">{{ c.value }}</div>
        <div class="stat-trend trend-up">{{ c.trend }}</div>
      </div>
    </div>

    <!-- 累计指标卡 -->
    <div class="admin-stats" style="grid-template-columns: repeat(5, 1fr); margin-bottom: 24px">
      <div v-for="c in cumCards" :key="c.label" class="admin-stat-card" style="padding: 16px">
        <div class="stat-label" style="font-size: 12px">{{ c.label }}</div>
        <div class="stat-value" style="font-size: 20px" :style="c.color ? { color: c.color } : {}">{{ c.value }}</div>
      </div>
    </div>

    <!-- 图表区：营收趋势 + 商机分类占比 -->
    <div class="admin-chart-row">
      <div class="admin-chart-card">
        <div class="chart-header">
          <h3>📈 营收趋势</h3>
          <div class="chart-tabs">
            <button
              v-for="g in (['day', 'week', 'month'] as TrendGranularity[])"
              :key="g"
              class="chart-tab"
              :class="{ 'is-active': granularity === g }"
              @click="granularity = g; load(g)"
            >
              {{ g === 'day' ? '按日' : g === 'week' ? '按周' : '按月' }}
            </button>
          </div>
        </div>
        <div v-if="loading" style="padding: 60px; text-align: center; color: var(--bf-text-3)">加载中…</div>
        <div v-else class="bar-chart">
          <div v-for="t in trend" :key="t.label" class="bar-col">
            <div class="bar-fill" :style="{ height: `${Math.max(6, Math.round((t.revenue / maxRevenue()) * 150))}px` }">
              <span class="bar-value">¥{{ t.revenue }}</span>
            </div>
            <span class="bar-label">{{ t.label }}</span>
          </div>
        </div>
      </div>

      <div class="admin-chart-card">
        <div class="chart-header">
          <h3>🥧 商机分类占比</h3>
        </div>
        <div class="donut-wrap">
          <div class="donut" :style="{ background: categoryShare.gradient }">
            <div class="donut-inner">
              <div class="dn">{{ categoryShare.total }}</div>
              <div class="dl">商机总数</div>
            </div>
          </div>
          <div class="legend-list">
            <div v-for="s in categoryShare.segs" :key="s.name" class="legend-row">
              <div class="legend-dot" :style="{ background: s.color }"></div>
              <div class="legend-name">{{ s.name }}</div>
              <div class="legend-val">{{ s.pct }}%</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 热门商机 + 最近订单 -->
    <div class="admin-chart-row">
      <div class="admin-chart-card">
        <div class="chart-header">
          <h3>🔥 热门商机 TOP {{ topOpps.length }}</h3>
          <a style="font-size: 12px; color: var(--bf-primary); text-decoration: none; cursor: pointer" @click="router.push('/opportunities')">管理商机库 →</a>
        </div>
        <div class="rank-list">
          <div v-for="(t, i) in topOpps" :key="t.name" class="rank-item">
            <div class="rank-num" :class="i === 0 ? 'top1' : i === 1 ? 'top2' : i === 2 ? 'top3' : ''">{{ i + 1 }}</div>
            <div class="rank-name">{{ t.name }}</div>
            <div class="rank-bar"><div class="rank-bar-fill" :style="{ width: `${Math.max(10, Math.round((t.heat / maxHeat) * 100))}%` }"></div></div>
            <div class="rank-count">{{ t.heat }}分</div>
          </div>
        </div>
      </div>

      <div class="admin-chart-card">
        <div class="chart-header">
          <h3>📋 最近订单</h3>
          <a style="font-size: 12px; color: var(--bf-primary); text-decoration: none; cursor: pointer" @click="router.push('/orders')">查看全部 →</a>
        </div>
        <table class="admin-table" style="margin-top: 8px">
          <thead>
            <tr>
              <th>用户</th>
              <th>商品</th>
              <th>金额</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="o in recentOrders" :key="o.id">
              <td>
                <div class="user-cell">
                  <div class="user-avatar-sm">{{ o.userPhone.slice(-4, -2) }}</div>
                  <div>
                    <div class="user-name">{{ o.userPhone }}</div>
                    <div class="user-sub">{{ o.id }}</div>
                  </div>
                </div>
              </td>
              <td>{{ o.planName }}</td>
              <td style="color: var(--bf-ok); font-weight: 600">¥{{ o.amountYuan }}</td>
              <td><span class="tag" :class="orderTag(o)">{{ orderTagText(o) }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- V5.0 第 8 章 运营自动化：异常告警 + 昨日数据日报 -->
    <div class="admin-chart-row">
      <div class="admin-chart-card">
        <div class="chart-header">
          <h3>
            🚨 异常告警
            <span v-if="alerts.length" class="tag tag-danger" style="margin-left: 8px">{{ unreadAlerts }} 条未读</span>
          </h3>
          <div style="display: flex; gap: 10px; align-items: center">
            <a style="font-size: 12px; color: var(--bf-primary); cursor: pointer" @click="onScanAlerts">立即巡检</a>
            <a style="font-size: 12px; color: var(--bf-primary); cursor: pointer" @click="onReadAllAlerts">全部已读</a>
          </div>
        </div>
        <div v-if="!alerts.length" class="bf-muted" style="font-size: 13px; padding: 12px 0">
          暂无异常订单，交付链路健康（每 5 分钟自动巡检一次）。
        </div>
        <div v-else class="alert-list">
          <div
            v-for="a in alerts"
            :key="a.id"
            class="alert-item"
            :class="a.level === 'danger' ? 'alert-item--danger' : 'alert-item--warn'"
          >
            <div class="alert-title">{{ a.title }}</div>
            <div class="alert-sub">{{ a.content }}</div>
            <div class="alert-meta">
              <span>{{ a.createdAt }}</span>
              <a
                v-if="a.relatedType === 'order'"
                style="color: var(--bf-primary); cursor: pointer"
                @click="router.push('/orders')"
              >
                去处理 →
              </a>
            </div>
          </div>
        </div>
      </div>

      <div class="admin-chart-card">
        <div class="chart-header">
          <h3>📰 昨日数据日报</h3>
          <div style="display: flex; gap: 10px; align-items: center">
            <span class="tag" :class="report?.pushStatus === 'sent' ? 'tag-ok' : 'tag-warn'">
              {{ pushStatusText }}
            </span>
            <a style="font-size: 12px; color: var(--bf-primary); cursor: pointer" @click="onGenerateReport">补生成</a>
          </div>
        </div>
        <template v-if="report">
          <div class="report-grid">
            <div class="report-cell">
              <div class="rc-label">营收</div>
              <div class="rc-value ok">¥{{ report.revenueLabel }}</div>
            </div>
            <div class="report-cell">
              <div class="rc-label">订单</div>
              <div class="rc-value">{{ report.orderCount }} 单</div>
            </div>
            <div class="report-cell">
              <div class="rc-label">新增用户</div>
              <div class="rc-value">{{ report.newUsers }} 人</div>
            </div>
            <div class="report-cell">
              <div class="rc-label">退款</div>
              <div class="rc-value">¥{{ report.refundLabel }}</div>
            </div>
            <div class="report-cell">
              <div class="rc-label">AI 成本</div>
              <div class="rc-value">{{ report.aiCostLabel }}</div>
            </div>
            <div class="report-cell">
              <div class="rc-label">净现金流</div>
              <div class="rc-value" :class="report.netCashCents >= 0 ? 'ok' : 'danger'">
                ¥{{ report.netCashLabel }}
              </div>
            </div>
          </div>
          <pre class="report-content">{{ report.content }}</pre>
          <div class="bf-muted" style="font-size: 12px">
            统计日 {{ report.reportDate }} · 每日 9 点自动生成；未配置推送 webhook 时仅落库不外部推送
          </div>
        </template>
        <div v-else class="bf-muted" style="font-size: 13px; padding: 12px 0">
          日报尚未生成，点「补生成」立即生成昨日日报。
        </div>
      </div>
    </div>

    <div class="bf-note bf-muted">
      口径：付费转化率 = 支付成功人数 ÷ 诊断完成人数；交付成功率 = 成功生成 10 件订单数 ÷ 已支付订单数（与第 10 章一致）；数据延迟 ≤ 5 分钟；打开后台 3 秒内可见当日核心数据（M11-05）· {{ refreshAt }}
    </div>
  </div>
</template>
