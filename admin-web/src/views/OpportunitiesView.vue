<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getAdminOpportunities,
  saveOpportunity,
  toggleOpportunityShelf,
  importOpportunities,
  reviewOpportunity,
  type AdminOpportunity,
  type AdminSession
} from '@/api/adminApi'
import { useAuthStore } from '@/store/auth'

const auth = useAuthStore()
const rows = ref<AdminOpportunity[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const keyword = ref('')
const status = ref('')
const loading = ref(false)

const STATUS_FILTERS = [
  { value: '', label: '全部' },
  { value: 'pending', label: '待审核' },
  { value: 'passed', label: '已通过' },
  { value: 'rejected', label: '已驳回' }
]

const load = async () => {
  loading.value = true
  try {
    const d = await getAdminOpportunities({ page: page.value, pageSize, status: status.value, keyword: keyword.value })
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

// 新增 / 编辑
const formOpen = ref(false)
const formBusy = ref(false)
const editingId = ref<string | null>(null)
const form = ref<Partial<AdminOpportunity>>({ title: '', category: '', city: '全国', capitalMin: 0, capitalMax: 0, paybackMonths: 0, marginPercent: 0, difficultyStars: 1 })

const openCreate = () => {
  editingId.value = null
  form.value = { title: '', category: '', city: '全国', capitalMin: 0, capitalMax: 0, paybackMonths: 0, marginPercent: 0, difficultyStars: 1 }
  formOpen.value = true
}

const openEdit = (o: AdminOpportunity) => {
  editingId.value = o.id
  form.value = { ...o }
  formOpen.value = true
}

const doSave = async () => {
  if (!form.value.title?.trim()) {
    ElMessage.warning('请输入商机名称')
    return
  }
  formBusy.value = true
  try {
    await saveOpportunity(auth.session as AdminSession, { ...form.value, id: editingId.value || undefined })
    formOpen.value = false
    ElMessage.success(editingId.value ? '商机已更新（5 分钟内对用户端生效）' : '商机已新增，进入待审核')
    void load()
  } finally {
    formBusy.value = false
  }
}

const doToggleShelf = async (o: AdminOpportunity, onShelf: boolean) => {
  const r = await toggleOpportunityShelf(auth.session as AdminSession, o.id, onShelf)
  ElMessage.success(r.message)
  void load()
}

// 批量导入
const importOpen = ref(false)
const importText = ref('')
const importBusy = ref(false)

const IMPORT_TEMPLATE = [
  '商机名称,分类,适用城市,资金下限(元),资金上限(元),回本周期(月),毛利率(%),难度(1-5星),来源',
  '夜市柠檬茶摊,餐饮小吃,长沙,8000,15000,2,62,1,批量导入',
  '上门宠物洗护,本地生活,上海,30000,80000,6,45,3,批量导入'
].join('\n')

const parseCsv = (text: string): AdminOpportunity[] => {
  const lines = text.trim().split(/\r?\n/).filter((l) => l.trim())
  if (lines.length < 2) return []
  const headers = lines[0].split(',').map((h) => h.trim())
  const idx = (name: string) => headers.indexOf(name)
  const out: AdminOpportunity[] = []
  for (let i = 1; i < lines.length; i++) {
    const cells = lines[i].split(',').map((c) => c.trim())
    const title = cells[idx('商机名称')]
    if (!title) continue
    out.push({
      id: `OP-IMP-${Date.now()}-${i}`,
      title,
      category: cells[idx('分类')] || '未分类',
      city: cells[idx('适用城市')] || '全国',
      capitalMin: Number(cells[idx('资金下限(元)')]) || 0,
      capitalMax: Number(cells[idx('资金上限(元)')]) || 0,
      paybackMonths: Number(cells[idx('回本周期(月)')]) || 0,
      marginPercent: Number(cells[idx('毛利率(%)')]) || 0,
      difficultyStars: Number(cells[idx('难度(1-5星)')]) || 1,
      source: cells[idx('来源')] || '批量导入',
      status: 'pending',
      statusLabel: '待审核',
      onShelf: false,
      createdAt: new Date().toISOString().slice(0, 10)
    })
  }
  return out
}

const doImport = async () => {
  const items = parseCsv(importText.value)
  if (items.length === 0) {
    ElMessage.warning('请粘贴至少 2 行：表头 + 数据')
    return
  }
  importBusy.value = true
  try {
    const r = await importOpportunities(auth.session as AdminSession, items)
    importOpen.value = false
    importText.value = ''
    ElMessage.success(`已导入 ${r.imported} 条，进入待审核队列`)
    status.value = 'pending'
    page.value = 1
    void load()
  } finally {
    importBusy.value = false
  }
}

const doReview = async (o: AdminOpportunity, action: 'approve' | 'reject') => {
  try {
    const r = await reviewOpportunity(auth.session as AdminSession, o.id, action)
    ElMessage.success(r.message)
    void load()
  } catch (e: any) {
    ElMessage.error(e?.message || '操作失败')
  }
}
</script>

<template>
  <div>
    <div class="bf-card">
      <div class="bf-filter">
        <el-input v-model="keyword" placeholder="搜索商机名称 / 分类 / 城市" style="width: 220px" clearable @keyup.enter="doSearch" />
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
        <span class="bf-muted">共 {{ total }} 条商机</span>
        <el-button size="small" type="primary" plain @click="openCreate">+ 新增商机</el-button>
        <el-button size="small" @click="importOpen = true">批量导入</el-button>
      </div>
    </div>

    <div class="bf-card">
      <el-table v-loading="loading" :data="rows" style="width: 100%">
        <el-table-column prop="title" label="商机名称" min-width="170" />
        <el-table-column prop="category" label="分类" width="100" />
        <el-table-column prop="city" label="城市" width="80" />
        <el-table-column label="资金" width="130">
          <template #default="{ row }">¥{{ row.capitalMin / 10000 }}–{{ row.capitalMax / 10000 }} 万</template>
        </el-table-column>
        <el-table-column label="回本 / 毛利" width="110">
          <template #default="{ row }">{{ row.paybackMonths }} 月 · {{ row.marginPercent }}%</template>
        </el-table-column>
        <el-table-column label="难度" width="90">
          <template #default="{ row }">{{ '★'.repeat(Math.max(1, row.difficultyStars)) }}</template>
        </el-table-column>
        <el-table-column label="审核状态" width="100">
          <template #default="{ row }">
            <span class="bf-tag" :class="{ 'bf-tag--ok': row.status === 'passed', 'bf-tag--warn': row.status === 'pending', 'bf-tag--danger': row.status === 'rejected' }">
              {{ row.statusLabel }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="上下架" width="90">
          <template #default="{ row }">
            <el-switch v-model="row.onShelf" :disabled="row.status !== 'passed'" @change="(v: boolean) => doToggleShelf(row, v)" />
          </template>
        </el-table-column>
        <el-table-column prop="source" label="来源" width="100" />
        <el-table-column label="操作" width="210" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="openEdit(row)">编辑</el-button>
            <template v-if="row.status === 'pending'">
              <el-button size="small" text type="success" @click="doReview(row, 'approve')">通过</el-button>
              <el-button size="small" text type="danger" @click="doReview(row, 'reject')">驳回</el-button>
            </template>
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

    <!-- 新增 / 编辑 -->
    <el-dialog v-model="formOpen" :title="editingId ? '编辑商机' : '新增商机'" width="560px" destroy-on-close>
      <el-form label-width="110px">
        <el-form-item label="商机名称"><el-input v-model="form.title" /></el-form-item>
        <el-form-item label="分类"><el-input v-model="form.category" placeholder="如：餐饮小吃 / 本地生活" /></el-form-item>
        <el-form-item label="适用城市"><el-input v-model="form.city" placeholder="如：上海 / 全国" /></el-form-item>
        <el-form-item label="资金区间">
          <el-input-number v-model="form.capitalMin" :min="0" :step="5000" style="width: 150px" /> ~
          <el-input-number v-model="form.capitalMax" :min="0" :step="5000" style="width: 150px" />
          <span class="bf-muted">（元）</span>
        </el-form-item>
        <el-form-item label="回本周期"><el-input-number v-model="form.paybackMonths" :min="1" :max="60" /> <span class="bf-muted">月</span></el-form-item>
        <el-form-item label="毛利率"><el-input-number v-model="form.marginPercent" :min="0" :max="100" /> <span class="bf-muted">%</span></el-form-item>
        <el-form-item label="难度星级"><el-input-number v-model="form.difficultyStars" :min="1" :max="5" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formOpen = false">取消</el-button>
        <el-button type="primary" :loading="formBusy" @click="doSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 批量导入 -->
    <el-dialog v-model="importOpen" title="批量导入商机" width="600px" destroy-on-close>
      <div class="bf-muted" style="margin-bottom: 8px">粘贴 CSV（第一行为表头，格式见模板）：</div>
      <el-input v-model="importText" type="textarea" :rows="6" :placeholder="IMPORT_TEMPLATE" />
      <div class="bf-note bf-muted">导入后进入「待审核」队列，审核通过后才可上架对用户端生效（M11-03）。</div>
      <template #footer>
        <el-button @click="importOpen = false">取消</el-button>
        <el-button type="primary" :loading="importBusy" @click="doImport">导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>
