<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getAdminPrompts,
  saveAdminPrompt,
  rollbackPrompt,
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
    await ElMessageBox.confirm(`确认回滚到 v${v.version}？当前内容将被覆盖（可再次保存新版本恢复）`, '一键回滚', { type: 'warning' })
    await rollbackPrompt(auth.session as AdminSession, versionItem.value.key, v.version)
    versionOpen.value = false
    ElMessage.success(`已回滚至 v${v.version}`)
    void load()
  } catch (e: any) {
    if (e?.message) ElMessage.error(e.message)
  }
}
</script>

<template>
  <div>
    <el-alert v-if="notice" type="success" :closable="false" show-icon style="margin-bottom: 14px" :title="notice" />

    <div class="bf-card">
      <el-table v-loading="loading" :data="items" style="width: 100%">
        <el-table-column prop="name" label="配置项" min-width="180" />
        <el-table-column prop="key" label="Key" width="110" />
        <el-table-column label="模型路由" width="160">
          <template #default="{ row }">
            <span class="bf-tag">{{ row.model }}</span>
          </template>
        </el-table-column>
        <el-table-column label="版本" width="80">
          <template #default="{ row }">v{{ row.versions.length }}</template>
        </el-table-column>
        <el-table-column prop="updatedAt" label="更新时间" width="150" />
        <el-table-column prop="content" label="内容预览" min-width="240">
          <template #default="{ row }">
            <div class="bf-muted" style="line-height: 1.6; max-width: 420px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap">
              {{ row.content }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" text @click="openVersions(row)">版本历史</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 编辑弹窗 -->
    <el-dialog v-model="editOpen" title="编辑提示词" width="620px" destroy-on-close>
      <template v-if="editing">
        <div class="bf-muted" style="margin-bottom: 10px">{{ editing.name }} · {{ editing.key }} · 当前 v{{ editing.versions.length }}</div>
        <div class="bf-muted" style="margin-bottom: 6px">模型路由</div>
        <div class="bf-filter" style="margin-bottom: 14px">
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
        <div class="bf-muted" style="margin-bottom: 6px">提示词内容</div>
        <el-input v-model="content" type="textarea" :rows="10" maxlength="4000" show-word-limit />
      </template>
      <template #footer>
        <el-button @click="editOpen = false">取消</el-button>
        <el-button type="primary" :loading="editBusy" @click="doSave">保存（立即生效，无需发版）</el-button>
      </template>
    </el-dialog>

    <!-- 版本历史 + 一键回滚 -->
    <el-dialog v-model="versionOpen" title="版本历史与一键回滚" width="680px" destroy-on-close>
      <template v-if="versionItem">
        <div class="bf-muted" style="margin-bottom: 10px">{{ versionItem.name }} · 共 {{ versionItem.versions.length }} 个版本，可回滚到任意历史版本（M11-04）</div>
        <div v-for="v in [...versionItem.versions].reverse()" :key="v.version" class="bf-card" style="margin-bottom: 10px">
          <div class="bf-row" style="justify-content: space-between">
            <div>
              <span class="bf-tag" style="margin-right: 8px">v{{ v.version }}</span>
              <span class="bf-tag">{{ v.model }}</span>
            </div>
            <div class="bf-muted">{{ v.updatedAt }} · {{ v.operator }}</div>
          </div>
          <div class="bf-muted" style="margin-top: 8px; line-height: 1.6; white-space: pre-wrap">{{ v.content }}</div>
          <div style="margin-top: 10px; text-align: right">
            <el-button v-if="v.version !== versionItem.versions.length" size="small" text type="warning" @click="doRollback(v)">
              回滚到此版本
            </el-button>
          </div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>
