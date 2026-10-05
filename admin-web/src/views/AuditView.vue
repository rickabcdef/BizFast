<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getAdminAuditLogs, type AuditLogItem } from '@/api/adminApi'

const rows = ref<AuditLogItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const operator = ref('')
const action = ref('')
const loading = ref(false)

const load = async () => {
  loading.value = true
  try {
    const d = await getAdminAuditLogs({ page: page.value, pageSize, operator: operator.value, action: action.value })
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
</script>

<template>
  <div>
    <div class="bf-card">
      <div class="bf-filter">
        <el-input v-model="operator" placeholder="操作人" style="width: 160px" clearable @keyup.enter="doSearch" />
        <el-input v-model="action" placeholder="操作类型" style="width: 160px" clearable @keyup.enter="doSearch" />
        <el-button type="primary" @click="doSearch">搜索</el-button>
        <div style="flex: 1" />
        <span class="bf-muted">共 {{ total }} 条日志</span>
      </div>
    </div>

    <div class="bf-card">
      <el-table v-loading="loading" :data="rows" style="width: 100%">
        <el-table-column prop="id" label="日志 ID" width="130" />
        <el-table-column prop="operator" label="操作人" width="120" />
        <el-table-column prop="role" label="角色" width="90" />
        <el-table-column prop="action" label="操作" width="120">
          <template #default="{ row }">
            <span class="bf-tag">{{ row.action }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="target" label="对象" width="140" />
        <el-table-column prop="detail" label="详情" min-width="240" />
        <el-table-column prop="createdAt" label="时间" width="170" />
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

    <div class="bf-note bf-muted">
      M11-08：记录后台所有关键操作（登录 / 改价 / 退款 / 改数据 / 改提示词），日志保留 ≥ 180 天、不可篡改；后台所有接口均鉴权、限流并记录审计日志。
    </div>
  </div>
</template>
