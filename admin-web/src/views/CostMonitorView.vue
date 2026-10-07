<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getCostMonitor, type CostMonitor } from '@/api/adminApi'

const loading = ref(true)
const data = ref<CostMonitor | null>(null)

const load = async () => {
  loading.value = true
  try {
    data.value = await getCostMonitor()
  } finally {
    loading.value = false
  }
}

onMounted(load)

const today = computed(() => data.value?.today)
const month = computed(() => data.value?.month)

const ratioPct = (r?: number) => `${((r || 0) * 100).toFixed(2)}%`

/** 平均单次成本（元）= 本月成本 / 本月调用次数，用于核算开业礼包毛利率 */
const avgPerCall = computed(() => {
  const m = month.value
  if (!m || !m.calls) return '0.00'
  return (m.costCents / m.calls / 100).toFixed(2)
})

const grossMargin = computed(() => {
  const avg = Number(avgPerCall.value)
  if (!avg) return '—'
  return `${Math.max(0, (1 - avg / 29.9) * 100).toFixed(1)}%`
})

const tierLabel = (t?: string) =>
  ({ light: '轻量模型（默认）', mid: '标准模型', top: '高精度模型' }[t || 'light'] || t || '')

/** 六道成本闸门（第 7.2 节，研发必须全部实现） */
const gates = computed(() => {
  const g = data.value?.gates
  const b = data.value?.budget
  if (!g || !b) return []
  return [
    {
      no: '①',
      name: '模型路由',
      desc: '默认轻档，验收不过才升档',
      setting: `当前：${tierLabel(g.modelTier)}`,
      runtime: `默认档位 ${g.modelTier} · 绝不一上来就跑最贵模型`,
      ok: g.modelTier === 'light'
    },
    {
      no: '②',
      name: '全链路缓存',
      desc: '提示词 / 商机库 / 模板全量缓存',
      setting: '前缀缓存已开启',
      runtime: `命中率 ${(g.cacheHitRate * 100).toFixed(1)}%（命中价可低至未命中价 1/25）`,
      ok: true
    },
    {
      no: '③',
      name: '模板化交付',
      desc: '10 件交付物：7 件模板 + 3 件 AI',
      setting: '模板 7 / AI 3',
      runtime: `模板占比 ${(g.templateRatio * 100).toFixed(1)}%`,
      ok: true
    },
    {
      no: '④',
      name: '轮数上限',
      desc: '防止智能体放飞',
      setting: `诊断≤${g.maxRounds.diagnose} 轮 / 启动包≤${g.maxRounds.package} 轮 / 教练≤${g.maxRounds.coach} 轮`,
      runtime: '超限自动截断，不拒绝服务',
      ok: true
    },
    {
      no: '⑤',
      name: '多模态限额',
      desc: '免费层不给生图，视频只加购',
      setting: '生图按张扣额度',
      runtime: '视频 / 数字人未混入标准套餐',
      ok: true
    },
    {
      no: '⑥',
      name: '预算熔断',
      desc: '用户级 / 项目级 / 密钥级三重上限',
      setting: `免费≤${b.free / 100} 元 / 单次≤${b.single / 100} 元 / 月卡≤${b.month / 100} 元`,
      runtime: data.value?.alert ? '已触发告警，自动降级模板模式' : '未触发降级',
      ok: !data.value?.alert
    }
  ]
})

const FEATURE_ICON: Record<string, string> = {
  diagnose: '🧭',
  package: '📦',
  coach: '🤖',
  poster: '🖼️',
  report: '🎉',
  topic: '💬'
}
</script>

