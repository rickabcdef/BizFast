<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/store/auth'
import { ROLE_NAME } from '@/api/adminApi'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const menus = [
  { path: '/dashboard', label: '数据看板', icon: 'DataLine', perm: 'dashboard' },
  { path: '/users', label: '用户管理', icon: 'User', perm: 'users' },
  { path: '/orders', label: '订单管理', icon: 'Tickets', perm: 'orders' },
  { path: '/opportunities', label: '商机库', icon: 'Suitcase', perm: 'opps' },
  { path: '/prompts', label: '提示词配置', icon: 'EditPen', perm: 'prompts' },
  { path: '/reviews', label: '内容审核', icon: 'DocumentChecked', perm: 'reviews' },
  { path: '/roles', label: '权限管理', icon: 'Lock', perm: 'roles' },
  { path: '/audit', label: '审计日志', icon: 'Notebook', perm: 'audit' },
  { path: '/ops', label: '运营位配置', icon: 'Bell', perm: 'ops' },
  { path: '/export', label: '数据导出', icon: 'Download', perm: 'export' }
]

const allowed = computed(() =>
  menus.filter((m) => auth.role === 'admin' || PERM_ALLOW[auth.role]?.includes(m.perm))
)

const PERM_ALLOW: Record<string, string[]> = {
  operator: ['dashboard', 'opps', 'prompts', 'reviews', 'ops'],
  support: ['users', 'orders'],
  finance: ['orders', 'export']
}

const userName = computed(() => auth.session?.name || '')
const roleName = computed(() => ROLE_NAME[auth.role])

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
  <div class="bf-layout">
    <aside class="bf-aside">
      <div class="bf-aside__brand">
        生意快启
        <div class="bf-aside__sub">运营管理后台 · 独立 Web（V2.2）</div>
      </div>
      <nav class="bf-menu">
        <router-link v-for="m in allowed" :key="m.path" :to="m.path" class="bf-menu__item" :class="{ 'is-active': route.path === m.path }">
          <el-icon><component :is="m.icon" /></el-icon>
          <span>{{ m.label }}</span>
        </router-link>
      </nav>
      <div class="bf-aside__foot">
        安全要求：独立域名 / 二次验证 / 不共用用户端登录态 / 审计留痕
      </div>
    </aside>
    <main class="bf-main">
      <header class="bf-header">
        <div class="bf-header__title">{{ route.meta.title }}</div>
        <div class="bf-header__right">
          <span class="bf-header__user">
            <el-icon><UserFilled /></el-icon>
            {{ userName }} · {{ roleName }}
          </span>
          <el-button size="small" text @click="doLogout">退出</el-button>
        </div>
      </header>
      <section class="bf-content">
        <router-view />
      </section>
    </main>
  </div>
</template>
