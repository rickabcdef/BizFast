<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getFunnel, getGrowth, type FunnelData, type GrowthData } from '@/api/adminApi'

const loading = ref(true)
const period = ref<'day' | 'week' | 'month'>('month')
const funnel = ref<FunnelData | null>(null)
const growth = ref<GrowthData | null>(null)

const load = async () => {
  loading.value = true
  try {
    const [f, g] = await Promise.all([getFunnel(period.value), getGrowth()])
    funnel.value = f
    growth.value = g
  } finally {
    loading.value = false
  }
}

onMounted(load)

const pick = async (p: 'day' | 'week' | 'month') => {
  period.value = p
  funnel.value = await getFunnel(p)
}

const PERIODS = [
  { value: 'day', label: '今日' },
  { value: 'week', label: '近 7 天' },
  { value: 'month', label: '近 30 天' }
] as const

const summary = computed(() => growth.value?.summary)
const kFactor = computed(() => summary.value?.kFactor ?? 0)
const firstOrderRate = computed(() => funnel.value?.overallConversion ?? 0)

/** LTV / CAC：单次客单价 29.9 元 ÷ 裂变获客成本，衡量是否值得投放 */
const ltvCac = computed(() => {
  const cac = (summary.value?.fissionCacCents ?? 0) / 100
  if (!cac) return '—'
  return (29.9 / cac).toFixed(2)
})

const pct = (v?: number | null) => `${((v || 0) * 100).toFixed(1)}%`

/** 漏斗条宽度（以首步为 100%，其余按占比，最小 6% 保证可见） */
const barWidth = (v: number) => {
  const top = funnel.value?.steps?.[0]?.value || 0
  if (!top) return '6%'
  return `${Math.max(6, Math.round((v / top) * 100))}%`
}

const CHANNEL_LABEL: Record<string, string> = {
  微信好友: '微信好友',
  朋友圈: '朋友圈',
  抖音: '抖音',
  小红书: '小红书',
  复制链接: '复制链接',
  保存图片: '保存图片',
  direct: '直接访问'
}
</script>

