import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/store/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { title: '登录' } },
  {
    path: '/',
    component: () => import('@/components/Layout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: '/dashboard' },
      { path: 'dashboard', name: 'dashboard', component: () => import('@/views/DashboardView.vue'), meta: { title: '数据看板', perm: 'dashboard' } },
      { path: 'users', name: 'users', component: () => import('@/views/UsersView.vue'), meta: { title: '用户管理', perm: 'users' } },
      { path: 'orders', name: 'orders', component: () => import('@/views/OrdersView.vue'), meta: { title: '订单管理', perm: 'orders' } },
      { path: 'opportunities', name: 'opportunities', component: () => import('@/views/OpportunitiesView.vue'), meta: { title: '商机库', perm: 'opps' } },
      { path: 'prompts', name: 'prompts', component: () => import('@/views/PromptsView.vue'), meta: { title: '提示词', perm: 'prompts' } },
      { path: 'reviews', name: 'reviews', component: () => import('@/views/ReviewsView.vue'), meta: { title: '内容审核', perm: 'reviews' } },
      { path: 'roles', name: 'roles', component: () => import('@/views/RolesView.vue'), meta: { title: '权限管理', perm: 'roles' } },
      { path: 'audit', name: 'audit', component: () => import('@/views/AuditView.vue'), meta: { title: '审计日志', perm: 'audit' } },
      { path: 'ops', name: 'ops', component: () => import('@/views/OpsView.vue'), meta: { title: '运营位配置', perm: 'ops' } },
      { path: 'export', name: 'export', component: () => import('@/views/ExportView.vue'), meta: { title: '数据导出', perm: 'export' } }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

// 登录守卫：独立登录态 + 按角色最小权限拦截（越权操作拦截）
router.beforeEach((to) => {
  const auth = useAuthStore()
  document.title = to.meta.title ? `${to.meta.title} · 生意快启后台` : '生意快启 · 运营管理后台'
  if (to.meta.requiresAuth && !auth.isLoggedIn) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.meta.perm && auth.isLoggedIn) {
    const perm = to.meta.perm as string
    const allowed = auth.role === 'admin' ? true : PERM_MAP[auth.role]?.includes(perm)
    if (!allowed) return { name: 'dashboard' }
  }
  if (to.name === 'login' && auth.isLoggedIn) return { path: '/' }
  return true
})

// 角色 → 功能权限（最小权限原则）
const PERM_MAP: Record<string, string[]> = {
  operator: ['dashboard', 'opps', 'prompts', 'reviews', 'ops'],
  support: ['users', 'orders', 'refund'],
  finance: ['orders', 'refund', 'export']
}

export default router
