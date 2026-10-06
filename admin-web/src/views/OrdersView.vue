<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getAdminOrders,
  processRefund,
  exportCsv,
  ORDER_ABNORMAL_LABEL,
  type AdminOrder,
  type AdminSession
} from '@/api/adminApi'
import { useAuthStore } from '@/store/auth'

const auth = useAuthStore()
const rows = ref<AdminOrder[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const keyword = ref('')
const status = ref('')
const channel = ref('')
const onlyAbnormal = ref(false)
const loading = ref(false)

const STATUS_TABS = [
  { value: '', label: '全部订单' },
  { value: 'paid', label: '已支付' },
  { value: 'generating', label: '生成中' },
  { value: 'delivered', label: '已交付' },
  { value: 'refunded', label: '已退款' },
  { value: 'closed', label: '已关闭' }
]

const CHANNEL_FILTERS = [
  { value: '', label: '全部支付方式' },
  { value: 'wechat', label: '微信支付' },
  { value: 'alipay', label: '支付宝' }
]

const load = async () => {
  loading.value = true
  try {
    const d = await getAdminOrders({ page: page.value, pageSize, status: status.value, keyword: keyword.value, abnormal: onlyAbnormal.value, channel: channel.value })
    rows.value = d.items
    total.value = d.total
  } finally {
    loading.value = false
  }
}

onMounted(load)

const doSearch = () => {
  page.value = 1
  void load()
}

// ---- 订单统计卡（对齐切图 15 页，来自 Mock 聚合） ----
const stats = computed(() => {
  const all = rows.value
  const todayOrders = all.filter((o) => o.status !== 'pending').length
  const todayRevenue = Math.round(all.reduce((s, o) => s + o.amountYuan, 0) * 10) / 10
  const generating = all.filter((o) => o.status === 'generating').length
  const refunded = all.filter((o) => o.status === 'refunded').length
  const refundAmount = Math.round(all.filter((o) => o.status === 'refunded').reduce((s, o) => s + o.amountYuan, 0) * 10) / 10
  return [
    { label: '今日订单', value: String(todayOrders) },
    { label: '今日营收', value: `¥${todayRevenue}`, color: 'var(--bf-ok)' },
    { label: '生成中', value: String(generating), color: 'var(--bf-warn)' },
    { label: '已退款', value: String(refunded) },
    { label: '退款金额', value: `¥${refundAmount}`, color: 'var(--bf-danger)' }
  ]
})

const abnormalCount = computed(() => rows.value.filter((o) => o.abnormal).length)
const rowClass = ({ row }: { row: AdminOrder }) => (row.abnormal ? 'bf-abnormal' : '')

const doExport = () => {
  exportCsv(
    `生意快启_订单对账表_${Date.now()}.csv`,
    ['订单号', '用户', '套餐', '金额', '状态', '渠道', '下单时间', '支付时间', '异常标记', '退款申请'],
    rows.value.map((o) => [o.id, o.userPhone, o.planName, o.amountYuan, o.statusLabel, o.channel, o.createdAt, o.paidAt || '', o.abnormal ? ORDER_ABNORMAL_LABEL[o.abnormalType || ''] || '异常' : '否', o.refundRequested ? o.refundReason || '是' : '否'])
  )
  ElMessage.success('对账表已导出')
}

const doRefund = async (o: AdminOrder, action: 'approve' | 'reject') => {
  try {
    if (action === 'reject') {
      const { value } = await ElMessageBox.prompt('请输入驳回原因', '驳回退款', {
        confirmButtonText: '确认驳回',
        cancelButtonText: '取消'
      })
      const r = await processRefund(auth.session as AdminSession, o.id, action, value)
      ElMessage.success(r.message)
    } else {
      await ElMessageBox.confirm(`确认同意退款 ¥${o.amountYuan}（24h 内原路到账）？`, '同意退款', { type: 'warning', confirmButtonText: '确认退款', cancelButtonText: '取消' })
      const r = await processRefund(auth.session as AdminSession, o.id, action)
      ElMessage.success(r.message)
    }
    void load()
  } catch (e: any) {
    if (e?.message) ElMessage.error(e.message)
  }
}

// 渠道 tag
const channelTag = (o: AdminOrder) => (o.channel === '微信支付' ? 'tag-green' : 'tag-blue')
const channelText = (o: AdminOrder) => (o.channel === '微信支付' ? '微信' : o.channel === '支付宝' ? '支付宝' : o.channel)
// 交付状态
const deliveryTag = (o: AdminOrder) => {
  if (o.abnormal) return 'tag-red'
  if (o.status === 'delivered' || o.status === 'refunded') return 'tag-green'
  if (o.status === 'generating') return 'tag-orange'
  return 'tag-gray'
}
const deliveryText = (o: AdminOrder) => {
  if (o.abnormal) return `⚠️ 未交付`
  if (o.status === 'delivered') return '✓ 已交付'
  if (o.status === 'generating') return '⏳ 生成中'
  if (o.status === 'refunded') return '—'
  return o.statusLabel
}
</script>

<template>
  <div>
    <!-- 异常告警（对齐切图 15 页 alert-danger + 一键处理异常） -->
    <div v-if="abnormalCount > 0" class="alert-card alert-danger">
      <span style="font-size: 18px">🚨</span>
      <div>
        <strong>异常订单告警：</strong>
        发现 <strong>{{ abnormalCount }} 笔已支付未交付 / 支付回调缺失</strong>订单，
        请立即处理以避免用户投诉！
        <el-button size="small" style="margin-left: 12px" type="danger" plain @click="onlyAbnormal = true; status = ''; page = 1; void load()">一键处理异常</el-button>
      </div>
    </div>

    <!-- Tab 切换 -->
    <div class="config-tabs" style="margin-bottom: 16px">
      <button
        v-for="t in STATUS_TABS"
        :key="t.value"
        class="config-tab"
        :class="{ 'is-active': status === t.value }"
        @click="status = t.value; page = 1; void load()"
      >
        {{ t.label }}
      </button>
      <button class="config-tab" :class="{ 'is-active': onlyAbnormal }" style="color: var(--bf-danger)" @click="onlyAbnormal = !onlyAbnormal; page = 1; void load()">
        仅异常 <span v-if="abnormalCount > 0">({{ abnormalCount }})</span>
      </button>
    </div>

    <!-- 筛选栏 -->
    <div class="admin-filter">
      <el-input v-model="keyword" placeholder="🔍 搜索订单号 / 用户手机号" style="flex: 2; min-width: 200px" clearable @keyup.enter="doSearch" />
      <el-select v-model="channel" style="width: 150px" @change="doSearch">
        <el-option v-for="c in CHANNEL_FILTERS" :key="c.value" :label="c.label" :value="c.value" />
      </el-select>
      <el-button type="primary" @click="doSearch">🔍 查询</el-button>
      <div style="flex: 1" />
      <span class="bf-muted">共 {{ total }} 笔订单</span>
      <el-button class="admin-btn admin-btn-outline admin-btn-sm" @click="doExport">📊 对账单导出</el-button>
    </div>

    <!-- 订单统计 -->
    <div class="admin-stats" style="grid-template-columns: repeat(5, 1fr); margin-bottom: 20px">
      <div v-for="s in stats" :key="s.label" class="admin-stat-card" style="padding: 14px 18px">
        <div class="stat-label" style="font-size: 12px; margin-bottom: 4px">{{ s.label }}</div>
        <div class="stat-value" style="font-size: 22px" :style="s.color ? { color: s.color } : {}">{{ s.value }}</div>
      </div>
    </div>

    <!-- 订单表格 -->
    <div class="admin-table-wrap">
      <el-table v-loading="loading" :data="rows" :row-class-name="rowClass" style="width: 100%">
        <el-table-column label="订单号" width="140">
          <template #default="{ row }">
            <span style="font-family: monospace; font-size: 12px">{{ row.id }}</span>
          </template>
        </el-table-column>
        <el-table-column label="用户" width="150">
          <template #default="{ row }">
            <div class="user-cell">
              <div class="user-avatar-sm">{{ row.userPhone.slice(-4, -2) }}</div>
              <div>
                <div class="user-name">{{ row.userPhone }}</div>
                <div class="user-sub">{{ row.userId }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="planName" label="商品" width="120" />
        <el-table-column label="金额" width="90">
          <template #default="{ row }">
            <span :style="{ color: row.status === 'refunded' ? 'var(--bf-text-3)' : 'var(--bf-ok)', fontWeight: 600, textDecoration: row.status === 'refunded' ? 'line-through' : 'none' }">
              ¥{{ row.amountYuan.toFixed(2) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="支付方式" width="90">
          <template #default="{ row }">
            <span class="tag" :class="channelTag(row)">{{ channelText(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="支付时间" width="150">
          <template #default="{ row }">{{ row.paidAt || '—' }}</template>
        </el-table-column>
        <el-table-column label="交付状态" width="110">
          <template #default="{ row }">
            <span class="tag" :class="deliveryTag(row)">{{ deliveryText(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <span class="tag" :class="row.abnormal ? 'tag-red' : row.status === 'delivered' || row.status === 'refunded' ? 'tag-green' : row.status === 'generating' || row.status === 'paid' ? 'tag-orange' : 'tag-gray'">
              {{ row.abnormal ? '异常' : row.statusLabel }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <template v-if="row.refundRequested && ['paid', 'generating', 'delivered'].includes(row.status)">
              <a class="action-link" style="color: var(--bf-ok)" @click="doRefund(row, 'approve')">同意退款</a>
              <a class="action-link danger" @click="doRefund(row, 'reject')">驳回</a>
            </template>
            <span v-else class="bf-muted">—</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination">
        <div>共 <strong style="color: var(--bf-text)">{{ total }}</strong> 条订单 · 异常 <strong style="color: var(--bf-danger)">{{ abnormalCount }}</strong> 笔</div>
        <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total" layout="prev, pager, next" background small @current-change="load" />
      </div>
    </div>
  </div>
</template>