<template>
  <div v-loading="loading">
    <div class="alert-card alert-success" v-if="funnel && growth">
      <span style="font-size: 18px">✅</span>
      <div>
        {{ PERIODS.find((p) => p.value === period)?.label }}首单转化率
        <strong>{{ pct(firstOrderRate) }}</strong>
        （存活线 3%）；K 因子 <strong>{{ kFactor }}</strong>
        {{ kFactor >= 1 ? '，已进入自增长飞轮' : '（K&gt;1 即自增长飞轮）' }}。
      </div>
    </div>

    <!-- 4 个核心 KPI -->
    <div class="admin-stats" v-if="growth">
      <div class="admin-stat-card">
        <div class="stat-icon" style="background: rgba(0, 180, 42, 0.15)">🎯</div>
        <div class="stat-label">首单转化率</div>
        <div class="stat-value">{{ pct(firstOrderRate) }}</div>
        <div class="stat-trend" :style="{ color: firstOrderRate >= 0.03 ? 'var(--bf-ok)' : 'var(--bf-warn)' }">
          {{ firstOrderRate >= 0.03 ? '✓ 达标（≥3%）' : '⚠️ 低于存活线 3%' }}
        </div>
      </div>
      <div class="admin-stat-card">
        <div class="stat-icon" style="background: rgba(123, 97, 255, 0.15)">🔗</div>
        <div class="stat-label">K 因子（病毒系数）</div>
        <div class="stat-value">{{ kFactor }}</div>
        <div class="stat-trend">每 100 个用户带来 {{ Math.round(kFactor * 100) }} 个新用户</div>
      </div>
      <div class="admin-stat-card">
        <div class="stat-icon" style="background: rgba(22, 93, 255, 0.15)">💸</div>
        <div class="stat-label">裂变获客成本</div>
        <div class="stat-value">¥{{ summary?.fissionCacLabel || '0.00' }}</div>
        <div class="stat-trend">邀请付费用户 {{ summary?.paidInvitees || 0 }} 人</div>
      </div>
      <div class="admin-stat-card">
        <div class="stat-icon" style="background: rgba(255, 125, 0, 0.15)">⚖️</div>
        <div class="stat-label">LTV / CAC</div>
        <div class="stat-value">{{ ltvCac }}</div>
        <div class="stat-trend" :style="{ color: Number(ltvCac) >= 3 ? 'var(--bf-ok)' : '' }">
          {{ Number(ltvCac) >= 3 ? '✓ 高于投放门槛 3' : '按单次客单价 29.9 元估算' }}
        </div>
      </div>
    </div>

    <div class="admin-chart-row" style="margin-top: 16px">
      <!-- 转化漏斗 -->
      <div class="admin-chart-card">
        <div class="chart-header">
          <h3>转化漏斗</h3>
          <div class="chart-tabs">
            <span
              v-for="p in PERIODS"
              :key="p.value"
              class="chart-tab"
              :class="{ 'is-active': period === p.value }"
              @click="pick(p.value)"
              >{{ p.label }}</span
            >
          </div>
        </div>
        <div
          v-for="s in funnel?.steps || []"
          :key="s.step"
          style="margin-bottom: 14px"
        >
          <div
            style="display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 6px"
          >
            <span style="color: var(--bf-text-2)">{{ s.label }}</span>
            <span>
              <strong>{{ s.value }}</strong>
              <span class="bf-muted" style="margin-left: 8px">{{ pct(s.rateFromTop) }}</span>
            </span>
          </div>
          <div
            style="height: 24px; border-radius: 6px; background: rgba(255, 255, 255, 0.06); overflow: hidden"
          >
            <div
              :style="{
                width: barWidth(s.value),
                height: '100%',
                display: 'flex',
                alignItems: 'center',
                paddingLeft: '8px',
                fontSize: '11px',
                color: '#fff',
                background: s.dropAlert
                  ? 'linear-gradient(90deg, #F53F3F, #FF7D00)'
                  : 'linear-gradient(90deg, #165DFF, #7B61FF)'
              }"
            >
              <span v-if="s.rateFromPrev !== null">{{ pct(s.rateFromPrev) }} 转化</span>
            </div>
          </div>
          <div v-if="s.dropAlert" class="bf-muted" style="margin-top: 4px; color: var(--bf-warn)">
            ⚠️ 流失最大的一步，建议检查该环节的引导与加载速度
          </div>
        </div>
        <div class="bf-muted" style="margin-top: 6px">{{ funnel?.notice }}</div>
      </div>

      <!-- 裂变数据 -->
      <div class="admin-chart-card">
        <div class="chart-header"><h3>裂变数据</h3></div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px">
          <div class="admin-stat-card" style="padding: 16px">
            <div class="stat-label" style="font-size: 12px">转发 / 保存卡片</div>
            <div class="stat-value" style="font-size: 22px">{{ summary?.shares || 0 }} 次</div>
          </div>
          <div class="admin-stat-card" style="padding: 16px">
            <div class="stat-label" style="font-size: 12px">带来新用户</div>
            <div class="stat-value" style="font-size: 22px; color: var(--bf-ok)">
              {{ summary?.registers || 0 }} 人
            </div>
          </div>
          <div class="admin-stat-card" style="padding: 16px">
            <div class="stat-label" style="font-size: 12px">裂变带来付费</div>
            <div class="stat-value" style="font-size: 22px; color: var(--bf-ok)">
              {{ summary?.pays || 0 }} 单
            </div>
          </div>
          <div class="admin-stat-card" style="padding: 16px">
            <div class="stat-label" style="font-size: 12px">发起邀请的用户</div>
            <div class="stat-value" style="font-size: 22px">{{ summary?.uniqueInviters || 0 }} 人</div>
          </div>
        </div>

        <div style="margin-top: 16px">
          <div class="bf-muted" style="margin-bottom: 8px">转发渠道分布</div>
          <el-table :data="growth?.rows || []" style="width: 100%" size="small">
            <el-table-column label="渠道" min-width="120">
              <template #default="{ row }">{{ CHANNEL_LABEL[row.channel] || row.channel }}</template>
            </el-table-column>
            <el-table-column prop="clicks" label="转发次数" width="110" />
          </el-table>
          <div v-if="!(growth?.rows || []).length" class="bf-muted" style="padding: 8px 0">
            暂无转发记录
          </div>
        </div>
        <div class="bf-muted" style="margin-top: 10px; line-height: 1.8">
          裂变是一人公司最便宜的获客方式（CAC 可压到 1—2 元/人）。
          K 因子 = 平均每个用户带来的新用户数，K &gt; 1 即为自增长飞轮。
        </div>
      </div>
    </div>
  </div>
</template>
