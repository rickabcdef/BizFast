<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getAdminReviews,
  reviewAction,
  batchReviewAction,
  appealReview,
  forceOfflineReview,
  type ReviewItem,
  type AdminSession
} from '@/api/adminApi'
import { useAuthStore } from '@/store/auth'

const auth = useAuthStore()
const rows = ref<ReviewItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const keyword = ref('')
const status = ref('')
const loading = ref(false)
const selection = ref<ReviewItem[]>([])

const STATUS_FILTERS = [
  { value: '', label: '全部' },
  { value: 'pending', label: '待审核' },
  { value: 'passed', label: '已通过' },
  { value: 'rejected', label: '已拦截' }
]

const load = async () => {
  loading.value = true
  try {
    const d = await getAdminReviews({ page: page.value, pageSize, status: status.value, keyword: keyword.value })
    rows.value = d.items
    total.value = d.total
    selection.value = []
  } finally {
    loading.value = false
  }
}

onMounted(load)

const doSearch = () => {
  page.value = 1
  void load()
}

const act = async (item: ReviewItem, action: 'pass' | 'reject') => {
  try {
    const r = await reviewAction(auth.session as AdminSession, item.id, action)
    ElMessage.success(r.message)
    void load()
  } catch (e: any) {
    ElMessage.error(e?.message || '操作失败')
  }
}

// 批量处理（M11-09）
const batch = async (action: 'pass' | 'reject') => {
  if (selection.value.length === 0) {
    ElMessage.warning('请先勾选待处理的内容')
    return
  }
  try {
    const ids = selection.value.map((r) => r.id)
    await ElMessageBox.confirm(`确认批量${action === 'pass' ? '通过' : '拦截'}选中的 ${ids.length} 条内容？`, '批量处理', { type: 'warning', confirmButtonText: '确认处理', cancelButtonText: '取消' })
    const r = await batchReviewAction(auth.session as AdminSession, ids, action)
    ElMessage.success(r.message)
    void load()
  } catch (e: any) {
    if (e?.message) ElMessage.error(e.message)
  }
}

// 申诉处理
const doAppeal = async (item: ReviewItem, action: 'approve' | 'reject') => {
  try {
    if (action === 'approve') {
      await ElMessageBox.confirm('确认通过该申诉并恢复内容展示？', '处理申诉', { type: 'warning', confirmButtonText: '通过申诉', cancelButtonText: '取消' })
    }
    const r = await appealReview(auth.session as AdminSession, item.id, action)
    ElMessage.success(r.message)
    void load()
  } catch (e: any) {
    if (e?.message) ElMessage.error(e.message)
  }
}

// 一键下架
const doForceOffline = async (item: ReviewItem) => {
  try {
    await ElMessageBox.confirm('违规内容将立即对用户端不可见（1 分钟内下架），确认？', '一键下架', { type: 'error', confirmButtonText: '确认下架' })
    const r = await forceOfflineReview(auth.session as AdminSession, item.id)
    ElMessage.success(r.message)
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
        <el-input v-model="keyword" placeholder="搜索内容 / 类型" style="width: 220px" clearable @keyup.enter="doSearch" />
        <el-button type="primary" @click="doSearch">搜索</el-button>
        <span
          v-for="f in STATUS_FILTERS"
          :key="f.value"
          class="bf-filter__seg"
          :class="{ 'is-active': status === f.value }"
          @click="status = f.value; page = 1; void load()"
        >
          {{ f.label }}
        </span>
        <div style="flex: 1" />
        <span class="bf-muted">共 {{ total }} 条内容</span>
        <el-button size="small" type="success" plain :disabled="selection.length === 0" @click="batch('pass')">批量通过</el-button>
        <el-button size="small" type="danger" plain :disabled="selection.length === 0" @click="batch('reject')">批量拦截</el-button>
      </div>
    </div>

    <div class="bf-card">
      <el-table v-loading="loading" :data="rows" style="width: 100%" @selection-change="(v: ReviewItem[]) => (selection = v)">
        <el-table-column type="selection" width="44" :selectable="(row: ReviewItem) => row.status === 'pending'" />
        <el-table-column prop="type" label="类型" width="110" />
        <el-table-column prop="content" label="内容" min-width="260">
          <template #default="{ row }">
            <div style="line-height: 1.6">{{ row.content }}</div>
            <div v-if="row.reason" style="margin-top: 4px">
              <el-tag type="warning" size="small">命中：{{ row.reason }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <span class="bf-tag" :class="{ 'bf-tag--ok': row.status === 'passed', 'bf-tag--warn': row.status === 'pending', 'bf-tag--danger': row.status === 'rejected' }">
              {{ row.statusLabel }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="申诉" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.appeal" type="danger" size="small" effect="plain">有申诉</el-tag>
            <span v-else class="bf-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="createdAt" label="时间" width="130" />
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <template v-if="row.status === 'pending'">
              <el-button size="small" text type="success" @click="act(row, 'pass')">通过</el-button>
              <el-button size="small" text type="danger" @click="act(row, 'reject')">拦截</el-button>
            </template>
            <template v-else-if="row.appeal">
              <el-button size="small" text type="success" @click="doAppeal(row, 'approve')">通过申诉</el-button>
              <el-button size="small" text @click="doAppeal(row, 'reject')">驳回申诉</el-button>
            </template>
            <el-button v-if="row.status === 'passed'" size="small" text type="danger" @click="doForceOffline(row)">一键下架</el-button>
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

    <div class="bf-note bf-muted">
      M11-06：P0 由后端服务实现敏感词拦截能力（违规拦截率 ≥ 99%）；M11-09（P1）：本工作台支持人工复核、批量处理、申诉与一键下架，违规内容可在 1 分钟内下架。
    </div>
  </div>
</template>
