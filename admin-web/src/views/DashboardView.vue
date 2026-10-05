<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getAdminDashboard, type DashboardKpis, type DashboardTrend, type TrendGranularity } from '@/api/adminApi'

const granularity = ref<TrendGranularity>('day')
const kpis = ref<DashboardKpis | null>(null)
const trend = ref<DashboardTrend[]>([])
const refreshAt = ref('')
const loading = ref(true)

const load = async (g: TrendGranularity) => {
  loading.value = true
  try {
    const d = await getAdminDashboard(g)
    kpis.value = d.kpis
    trend.value = d.trend
    refreshAt.value = d.refreshAt
  } finally {
    loading.value = false
  }
}

onMounted(() => load('day'))

const cards = () =>
  kpis.value
    ? [
        { label: '诊断完成数', value: String(kpis.value.diagnoseCount), unit: '人' },
        { label: '付费单数', value: String(kpis.value.payCount), unit: '单' },
        { label: '总收入', value: `¥${kpis.value.revenueYuan}`, unit: '' },
        { label: '付费转化率', value: kpis.value.conversionRate, unit: '' },
        { label: '交付成功率', value: kpis.value.packageDoneRate, unit: '' },
        { label: '退款率', value: kpis.value.refundRate, unit: '' },
        { label: '客单价', value: `¥${kpis.value.avgOrderYuan}`, unit: '' }
      ]
    : []

const maxOrders = () => Math.max(1, ...trend.value.map((t) => t.orders))
const maxRevenue = () => Math.max(1, ...trend.value.map((t) => t.revenue))
</script>

<template>
  <div>
    <div class="bf-kpis">
      <div v-for="c in cards()" :key="c.label" class="bf-kpi">
        <div class="bf-kpi__label">{{ c.label }}</div>
        <div class="bf-kpi__value">
          {{ c.value }}<span class="bf-kpi__unit">{{ c.unit }}</span>
        </div>
      </div>
    </div>

    <div class="bf-card">
      <div class="bf-row" style="justify-content: space-between">
        <div class="bf-card__title">经营趋势（订单数 / 收入）</div>
        <div class="bf-filter">
          <span
            v-for="g in (['day', 'week', 'month'] as TrendGranularity[])"
            :key="g"
            class="bf-filter__seg"
            :class="{ 'is-active': granularity === g }"
            @click="granularity = g; load(g)"
          >
            {{ g === 'day' ? '按日' : g === 'week' ? '按周' : '按月' }}
          </span>
        </div>
      </div>
      <div v-if="loading" style="padding: 40px; text-align: center; color: var(--bf-text-3)">加载中…</div>
      <div v-else class="bf-trend">
        <div v-for="t in trend" :key="t.label" class="bf-trend__col">
          <div class="bf-trend__bars">
            <div class="bf-trend__bar bf-trend__bar--rev" :style="{ height: `${Math.max(6, Math.round((t.revenue / maxRevenue()) * 110))}px` }" />
            <div class="bf-trend__bar bf-trend__bar--ord" :style="{ height: `${Math.max(6, Math.round((t.orders / maxOrders()) * 110))}px` }" />
          </div>
          <div class="bf-trend__date">{{ t.label }}</div>
          <div class="bf-trend__num">{{ t.orders }} 单 / ¥{{ t.revenue }}</div>
        </div>
      </div>
      <div class="bf-note bf-muted">
        口径：付费转化率 = 支付成功人数 ÷ 诊断完成人数；交付成功率 = 成功生成 10 件订单数 ÷ 已支付订单数（与第 10 章一致）；数据延迟 ≤ 5 分钟；打开后台 3 秒内可见当日核心数据（M11-05）。
      </div>
    </div>
  </div>
</template>
