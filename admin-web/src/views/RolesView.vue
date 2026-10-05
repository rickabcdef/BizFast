<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getAdminRoles,
  saveAdminRole,
  type RoleItem,
  type AdminSession,
  type RolePerm
} from '@/api/adminApi'
import { useAuthStore } from '@/store/auth'

const auth = useAuthStore()
const items = ref<RoleItem[]>([])
const notice = ref('')
const loading = ref(true)

const load = async () => {
  loading.value = true
  try {
    const d = await getAdminRoles()
    items.value = d.items
    notice.value = d.notice
  } finally {
    loading.value = false
  }
}

onMounted(load)

const editOpen = ref(false)
const editing = ref<RoleItem | null>(null)

const openEdit = (r: RoleItem) => {
  editing.value = JSON.parse(JSON.stringify(r)) as RoleItem
  editOpen.value = true
}

const isLocked = (p: RolePerm) => editing.value?.role === 'admin' && (p.key === 'roles' || p.key === 'audit')

const toggle = (p: RolePerm, v: boolean) => {
  if (!editing.value) return
  if (isLocked(p)) {
    ElMessage.warning('管理员基础权限不可关闭（防锁死）')
    return
  }
  p.enabled = v
}

const doSave = async () => {
  if (!editing.value) return
  const r = await saveAdminRole(auth.session as AdminSession, editing.value.role, editing.value.perms)
  editOpen.value = false
  ElMessage.success('权限已保存（操作人已记录审计日志）')
  void load()
}
</script>

<template>
  <div>
    <el-alert v-if="notice" type="success" :closable="false" show-icon style="margin-bottom: 14px" :title="notice" />

    <div class="bf-card">
      <el-table v-loading="loading" :data="items" style="width: 100%">
        <el-table-column label="角色" width="110">
          <template #default="{ row }">
            <span class="bf-grad-text" style="font-weight: 700">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="职责说明" min-width="220" />
        <el-table-column label="权限数" width="90">
          <template #default="{ row }">{{ row.perms.filter((p: RolePerm) => p.enabled).length }} / {{ row.perms.length }}</template>
        </el-table-column>
        <el-table-column label="已启用权限" min-width="240">
          <template #default="{ row }">
            <span v-for="p in row.perms.filter((x: RolePerm) => x.enabled)" :key="p.key" class="bf-tag" style="margin: 2px 6px 2px 0">
              {{ p.label }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="openEdit(row)">配置</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="editOpen" title="角色权限配置" width="620px" destroy-on-close>
      <template v-if="editing">
        <div style="margin-bottom: 12px">
          <span class="bf-grad-text" style="font-weight: 700; font-size: 16px">{{ editing.name }}</span>
          <span class="bf-muted" style="margin-left: 10px">{{ editing.description }}</span>
        </div>
        <div class="bf-row" style="flex-wrap: wrap; gap: 16px">
          <div v-for="p in editing.perms" :key="p.key" style="display: flex; align-items: center; gap: 8px; min-width: 150px">
            <el-switch :model-value="p.enabled" :disabled="isLocked(p)" @change="(v: boolean) => toggle(p, v)" />
            <span>{{ p.label }}</span>
          </div>
        </div>
      </template>
      <template #footer>
        <el-button @click="editOpen = false">取消</el-button>
        <el-button type="primary" @click="doSave">保存（记录操作人）</el-button>
      </template>
    </el-dialog>
  </div>
</template>
