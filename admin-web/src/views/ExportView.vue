<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  exportCenterData,
  downloadText,
  type AdminSession
} from '@/api/adminApi'
import { useAuthStore } from '@/store/auth'

const auth = useAuthStore()
const busy = ref(false)
const result = ref('')

const KINDS = [
  { value: 'users', label: '用户数据', desc: '用户 ID / 手机号 / 会员状态 / 消费 / 来源渠道' },
  { value: 'orders', label: '订单数据', desc: '订单号 / 金额 / 状态 / 渠道 / 异常标记' },
  { value: 'deliveries', label: '交付数据', desc: '启动包订单 / 文件数 / 生成状态' },
  { value: 'events', label: '埋点事件', desc: '关键节点埋点（模块_动作_结果）' }
] as const

const format = ref<'csv' | 'json'>('csv')

const doExport = async (kind: (typeof KINDS)[number]['value']) => {
  busy.value = true
  result.value = ''
  try {
    const r = await exportCenterData(auth.session as AdminSession, kind, format.value)
    downloadText(r.fileName, r.content)
    result.value = r.message
    ElMessage.success(`已生成并下载 ${r.fileName}`)
  } catch (e: any) {
    ElMessage.error(e?.message || '导出失败')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div>
    <div class="bf-card">
      <div class="bf-row" style="justify-content: space-between; margin-bottom: 14px">
        <div class="bf-card__title">数据导出中心</div>
        <el-radio-group v-model="format">
          <el-radio-button value="csv">CSV</el-radio-button>
          <el-radio-button value="json">JSON</el-radio-button>
        </el-radio-group>
      </div>
      <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px">
        <div v-for="k in KINDS" :key="k.value" class="bf-card" style="margin-bottom: 0">
          <div style="font-weight: 600">{{ k.label }}</div>
          <div class="bf-muted" style="margin: 6px 0 12px">{{ k.desc }}</div>
          <el-button type="primary" plain :loading="busy" @click="doExport(k.value)">导出 {{ format.toUpperCase() }}</el-button>
        </div>
      </div>
      <div v-if="result" class="bf-note">
        <el-tag type="success">{{ result }}</el-tag>
      </div>
      <div class="bf-note bf-muted">
        M11-11（P2）：用户 / 订单 / 交付 / 埋点数据批量导出，单次可导出 ≤ 10 万条；导出操作写入审计日志。
      </div>
    </div>
  </div>
</template>
