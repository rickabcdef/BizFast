<script setup lang="ts">
import { ref, onMounted } from 'vue'
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
const onlyAbnormal = ref(false)
const loading = ref(false)

const STATUS_LIST = [
  { value: '', label: '全部状态' },
  { value: 'pending', label: '待支付' },
  { value: 'paid', label: '已支付' },
  { value: 'generating', label: '生成中' },
  { value: 'delivered', label: '已交付' },
  { value: 'refunded', label: '已退款' },
  { value: 'closed', label: '已关闭' }
]

const load = async () => {
  loading.value = true
  try {
    const d = await getAdminOrders({ page: page.value, pageSize, status: status.value, keyword: keyword.value, abnormal: onlyAbnormal.value })
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

const abnormalCount = () => rows.value.filter((o) => o.abnormal).length
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
</script>

<template>
  <div>
    <div class="bf-card">
      <div class="bf-filter">
        <el-input v-model="keyword" placeholder="搜索订单号 / 手机号" style="width: 220px" clearable @keyup.enter="doSearch" />
        <el-button type="primary" @click="doSearch">搜索</el-button>
        <span
          v-for="s in STATUS_LIST"
          :key="s.value"
          class="bf-filter__seg"
          :class="{ 'is-active': status === s.value }"
          @click="status = s.value; page = 1; void load()"
        >
          {{ s.label }}
        </span>
        <el-checkbox v-model="onlyAbnormal" label="只看异常订单" style="margin-left: 8px" @change="page = 1; void load()" />
        <div style="flex: 1" />
        <span class="bf-muted">共 {{ total }} 笔订单</span>
        <el-button size="small" @click="doExport">导出对账表</el-button>
      </div>
      <div v-if="abnormalCount() > 0" style="margin-top: 12px">
        <el-alert type="error" :closable="false" show-icon>
          <template #title>
            当前列表有 <b>{{ abnormalCount() }}</b> 笔异常订单（已支付未交付 / 支付回调缺失），已自动标红并告警（M11-02）
          </template>
        </el-alert>
      </div>
    </div>

    <div class="bf-card">
      <el-table v-loading="loading" :data="rows" :row-class-name="rowClass" style="width: 100%">
        <el-table-column prop="id" label="订单号" width="140" />
        <el-table-column prop="userPhone" label="用户" width="120" />
        <el-table-column prop="planName" label="套餐" width="110" />
        <el-table-column label="金额" width="80">
          <template #default="{ row }">¥{{ row.amountYuan }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <span class="bf-tag" :class="{ 'bf-tag--ok': row.status === 'delivered', 'bf-tag--warn': row.status === 'generating' || row.status === 'paid', 'bf-tag--danger': row.abnormal }">
              {{ row.statusLabel }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="异常告警" width="160">
          <template #default="{ row }">
            <span v-if="row.abnormal" class="bf-abnormal-tag">
              <el-icon><WarningFilled /></el-icon>
              {{ ORDER_ABNORMAL_LABEL[row.abnormalType || ''] || '异常' }}
            </span>
            <span v-else class="bf-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="channel" label="渠道" width="100" />
        <el-table-column prop="createdAt" label="下单时间" width="130" />
        <el-table-column label="退款" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.refundRequested" size="small" type="warning">退款申请中</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <template v-if="row.refundRequested && ['paid', 'generating', 'delivered'].includes(row.status)">
              <el-button size="small" text type="success" @click="doRefund(row, 'approve')">同意退款</el-button>
              <el-button size="small" text type="danger" @click="doRefund(row, 'reject')">驳回</el-button>
            </template>
            <span v-else class="bf-muted">—</span>
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
  </div>
</template>
