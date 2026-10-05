<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getAdminOps,
  saveAdminOps,
  toggleAdminOps,
  type OpsSlot,
  type AdminSession
} from '@/api/adminApi'
import { useAuthStore } from '@/store/auth'

const auth = useAuthStore()
const items = ref<OpsSlot[]>([])
const notice = ref('')
const loading = ref(true)

const load = async () => {
  loading.value = true
  try {
    const d = await getAdminOps()
    items.value = d.items
    notice.value = d.notice
  } finally {
    loading.value = false
  }
}

onMounted(load)

const TYPE_LABEL: Record<string, string> = { recommend: '首页推荐位', popup: '活动弹窗', coupon: '优惠券' }

const editOpen = ref(false)
const editing = ref<OpsSlot | null>(null)

const openEdit = (o: OpsSlot) => {
  editing.value = { ...o }
  editOpen.value = true
}

const doSave = async () => {
  if (!editing.value) return
  await saveAdminOps(auth.session as AdminSession, editing.value)
  editOpen.value = false
  ElMessage.success('运营位已保存（实时生效）')
  void load()
}

const doToggle = async (o: OpsSlot, enabled: boolean) => {
  const r = await toggleAdminOps(auth.session as AdminSession, o.id, enabled)
  ElMessage.success(r.message)
  void load()
}
</script>

<template>
  <div>
    <el-alert v-if="notice" type="success" :closable="false" show-icon style="margin-bottom: 14px" :title="notice" />

    <div class="bf-card">
      <el-table v-loading="loading" :data="items" style="width: 100%">
        <el-table-column prop="name" label="运营位名称" min-width="180" />
        <el-table-column label="类型" width="110">
          <template #default="{ row }">
            <span class="bf-tag">{{ TYPE_LABEL[row.type] }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" width="160" />
        <el-table-column prop="content" label="内容说明" min-width="200" />
        <el-table-column label="生效时间" width="200">
          <template #default="{ row }">{{ row.startAt }} ~ {{ row.endAt }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <span class="bf-tag" :class="{ 'bf-tag--ok': row.enabled }">{{ row.enabled ? '已启用' : '已停用' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" text :type="row.enabled ? 'danger' : 'success'" @click="doToggle(row, !row.enabled)">
              {{ row.enabled ? '停用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="editOpen" title="编辑运营位" width="560px" destroy-on-close>
      <template v-if="editing">
        <el-form label-width="100px">
          <el-form-item label="运营位名称"><el-input v-model="editing.name" /></el-form-item>
          <el-form-item label="类型">
            <el-select v-model="editing.type" style="width: 100%">
              <el-option v-for="(v, k) in TYPE_LABEL" :key="k" :label="v" :value="k" />
            </el-select>
          </el-form-item>
          <el-form-item label="标题"><el-input v-model="editing.title" /></el-form-item>
          <el-form-item label="内容说明"><el-input v-model="editing.content" type="textarea" :rows="3" /></el-form-item>
          <el-form-item label="开始时间"><el-input v-model="editing.startAt" placeholder="2026-10-01 00:00" /></el-form-item>
          <el-form-item label="结束时间"><el-input v-model="editing.endAt" placeholder="2026-10-31 23:59" /></el-form-item>
        </el-form>
      </template>
      <template #footer>
        <el-button @click="editOpen = false">取消</el-button>
        <el-button type="primary" @click="doSave">保存（实时生效）</el-button>
      </template>
    </el-dialog>
  </div>
</template>
