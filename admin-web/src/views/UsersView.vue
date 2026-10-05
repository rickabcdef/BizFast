<script setup lang="ts">
import { ref, onMounted } from 'vue'
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
const loading = ref(false)
const detail = ref<{ user: AdminUser; orders: AdminOrder[]; packages: any[] } | null>(null)
const detailOpen = ref(false)

const MEMBER_FILTERS = [
  { value: '', label: '全部' },
  { value: 'none', label: '游客' },
  { value: 'single', label: '单次' },
  { value: 'month', label: '月会员' },
  { value: 'year', label: '年会员' }
]

const load = async () => {
  loading.value = true
  try {
    const d = await getAdminUsers({ page: page.value, pageSize, keyword: keyword.value, memberStatus: member.value })
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
</script>

<template>
  <div>
    <div class="bf-card">
      <div class="bf-filter">
        <el-input v-model="keyword" placeholder="搜索手机号 / 昵称 / 城市" style="width: 240px" clearable @keyup.enter="doSearch" />
        <el-button type="primary" @click="doSearch">搜索</el-button>
        <span
          v-for="f in MEMBER_FILTERS"
          :key="f.value"
          class="bf-filter__seg"
          :class="{ 'is-active': member === f.value }"
          @click="member = f.value; page = 1; void load()"
        >
          {{ f.label }}
        </span>
        <div style="flex: 1" />
        <span class="bf-muted">共 {{ total }} 个用户</span>
        <el-button size="small" @click="doExport">导出 CSV</el-button>
      </div>
    </div>

    <div class="bf-card">
      <el-table v-loading="loading" :data="rows" style="width: 100%">
        <el-table-column prop="nickname" label="昵称" min-width="120">
          <template #default="{ row }">
            {{ row.nickname }}
            <el-tag v-if="row.riskFlag" type="danger" size="small" style="margin-left: 6px">风控</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="phone" label="手机号" width="130" />
        <el-table-column prop="city" label="城市" width="80" />
        <el-table-column label="会员状态" width="100">
          <template #default="{ row }">
            <span class="bf-tag" :class="{ 'bf-tag--ok': row.memberStatus !== 'none' }">{{ row.memberLabel }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="orderCount" label="订单数" width="80" />
        <el-table-column label="消费总额" width="100">
          <template #default="{ row }">¥{{ row.totalSpendYuan }}</template>
        </el-table-column>
        <el-table-column prop="source" label="来源渠道" width="110" />
        <el-table-column prop="createdAt" label="注册时间" width="130" />
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="openDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-if="total > pageSize"
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next"
        style="margin-top: 14px; justify-content: flex-end"
        @current-change="load"
      />
    </div>

    <el-dialog v-model="detailOpen" title="用户详情" width="640px" destroy-on-close>
      <template v-if="detail">
        <div class="bf-card" style="margin-bottom: 12px">
          <div style="font-size: 16px; font-weight: 700">{{ detail.user.nickname }}</div>
          <div class="bf-muted" style="margin-top: 4px">
            {{ detail.user.phone }} · {{ detail.user.city }} · {{ detail.user.memberLabel }} · 来源 {{ detail.user.source }}
          </div>
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