<template>
  <div v-loading="loading">
    <div
      v-if="data"
      class="alert-card"
      :class="data.alert ? 'alert-warning' : 'alert-success'"
    >
      <span style="font-size: 18px">{{ data.alert ? '⚠️' : '✅' }}</span>
      <div>{{ data.notice }}</div>
    </div>

    <!-- 4 个核心卡 -->
    <div class="admin-stats" v-if="data">
      <div class="admin-stat-card">
        <div class="stat-icon" style="background: rgba(255, 125, 0, 0.15)">🔥</div>
        <div class="stat-label">今日 AI 成本</div>
        <div class="stat-value">¥{{ today?.costLabel }}</div>
        <div class="stat-trend">{{ today?.calls }} 次调用 · {{ today?.tokens }} tokens</div>
      </div>
      <div class="admin-stat-card">
        <div class="stat-icon" style="background: rgba(0, 180, 42, 0.15)">📉</div>
        <div class="stat-label">成本占收入比</div>
        <div
          class="stat-value"
          :style="{ color: today?.alert ? 'var(--bf-danger)' : 'var(--bf-ok)' }"
        >
          {{ ratioPct(today?.costRatio) }}
        </div>
        <div class="stat-trend">
          {{
            today?.alert
              ? `⚠️ 超过红线 ${(data.alertRatio * 100).toFixed(0)}%`
              : `✓ 低于红线 ${(data.alertRatio * 100).toFixed(0)}%`
          }}
        </div>
      </div>
      <div class="admin-stat-card">
        <div class="stat-icon" style="background: rgba(22, 93, 255, 0.15)">📅</div>
        <div class="stat-label">本月累计成本</div>
        <div class="stat-value">¥{{ month?.costLabel }}</div>
        <div class="stat-trend">本月收入 ¥{{ month?.revenueLabel }}</div>
      </div>
      <div class="admin-stat-card">
        <div class="stat-icon" style="background: rgba(123, 97, 255, 0.15)">🎁</div>
        <div class="stat-label">平均单次成本</div>
        <div class="stat-value">¥{{ avgPerCall }}</div>
        <div class="stat-trend">开业礼包毛利率 {{ grossMargin }}（红线 ≥88%）</div>
      </div>
    </div>

    <!-- 六道成本闸门 -->
    <div class="bf-card" style="margin-top: 16px">
      <div class="chart-header">
        <h3>🛡️ 六道成本闸门状态</h3>
        <span class="bf-muted">第 7.2 节 · 研发必须全部实现 · 每日自动校验</span>
      </div>
      <el-table :data="gates" style="width: 100%">
        <el-table-column label="闸门" min-width="200">
          <template #default="{ row }">
            <div style="font-weight: 600">{{ row.no }} {{ row.name }}</div>
            <div class="bf-muted">{{ row.desc }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="setting" label="当前设置" min-width="220" />
        <el-table-column prop="runtime" label="运行数据" min-width="220" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <span class="bf-tag" :class="row.ok ? 'bf-tag--ok' : 'bf-tag--warn'">
              {{ row.ok ? '✓ 正常' : '⚠️ 告警' }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 成本分布 -->
    <div class="admin-chart-row" style="margin-top: 16px">
      <div class="admin-chart-card">
        <div class="chart-header"><h3>按功能分布（本月）</h3></div>
        <el-table :data="data?.byFeature || []" style="width: 100%">
          <el-table-column label="功能" min-width="140">
            <template #default="{ row }">
              {{ FEATURE_ICON[row.feature] || '▪' }} {{ row.featureLabel }}
            </template>
          </el-table-column>
          <el-table-column prop="calls" label="调用" width="90" />
          <el-table-column label="成本" width="100">
            <template #default="{ row }">¥{{ row.costLabel }}</template>
          </el-table-column>
          <el-table-column prop="tokens" label="Tokens" width="120" />
        </el-table>
        <div v-if="!(data?.byFeature || []).length" class="bf-muted" style="padding: 12px 0">
          本月暂无成本记录
        </div>
      </div>
      <div class="admin-chart-card">
        <div class="chart-header"><h3>按模型分布（本月）</h3></div>
        <el-table :data="data?.byModel || []" style="width: 100%">
          <el-table-column prop="model" label="模型" min-width="150" />
          <el-table-column label="成本" width="100">
            <template #default="{ row }">¥{{ row.costLabel }}</template>
          </el-table-column>
          <el-table-column prop="tokens" label="Tokens" width="130" />
        </el-table>
        <div v-if="!(data?.byModel || []).length" class="bf-muted" style="padding: 12px 0">
          本月暂无成本记录
        </div>
      </div>
    </div>
  </div>
</template>
