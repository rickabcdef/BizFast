<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getAdminOpportunities,
  saveOpportunity,
  toggleOpportunityShelf,
  importOpportunities,
  reviewOpportunity,
  getAdminOpportunityVersions,
  rollbackOpportunity,
  type AdminOpportunity,
  type AdminSession,
  type OpportunityVersion
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
  { value: '', label: '全部状态' },
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

// ---- 商机统计卡（对齐切图 16 页：总数 / 上架中 / 待审核 / 已驳回） ----
const stats = computed(() => {
  const passed = rows.value.filter((o) => o.status === 'passed').length
  const onShelf = rows.value.filter((o) => o.onShelf).length
  const pending = rows.value.filter((o) => o.status === 'pending').length
  const rejected = rows.value.filter((o) => o.status === 'rejected').length
  return [
    { label: '商机总数', value: String(total.value) },
    { label: '上架中', value: String(onShelf), color: 'var(--bf-ok)' },
    { label: '待审核', value: String(pending), color: 'var(--bf-primary)' },
    { label: '已驳回', value: String(rejected), color: 'var(--bf-text-3)' }
  ]
})

// ---- 卡片辅助（对齐切图 biz-card） ----
const statusDot = (o: AdminOpportunity) => (o.onShelf ? 'on' : o.status === 'passed' ? 'off' : 'off')
const statusText = (o: AdminOpportunity) => (o.onShelf ? '上架中' : o.status === 'passed' ? '已下架' : o.statusLabel)
const statusColor = (o: AdminOpportunity) =>
  o.onShelf || o.status === 'passed' ? (o.onShelf ? 'var(--bf-ok)' : 'var(--bf-text-3)') : o.status === 'pending' ? 'var(--bf-warn)' : 'var(--bf-danger)'
const capitalText = (o: AdminOpportunity) => `¥${o.capitalMin / 10000}–${o.capitalMax / 10000} 万`
const stars = (o: AdminOpportunity) => '★'.repeat(Math.max(1, o.difficultyStars))

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

const doReview = async (o: AdminOpportunity, action: 'approve' | 'reject') => {
  try {
    const r = await reviewOpportunity(auth.session as AdminSession, o.id, action)
    ElMessage.success(r.message)
    void load()
  } catch (e: any) {
    ElMessage.error(e?.message || '操作失败')
  }
}

// ---- V5.0 M4-04 版本历史 / 一键回滚（保存时自动备份上一版本，所见即所得） ----
const versionOpen = ref(false)
const versionBusy = ref(false)
const versionItem = ref<AdminOpportunity | null>(null)
const versionList = ref<OpportunityVersion[]>([])

const openVersions = async (o: AdminOpportunity) => {
  versionItem.value = o
  versionOpen.value = true
  try {
    const d = await getAdminOpportunityVersions(auth.session as AdminSession, o.id)
    versionList.value = d.versions || []
  } catch {
    versionList.value = []
  }
}

const doRollback = async (v: OpportunityVersion) => {
  if (!versionItem.value || versionBusy.value) return
  versionBusy.value = true
  try {
    await ElMessageBox.confirm(`确认回滚到 v${v.version}？当前内容将被历史版本覆盖（可再次保存新版本恢复）。`, '一键回滚', {
      type: 'warning',
      confirmButtonText: '确认回滚',
      cancelButtonText: '取消'
    })
    const r = await rollbackOpportunity(auth.session as AdminSession, versionItem.value.id, v.version)
    ElMessage.success(r.message)
    versionOpen.value = false
    void load()
  } catch (e: any) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e?.message || '回滚失败')
  } finally {
    versionBusy.value = false
  }
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
</script>

