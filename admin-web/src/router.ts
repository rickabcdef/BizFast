import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/store/auth'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: '登录', sub: '独立 Web · 强制二次验证 · 不共用用户端登录态' }
  },
  {
    path: '/',
    component: () => import('@/components/Layout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: '/dashboard' },
      { path: 'dashboard', name: 'dashboard', component: () => import('@/views/DashboardView.vue'), meta: { title: '数据看板', sub: '实时监控产品核心指标 · 数据延迟 ≤ 5 分钟', perm: 'dashboard' } },
      { path: 'users', name: 'users', component: () => import('@/views/UsersView.vue'), meta: { title: '用户管理', sub: '用户查询、会员统计、风控标记与数据导出', perm: 'users' } },
      { path: 'orders', name: 'orders', component: () => import('@/views/OrdersView.vue'), meta: { title: '订单管理', sub: '全部订单查询、退款处理、对账导出、异常告警', perm: 'orders' } },
      { path: 'opportunities', name: 'opportunities', component: () => import('@/views/OpportunitiesView.vue'), meta: { title: '商机库', sub: '管理商机数据与上下架——修改后 5 分钟内对用户端生效', perm: 'opps' } },
      { path: 'prompts', name: 'prompts', component: () => import('@/views/PromptsView.vue'), meta: { title: '提示词配置', sub: 'AI 提示词与模型路由——保存即生效，支持版本历史与一键回滚', perm: 'prompts' } },
      { path: 'reviews', name: 'reviews', component: () => import('@/views/ReviewsView.vue'), meta: { title: '内容审核', sub: '审核工作台：批量处理 / 申诉复核 / 一键下架', perm: 'reviews' } },
      { path: 'roles', name: 'roles', component: () => import('@/views/RolesView.vue'), meta: { title: '权限管理', sub: '四角色权限：管理员 / 运营 / 客服 / 财务（最小权限 + 审计留痕）', perm: 'roles' } },
      { path: 'audit', name: 'audit', component: () => import('@/views/AuditView.vue'), meta: { title: '审计日志', sub: '关键操作全程留痕 · 保留 ≥ 180 天 · 不可篡改', perm: 'audit' } },
      { path: 'ops', name: 'ops', component: () => import('@/views/OpsView.vue'), meta: { title: '运营位配置', sub: '推荐位 / 弹窗 / 优惠券——配置后实时生效', perm: 'ops' } },
      { path: 'export', name: 'export', component: () => import('@/views/ExportView.vue'), meta: { title: '数据导出', sub: '导出中心：单次 ≤ 10 万条（CSV / JSON）', perm: 'export' } }
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
