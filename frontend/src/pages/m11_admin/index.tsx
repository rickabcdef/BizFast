import { useState } from 'react'
import { View, Text, Input } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { adminLogin, type AdminRole } from '@/services/bApi'
import DashboardView from './views/dashboard'
import UsersView from './views/users'
import OrdersView from './views/orders'
import OpportunitiesView from './views/opportunities'
import PromptsView from './views/prompts'
import ReviewsView from './views/reviews'
import RolesView from './views/roles'
import AuditView from './views/audit'
import ShareView from './views/share'
import './index.scss'

// m11_admin 运营管理后台 | 负责人: B+D | 优先级: P1
// 需求点：
//   M11-01 用户管理（列表/详情/会员状态/消费记录，筛选与导出）
//   M11-02 订单管理（查看/处理退款/核对支付，导出对账表）
//   M11-03 商机库管理（P0：商机模板/行业数据/案例库，批量导入与审核）
//   M11-04 提示词配置（在线配置 AI 提示词与模型路由，改后无需发版生效）
//   M11-05 数据看板（转化率/付费单数/收入/退款率，数据延迟 ≤ 5 分钟）
//   M11-06 内容审核（敏感词与合规审核，违规拦截率 ≥ 99%）
//   M11-07 权限管理（管理员/运营/客服分级，操作均记录操作人）
//   M11-08 审计日志（关键操作留痕，日志保留 ≥ 180 天）
// 分享转化（M8-04）为研发 D 的模块，作为独立 Tab 保留。

type TabKey = 'dashboard' | 'users' | 'orders' | 'opportunities' | 'reviews' | 'prompts' | 'roles' | 'audit' | 'share'

const TABS: { key: TabKey; label: string }[] = [
  { key: 'dashboard', label: '数据看板' },
  { key: 'users', label: '用户管理' },
  { key: 'orders', label: '订单管理' },
  { key: 'opportunities', label: '商机库' },
  { key: 'reviews', label: '内容审核' },
  { key: 'prompts', label: '提示词' },
  { key: 'roles', label: '权限' },
  { key: 'audit', label: '审计日志' },
  { key: 'share', label: '分享转化' }
]

const ROLE_LABEL: Record<AdminRole, string> = {
  admin: '管理员',
  operator: '运营',
  support: '客服'
}

export default function M11Admin() {
  const [tab, setTab] = useState<TabKey>('dashboard')
  // 管理员登录态（token 存本地；生产环境由后端校验并注入密钥）
  const [profile, setProfile] = useState<{ name: string; role: AdminRole } | null>(() => {
    try {
      const p = Taro.getStorageSync('bf_admin_profile')
      return p && p.name ? p : null
    } catch {
      return null
    }
  })
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const doLogin = async () => {
    setBusy(true)
    setErr('')
    try {
      const r = await adminLogin(username, password)
      Taro.setStorageSync('bf_admin_token', r.token)
      Taro.setStorageSync('bf_admin_profile', { name: r.name, role: r.role })
      setProfile({ name: r.name, role: r.role })
    } catch (e: any) {
      setErr(e?.message || '登录失败，请重试')
    } finally {
      setBusy(false)
    }
  }

  const doLogout = () => {
    Taro.removeStorageSync('bf_admin_token')
    Taro.removeStorageSync('bf_admin_profile')
    setProfile(null)
    setUsername('')
    setPassword('')
  }

  // 未登录：管理员登录门（后台为内部角色，无游客入口）
  if (!profile) {
    return (
      <View className='page m11-admin'>
        <View className='m11-login'>
          <Text className='m11-login__logo'>生意快启</Text>
          <Text className='m11-login__title'>运营管理后台</Text>
          <Text className='bf-muted m11-login__sub'>内部系统 · 仅限管理员/运营/客服账号登录</Text>
          <Input
            className='bf-input m11-login__input'
            placeholder='管理员账号'
            value={username}
            onInput={(e) => setUsername(e.detail.value)}
          />
          <Input
            className='bf-input m11-login__input'
            password
            placeholder='密码'
            value={password}
            onInput={(e) => setPassword(e.detail.value)}
          />
          {err && <Text className='m11-login__err'>{err}</Text>}
          <View className={`bf-btn m11-login__btn ${busy ? 'bf-btn--disabled' : ''}`} onClick={() => !busy && doLogin()}>
            {busy ? '正在登录…' : '进入后台'}
          </View>
          <Text className='bf-muted m11-login__foot'>
            演示环境：任意账号密码可进入（开发 Mock）；生产环境密钥走环境变量，绝不进代码库。
          </Text>
        </View>
      </View>
    )
  }

  return (
    <View className='page m11-admin'>
      <View className='bf-row m11-head'>
        <View>
          <Text className='m11-head__title'>运营管理后台</Text>
          <Text className='bf-muted m11-head__sub'>
            {profile.name} · {ROLE_LABEL[profile.role] || profile.role}
          </Text>
        </View>
        <View className='bf-btn bf-btn--sm bf-btn--ghost' onClick={doLogout}>
          退出
        </View>
      </View>

      {/* Tab 导航 */}
      <View className='m11-tabs'>
        {TABS.map((t) => (
          <View
            key={t.key}
            className={`m11-tab ${tab === t.key ? 'is-active' : ''}`}
            onClick={() => setTab(t.key)}
          >
            <Text>{t.label}</Text>
          </View>
        ))}
      </View>

      <View className='m11-body'>
        {tab === 'dashboard' && <DashboardView />}
        {tab === 'users' && <UsersView />}
        {tab === 'orders' && <OrdersView />}
        {tab === 'opportunities' && <OpportunitiesView />}
        {tab === 'reviews' && <ReviewsView />}
        {tab === 'prompts' && <PromptsView />}
        {tab === 'roles' && <RolesView />}
        {tab === 'audit' && <AuditView />}
        {tab === 'share' && <ShareView />}
      </View>
    </View>
  )
}
