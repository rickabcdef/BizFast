<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getAdminPrompts,
  saveAdminPrompt,
  rollbackPrompt,
  testAdminPrompt,
  type PromptItem,
  type AdminSession
} from '@/api/adminApi'
import { useAuthStore } from '@/store/auth'

const auth = useAuthStore()
const items = ref<PromptItem[]>([])
const notice = ref('')
const loading = ref(true)

const load = async () => {
  loading.value = true
  try {
    const d = await getAdminPrompts()
    items.value = d.items
    notice.value = d.notice
  } finally {
    loading.value = false
  }
}

onMounted(load)

// 当前生效版本合计（对齐切图 16 页 alert-success：当前生效版本）
const versionSummary = computed(() => {
  if (items.value.length === 0) return { v: '', at: '', models: '' }
  const last = items.value[0]
  const allV = items.value.reduce((s, p) => s + p.versions.length, 0)
  return {
    v: `共 ${items.value.length} 项配置 · ${allV} 个版本`,
    at: items.value.map((p) => `${p.name} v${p.versions.length}`).join(' · '),
    models: items.value.map((p) => p.model).join(' / ')
  }
})

// 编辑
const editOpen = ref(false)
const editBusy = ref(false)
const editing = ref<PromptItem | null>(null)
const content = ref('')
const model = ref('')

const openEdit = (p: PromptItem) => {
  editing.value = p
  content.value = p.content
  model.value = p.model
  editOpen.value = true
}

const doSave = async () => {
  if (!editing.value || editBusy.value) return
  editBusy.value = true
  try {
    const r = await saveAdminPrompt(auth.session as AdminSession, editing.value.key, { content: content.value, model: model.value })
    editOpen.value = false
    ElMessage.success(`已保存（v${r.versions.length}，即时生效无需发版）`)
    void load()
  } finally {
    editBusy.value = false
  }
}

// 版本历史 + 一键回滚
const versionOpen = ref(false)
const versionItem = ref<PromptItem | null>(null)

const openVersions = (p: PromptItem) => {
  versionItem.value = p
  versionOpen.value = true
}

const doRollback = async (v: { version: number }) => {
  if (!versionItem.value) return
  try {
    await ElMessageBox.confirm(`确认回滚到 v${v.version}？当前内容将被覆盖（可再次保存新版本恢复）`, '一键回滚', { type: 'warning', confirmButtonText: '确认回滚', cancelButtonText: '取消' })
    await rollbackPrompt(auth.session as AdminSession, versionItem.value.key, v.version)
    versionOpen.value = false
    ElMessage.success(`已回滚至 v${v.version}`)
    void load()
  } catch (e: any) {
    if (e?.message) ElMessage.error(e.message)
  }
}

// V5.0 M4-06 一键测试（不产生真实费用，返回示例输出）
const testingKey = ref<string | null>(null)
const testResult = ref<{ key: string; sample: string; latencyMs: number } | null>(null)

const doTest = async (p: PromptItem) => {
  if (testingKey.value) return
  testingKey.value = p.key
  testResult.value = null
  try {
    const r = await testAdminPrompt(auth.session as AdminSession, p.key)
    testResult.value = { key: p.key, sample: r.sample, latencyMs: r.latencyMs }
    ElMessage.success(r.ok ? '测试通过' : '测试异常')
  } catch (e: any) {
    ElMessage.error(e?.message || '测试失败')
  } finally {
    testingKey.value = null
  }
}
</script>

