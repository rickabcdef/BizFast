<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getAdminUsers,
  getAdminUserDetail,
  exportCsv,
  type AdminUser,
  type AdminOrder
} from '@/api/adminApi'

const rows = ref<AdminUser[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const keyword = ref('')
const member = ref('')
const source = ref('')
const loading = ref(false)
const detail = ref<{ user: AdminUser; orders: AdminOrder[]; packages: any[] } | null>(null)
const detailOpen = ref(false)

const MEMBER_FILTERS = [
  { value: '', label: '全部会员等级' },
  { value: 'none', label: '免费用户' },
  { value: 'single', label: '开业礼包' },
  { value: 'month', label: 'AI 合伙人月卡' },
  { value: 'year', label: '创业陪跑年卡' }
]

// M0-04（V5.0）：来源渠道 = 邀请注册 > 埋点渠道 > 自然流量，必须与后端产出的标签逐字一致
const SOURCE_FILTERS = [
  { value: '', label: '来源渠道（全部）' },
  { value: '邀请注册', label: '邀请注册' },
  { value: '自然流量', label: '自然流量' },
  { value: '商机详情页', label: '商机详情页' },
  { value: '分享卡片', label: '分享卡片' },
  { value: '付费弹窗', label: '付费弹窗' }
]

const load = async () => {
  loading.value = true
  try {
    const d = await getAdminUsers({ page: page.value, pageSize, keyword: keyword.value, memberStatus: member.value, source: source.value })
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

const doReset = () => {
  keyword.value = ''
  member.value = ''
  source.value = ''
  page.value = 1
  void load()
}

// ---- 用户统计小卡（对齐切图 14 页，数据来自 Mock 聚合） ----
const stats = computed(() => {
  const all = rows.value.length + (total.value > pageSize ? total.value - pageSize : 0)
  const free = rows.value.filter((u) => u.memberStatus === 'none').length
  const month = rows.value.filter((u) => u.memberStatus === 'month').length
  const year = rows.value.filter((u) => u.memberStatus === 'year').length
  return [
    { label: '当前列表', value: String(all) },
    { label: '免费用户', value: String(free) },
    { label: 'AI 合伙人月卡', value: String(month), color: 'var(--bf-primary)' },
    { label: '创业陪跑年卡', value: String(year), color: 'var(--bf-primary-2)' }
  ]
})

const doExport = () => {
  const ok = exportCsv(
    `生意快启_用户列表_${Date.now()}.csv`,
    ['用户ID', '手机号', '昵称', '城市', '会员状态', '订单数', '消费总额', '来源渠道', '注册时间', '风控标记'],
    rows.value.map((u) => [u.id, u.phone, u.nickname, u.city, u.memberLabel, u.orderCount, u.totalSpendYuan, u.source, u.createdAt, u.riskFlag ? '是' : '否'])
  )
  ElMessage.success(ok ? '已导出 CSV' : '导出失败')
}

const openDetail = async (u: AdminUser) => {
  detail.value = await getAdminUserDetail(u.id)
  detailOpen.value = true
}

// 会员等级 tag（对齐切图 tag-purple/blue/gray/orange）
const memberTag = (u: AdminUser) => {
  if (u.memberStatus === 'year') return 'tag-purple'
  if (u.memberStatus === 'month') return 'tag-blue'
  if (u.memberStatus === 'single') return 'tag-orange'
  return 'tag-gray'
}
const memberLabel = (u: AdminUser) => {
  const icon = u.memberStatus === 'year' ? '👑 ' : u.memberStatus === 'month' ? '📅 ' : u.memberStatus === 'single' ? '🎁 ' : ''
  return icon + u.memberLabel
}
const statusTag = (u: AdminUser) => (u.riskFlag ? 'tag-orange' : 'tag-green')
const statusLabel = (u: AdminUser) => (u.riskFlag ? '风控中' : '正常')
</script>

<template>
  <div>
    <!-- 用户统计小卡 -->
    <div class="admin-stats" style="grid-template-columns: repeat(4, 1fr); margin-bottom: 20px">
      <div v-for="s in stats" :key="s.label" class="admin-stat-card" style="padding: 14px 18px">
        <div class="stat-label" style="font-size: 12px; margin-bottom: 4px">{{ s.label }}</div>
        <div class="stat-value" style="font-size: 22px" :style="s.color ? { color: s.color } : {}">{{ s.value }}</div>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="admin-filter">
      <el-input v-model="keyword" placeholder="🔍 搜索手机号 / 昵称 / 城市" style="flex: 2; min-width: 220px" clearable @keyup.enter="doSearch" />
      <el-select v-model="member" style="width: 150px" @change="page = 1; void load()">
        <el-option v-for="f in MEMBER_FILTERS" :key="f.value" :label="f.label" :value="f.value" />
      </el-select>
      <el-select v-model="source" style="width: 170px" @change="page = 1; void load()">
        <el-option v-for="f in SOURCE_FILTERS" :key="f.value" :label="f.label" :value="f.value" />
      </el-select>
      <el-button type="primary" @click="doSearch">🔍 查询</el-button>
      <el-button @click="doReset">重置</el-button>
      <div style="flex: 1" />
      <span class="bf-muted">共 {{ total }} 位注册用户</span>
      <el-button class="admin-btn admin-btn-outline admin-btn-sm" @click="doExport">📥 导出用户数据</el-button>
    </div>

    <!-- 用户表格 -->
    <div class="admin-table-wrap">
      <el-table v-loading="loading" :data="rows" style="width: 100%">
        <el-table-column label="用户" min-width="180">
          <template #default="{ row }">
            <div class="user-cell">
              <div class="user-avatar-sm">{{ row.nickname.slice(0, 1) }}</div>
              <div>
                <div class="user-name">{{ row.nickname }}</div>
                <div class="user-sub">{{ row.id }} · {{ row.phone }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="会员等级" width="120">
          <template #default="{ row }">
            <span class="tag" :class="memberTag(row)">{{ memberLabel(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="累计消费" width="110">
          <template #default="{ row }">
            <span style="color: var(--bf-ok); font-weight: 600">¥{{ row.totalSpendYuan.toFixed(2) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="orderCount" label="订单数" width="80" />
        <el-table-column prop="source" label="注册来源" width="150">
          <template #default="{ row }">
            <span class="tag" :class="row.source === '邀请注册' ? 'tag-purple' : row.source === '付费弹窗' ? 'tag-orange' : row.source === '商机详情页' || row.source === '分享卡片' ? 'tag-green' : 'tag-blue'">{{ row.source }}</span>
            <div v-if="row.inviterPhone" class="user-sub" style="margin-top: 2px">邀请人 {{ row.inviterPhone }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="createdAt" label="注册时间" width="150" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <span class="tag" :class="statusTag(row)">{{ statusLabel(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <a class="action-link" @click="openDetail(row)">详情</a>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination">
        <div>共 <strong style="color: var(--bf-text)">{{ total }}</strong> 条记录 · 当前第 {{ page }} 页</div>
        <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total" layout="prev, pager, next" background small @current-change="load" />
      </div>
    </div>

    <!-- 用户详情 -->
    <el-dialog v-model="detailOpen" title="用户详情" width="640px" destroy-on-close>
      <template v-if="detail">
        <div class="bf-card" style="margin-bottom: 12px">
          <div style="font-size: 16px; font-weight: 700">{{ detail.user.nickname }}</div>
          <div class="bf-muted" style="margin-top: 4px">
            {{ detail.user.phone }} · {{ detail.user.city }} · {{ detail.user.memberLabel }} · 来源 {{ detail.user.source }}
          </div>
          <div v-if="detail.user.inviterPhone" class="bf-muted">邀请人（已脱敏）：{{ detail.user.inviterPhone }}</div>
          <div class="bf-muted">订单 {{ detail.user.orderCount }} 单 · 累计消费 ¥{{ detail.user.totalSpendYuan }} · 注册 {{ detail.user.createdAt }}</div>
          <el-tag v-if="detail.user.riskFlag" type="danger" size="small" style="margin-top: 6px">命中风控标记，已转人工审核</el-tag>
        </div>

        <div class="bf-card" style="margin-bottom: 12px">
          <div style="font-weight: 600; margin-bottom: 8px">全部订单（{{ detail.orders.length }}）</div>
          <el-table :data="detail.orders" size="small">
            <el-table-column prop="id" label="订单号" width="130" />
            <el-table-column prop="planName" label="套餐" width="110" />
            <el-table-column label="金额" width="80">
              <template #default="{ row }">¥{{ row.amountYuan }}</template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <span class="bf-tag" :class="{ 'bf-tag--ok': row.status === 'delivered', 'bf-tag--warn': row.status === 'generating', 'bf-tag--danger': row.abnormal }">
                  {{ row.statusLabel }}
                </span>
                <span v-if="row.abnormal" class="bf-abnormal-tag" style="margin-left: 4px">异常</span>
              </template>
            </el-table-column>
            <el-table-column prop="createdAt" label="下单时间" width="130" />
          </el-table>
        </div>

        <div class="bf-card">
          <div style="font-weight: 600; margin-bottom: 8px">启动包记录（{{ detail.packages.length }}）</div>
          <el-table :data="detail.packages" size="small">
            <el-table-column prop="orderId" label="订单号" width="130" />
            <el-table-column prop="name" label="启动包" min-width="180" />
            <el-table-column prop="fileCount" label="文件数" width="80" />
            <el-table-column prop="status" label="状态" width="90" />
            <el-table-column prop="createdAt" label="生成时间" width="130" />
          </el-table>
        </div>
      </template>
    </el-dialog>
  </div>
</template>
