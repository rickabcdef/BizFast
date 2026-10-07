<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/store/auth'
import { ROLE_NAME } from '@/api/adminApi'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

// 菜单分组（对齐 V2.2 切图 13~16 号页面的侧边栏结构，保留 M11 P0-P2 全部入口）
const menuGroups = [
  {
    group: '概览',
    items: [{ path: '/dashboard', label: '数据看板', icon: 'DataLine', perm: 'dashboard' }]
  },
  {
    group: '业务管理',
    items: [
      { path: '/users', label: '用户管理', icon: 'User', perm: 'users' },
      { path: '/orders', label: '订单管理', icon: 'Tickets', perm: 'orders' },
      { path: '/opportunities', label: '商机库', icon: 'Suitcase', perm: 'opps' },
      { path: '/prompts', label: '提示词配置', icon: 'EditPen', perm: 'prompts' },
      { path: '/reviews', label: '内容审核', icon: 'DocumentChecked', perm: 'reviews' }
    ]
  },
  {
    group: '增长与成本',
    items: [
      { path: '/cost', label: '成本监控', icon: 'Money', perm: 'dashboard' },
      { path: '/growth', label: '转化与裂变', icon: 'TrendCharts', perm: 'dashboard' }
    ]
  },
  {
    group: '系统',
    items: [
      { path: '/roles', label: '权限管理', icon: 'Lock', perm: 'roles' },
      { path: '/audit', label: '审计日志', icon: 'Notebook', perm: 'audit' },
      { path: '/ops', label: '运营位配置', icon: 'Bell', perm: 'ops' },
      { path: '/export', label: '数据导出', icon: 'Download', perm: 'export' }
    ]
  }
]

const PERM_ALLOW: Record<string, string[]> = {
  operator: ['dashboard', 'opps', 'prompts', 'reviews', 'ops'],
  support: ['users', 'orders'],
  finance: ['orders', 'export']
}

const allowedGroups = computed(() =>
  menuGroups
    .map((g) => ({
      group: g.group,
      items: g.items.filter((m) => auth.role === 'admin' || PERM_ALLOW[auth.role]?.includes(m.perm))
    }))
    .filter((g) => g.items.length > 0)
)

const userName = computed(() => auth.session?.name || '')
const roleName = computed(() => ROLE_NAME[auth.role] || '')
const avatarChar = computed(() => (userName.value ? userName.value.slice(0, 1) : '管'))

// 顶栏当前时间（对齐切图 13 页顶栏）
const nowText = ref('')
const timer = ref<ReturnType<typeof setInterval> | null>(null)
const fmtNow = () => {
  const d = new Date()
  const week = ['日', '一', '二', '三', '四', '五', '六'][d.getDay()]
  const p = (n: number) => String(n).padStart(2, '0')
  nowText.value = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${week === '日' ? '周日' : '周' + week} ${p(d.getHours())}:${p(d.getMinutes())}`
}
onMounted(() => {
  fmtNow()
  timer.value = setInterval(fmtNow, 30 * 1000)
})
onUnmounted(() => {
  if (timer.value) clearInterval(timer.value)
})

const doLogout = async () => {
  try {
    await ElMessageBox.confirm('确认退出登录？', '退出', { type: 'warning', confirmButtonText: '退出登录', cancelButtonText: '取消' })
    auth.logout()
    router.replace('/login')
  } catch {
    /* 取消 */
  }
}
</script>

<template>
  <div class="admin-layout">
    <aside class="admin-sidebar">
      <div class="admin-logo">
        <div class="logo-text">🚀 生意快启</div>
        <div class="logo-sub">运营管理后台 · 独立 Web（V2.2）</div>
      </div>
      <nav class="admin-menu">
        <template v-for="g in allowedGroups" :key="g.group">
          <div class="admin-menu-group">{{ g.group }}</div>
          <router-link
            v-for="m in g.items"
            :key="m.path"
            :to="m.path"
            class="admin-menu-item"
            :class="{ 'is-active': route.path === m.path }"
          >
            <span class="menu-icon"><el-icon><component :is="m.icon" /></el-icon></span>
            <span>{{ m.label }}</span>
          </router-link>
        </template>
      </nav>
      <div class="admin-sidebar-foot">安全要求：独立域名 / 二次验证 / 不共用用户端登录态 / 审计留痕</div>
    </aside>

    <main class="admin-main">
      <header class="admin-topbar">
        <div>
          <h1>{{ route.meta.title }}</h1>
          <div class="topbar-sub">{{ route.meta.sub }}</div>
        </div>
        <div class="topbar-right">
          <span style="font-size: 13px; color: var(--bf-text-3)">{{ nowText }}</span>
          <div class="admin-user">
            <div class="admin-avatar">{{ avatarChar }}</div>
            <div>
              <div style="font-size: 13px; font-weight: 500">{{ userName }}</div>
              <div style="font-size: 11px; color: var(--bf-text-3)">{{ roleName }}</div>
            </div>
          </div>
          <el-button size="small" text @click="doLogout">退出</el-button>
        </div>
      </header>
      <section class="admin-content">
        <router-view />
      </section>
    </main>
  </div>
</template>