<template>
  <div>
    <!-- 商机统计卡 -->
    <div class="admin-stats" style="grid-template-columns: repeat(4, 1fr); margin-bottom: 16px">
      <div v-for="s in stats" :key="s.label" class="admin-stat-card" style="padding: 14px 18px">
        <div class="stat-label" style="font-size: 12px">{{ s.label }}</div>
        <div class="stat-value" style="font-size: 22px" :style="s.color ? { color: s.color } : {}">{{ s.value }}</div>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="admin-filter">
      <el-input v-model="keyword" placeholder="🔍 搜索商机名称 / 分类 / 城市" style="flex: 2; min-width: 220px" clearable @keyup.enter="doSearch" />
      <el-select v-model="status" style="width: 150px" @change="page = 1; void load()">
        <el-option v-for="f in STATUS_FILTERS" :key="f.value" :label="f.label" :value="f.value" />
      </el-select>
      <el-button type="primary" @click="doSearch">🔍 查询</el-button>
      <div style="flex: 1" />
      <span class="bf-muted">共 {{ total }} 条商机</span>
      <el-button type="primary" @click="openCreate">➕ 新增商机</el-button>
      <el-button class="admin-btn admin-btn-outline admin-btn-sm" @click="importOpen = true">📥 批量导入</el-button>
    </div>

    <!-- 商机卡片网格（对齐切图 16 页 biz-grid） -->
    <div v-loading="loading" class="biz-grid">
      <div v-for="o in rows" :key="o.id" class="biz-card">
        <div class="biz-card-header">
          <div>
            <div class="biz-name">{{ o.title }}</div>
            <div class="biz-cat">{{ o.category }} · {{ o.city }} · 来源 {{ o.source }}</div>
          </div>
          <div class="biz-status">
            <span class="biz-dot" :class="statusDot(o)"></span>
            <span style="font-size: 12px; margin-left: 4px" :style="{ color: statusColor(o) }">{{ statusText(o) }}</span>
          </div>
        </div>
        <div class="biz-meta">
          <div class="biz-meta-item">
            <div class="k">启动资金</div>
            <div class="v" :style="{ color: o.capitalMax <= 20000 ? 'var(--bf-ok)' : '' }">{{ capitalText(o) }}</div>
          </div>
          <div class="biz-meta-item">
            <div class="k">回本周期</div>
            <div class="v">{{ o.paybackMonths }} 月</div>
          </div>
          <div class="biz-meta-item">
            <div class="k">毛利率</div>
            <div class="v" :style="{ color: o.marginPercent >= 45 ? 'var(--bf-ok)' : '' }">{{ o.marginPercent }}%</div>
          </div>
          <div class="biz-meta-item">
            <div class="k">难度</div>
            <div class="v" style="color: var(--bf-warn)">{{ stars(o) }}</div>
          </div>
        </div>
        <div class="biz-actions">
          <button class="admin-btn admin-btn-sm" @click="openEdit(o)">编辑</button>
          <button class="admin-btn admin-btn-outline admin-btn-sm" @click="openVersions(o)">版本</button>
          <template v-if="o.status === 'passed'">
            <button v-if="!o.onShelf" class="admin-btn admin-btn-sm" style="background: var(--bf-ok)" @click="doToggleShelf(o, true)">上架</button>
            <button v-else class="admin-btn admin-btn-outline admin-btn-sm" @click="doToggleShelf(o, false)">下架</button>
          </template>
          <template v-else-if="o.status === 'pending'">
            <button class="admin-btn admin-btn-sm" style="background: var(--bf-ok)" @click="doReview(o, 'approve')">通过</button>
            <button class="admin-btn admin-btn-danger admin-btn-sm" @click="doReview(o, 'reject')">驳回</button>
          </template>
          <span v-else class="bf-muted" style="font-size: 12px; align-self: center">已驳回，可编辑后重新提交</span>
        </div>
      </div>

      <!-- 添加新商机卡 -->
      <div class="biz-add" @click="openCreate">
        <div>＋</div>
        <div style="font-size: 13px; margin-top: 8px">添加新商机</div>
      </div>
    </div>

    <div v-if="total > pageSize" style="display: flex; justify-content: flex-end; margin-top: 8px">
      <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total" layout="prev, pager, next" background small @current-change="load" />
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

    <!-- V5.0 M4-04 版本历史 / 一键回滚 -->
    <el-dialog v-model="versionOpen" title="版本历史与一键回滚" width="640px" destroy-on-close>
      <div class="bf-muted" style="margin-bottom: 10px">
        {{ versionItem?.title }} · 保存时自动备份上一版本，可回滚到任意历史版本；修改后 5 分钟内对用户端生效。
      </div>
      <div v-if="versionList.length === 0" class="bf-muted" style="padding: 12px 0">暂无历史版本</div>
      <div v-for="v in versionList" :key="v.version" style="display: flex; align-items: center; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid rgba(255,255,255,0.06)">
        <div style="min-width: 0">
          <div style="font-size: 13px; color: var(--bf-text-1)">v{{ v.version }}</div>
          <div class="bf-muted" style="font-size: 12px">更新于 {{ v.updatedAt }}</div>
        </div>
        <el-button size="small" :loading="versionBusy" @click="doRollback(v)">↩️ 回滚到此版本</el-button>
      </div>
    </el-dialog>
  </div>
</template>
