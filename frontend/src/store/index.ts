// 全局状态（Zustand）：用户信息、当前诊断任务、订单进度。
// 游客可免登录；注册用户多端同步（见 docs/data-model.md）。
import { create } from 'zustand'
import Taro from '@tarojs/taro'
import type { Plan, StartupInput, UserProfile } from '@/types'

interface AppState {
  token: string | null
  plan: Plan
  user: UserProfile | null
  input: StartupInput | null
  taskId: string | null
  orderId: string | null
  setToken: (t: string | null) => void
  setPlan: (p: Plan) => void
  setUser: (u: UserProfile | null) => void
  setInput: (i: StartupInput) => void
  setTaskId: (id: string | null) => void
  setOrderId: (id: string | null) => void
  logout: () => void
}

export const useAppStore = create<AppState>((set) => ({
  token: Taro.getStorageSync('bf_token') || null,
  plan: (Taro.getStorageSync('bf_plan') as Plan) || 'none',
  user: Taro.getStorageSync('bf_user') || null,
  // 最近一次的三要素要跨刷新保留：M3-08「重新诊断」需要在刷新后仍能取回原条件
  input: (Taro.getStorageSync('bf_input') as StartupInput) || null,
  taskId: null,
  orderId: null,
  setToken: (t) => {
    if (t) Taro.setStorageSync('bf_token', t)
    else Taro.removeStorageSync('bf_token')
    set({ token: t })
  },
  setPlan: (p) => {
    Taro.setStorageSync('bf_plan', p)
    set({ plan: p })
  },
  setUser: (u) => {
    if (u) Taro.setStorageSync('bf_user', u)
    else Taro.removeStorageSync('bf_user')
    set({ user: u, plan: u ? u.plan : 'none' })
  },
  setInput: (i) => {
    Taro.setStorageSync('bf_input', i)
    set({ input: i })
  },
  setTaskId: (id) => set({ taskId: id }),
  setOrderId: (id) => set({ orderId: id }),
  logout: () => {
    Taro.removeStorageSync('bf_token')
    Taro.removeStorageSync('bf_user')
    Taro.removeStorageSync('bf_input')
    set({ token: null, user: null, plan: 'none', input: null, taskId: null, orderId: null })
  }
}))

export default useAppStore