<template>
  <div>
    <!-- 当前生效版本（对齐切图 16 页 alert-success） -->
    <div class="alert-card alert-success">
      <span style="font-size: 18px">✅</span>
      <div>
        <strong>当前生效：{{ versionSummary.v }}</strong>
        <div style="font-size: 12px; margin-top: 2px">{{ versionSummary.at }}</div>
        <div style="font-size: 12px; color: var(--bf-text-3)">AI 模型路由：{{ versionSummary.models }} · 所有修改保存后即时生效，支持一键回滚（M11-04）</div>
      </div>
    </div>

    <!-- 配置项列表 -->
    <div class="admin-table-wrap">
      <el-table v-loading="loading" :data="items" style="width: 100%">
        <el-table-column label="配置项" min-width="200">
          <template #default="{ row }">
            <div class="user-cell">
              <div class="user-avatar-sm">AI</div>
              <div>
                <div class="user-name">{{ row.name }}</div>
                <div class="user-sub">{{ row.key }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="模型路由" width="170">
          <template #default="{ row }">
            <span class="tag" :class="row.model === 'doubao-seed-1.6' ? 'tag-blue' : row.model === 'doubao-lite' ? 'tag-purple' : 'tag-gray'">{{ row.model }}</span>
          </template>
        </el-table-column>
        <el-table-column label="版本" width="90">
          <template #default="{ row }">
            <span class="tag tag-green">v{{ row.versions.length }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="updatedAt" label="更新时间" width="160" />
        <el-table-column label="内容预览" min-width="260">
          <template #default="{ row }">
            <div class="bf-muted" style="line-height: 1.6; max-width: 420px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap">
              {{ row.content }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <a class="action-link" @click="openEdit(row)">编辑</a>
            <a class="action-link" style="color: var(--bf-primary)" @click="doTest(row)">{{ testingKey === row.key ? '测试中…' : '一键测试' }}</a>
            <a class="action-link" @click="openVersions(row)">版本历史</a>
            <a class="action-link" style="color: var(--bf-warn)" @click="openVersions(row)">回滚</a>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- V5.0 M4-06 一键测试结果 -->
    <div v-if="testResult" class="admin-chart-card" style="margin-top: 12px">
      <div class="bf-row" style="justify-content: space-between">
        <strong>一键测试结果（{{ testResult.key }} · {{ testResult.latencyMs }}ms）</strong>
        <a class="action-link" @click="testResult = null">关闭</a>
      </div>
      <div class="bf-muted" style="margin-top: 8px; line-height: 1.6">{{ testResult.sample }}</div>
    </div>

    <div class="bf-note bf-muted">{{ notice }}</div>

    <!-- 编辑弹窗（对齐切图 16 页 prompt-editor 风格） -->
    <el-dialog v-model="editOpen" title="编辑提示词" width="680px" destroy-on-close>
      <template v-if="editing">
        <div class="bf-muted" style="margin-bottom: 10px">{{ editing.name }} · {{ editing.key }} · 当前 v{{ editing.versions.length }}（保存后自动备份上一版本，可随时回滚）</div>
        <div class="form-row">
          <div class="form-label">🤖 模型路由</div>
          <div class="bf-filter">
            <span
              v-for="m in ['doubao-seed-1.6', 'doubao-lite', 'default']"
              :key="m"
              class="bf-filter__seg"
              :class="{ 'is-active': model === m }"
              @click="model = m"
            >
              {{ m }}
            </span>
          </div>
        </div>
        <div class="form-row">
          <div class="form-label">📝 提示词内容（{变量} 将被用户实际输入替换）</div>
          <textarea v-model="content" class="prompt-editor" rows="12" maxlength="4000"></textarea>
          <div class="form-hint">💡 修改会直接影响用户收到的诊断 / 启动包质量；保存后即时生效，无需发版。</div>
        </div>
      </template>
      <template #footer>
        <el-button @click="editOpen = false">取消</el-button>
        <el-button type="primary" :loading="editBusy" @click="doSave">💾 保存（即时生效）</el-button>
      </template>
    </el-dialog>

    <!-- 版本历史 + 一键回滚 -->
    <el-dialog v-model="versionOpen" title="版本历史与一键回滚" width="700px" destroy-on-close>
      <template v-if="versionItem">
        <div class="bf-muted" style="margin-bottom: 10px">{{ versionItem.name }} · 共 {{ versionItem.versions.length }} 个版本，可回滚到任意历史版本（M11-04）</div>
        <div v-for="v in [...versionItem.versions].reverse()" :key="v.version" class="admin-chart-card" style="margin-bottom: 10px">
          <div class="bf-row" style="justify-content: space-between">
            <div>
              <span class="tag tag-green" style="margin-right: 8px">v{{ v.version }}</span>
              <span class="tag tag-blue">{{ v.model }}</span>
              <span v-if="v.version === versionItem.versions.length" class="tag tag-orange" style="margin-left: 8px">当前生效</span>
            </div>
            <div class="bf-muted">{{ v.updatedAt }} · {{ v.operator }}</div>
          </div>
          <div class="bf-muted" style="margin-top: 8px; line-height: 1.6; white-space: pre-wrap; max-height: 90px; overflow-y: auto">{{ v.content }}</div>
          <div style="margin-top: 10px; text-align: right">
            <el-button v-if="v.version !== versionItem.versions.length" size="small" text type="warning" @click="doRollback(v)">
              ↩️ 回滚到此版本
            </el-button>
          </div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>
