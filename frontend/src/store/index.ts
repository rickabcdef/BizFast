// 全局状态（Zustand）：用户信息、当前诊断任务、订单进度。
// 游客可免登录；注册用户多端同步（见 docs/data-model.md）。
import { create } from 'zustand'
import Taro from '@tarojs/taro'
import type { Plan, StartupInput } from '@/types'

interface AppState {
  token: string | null
  plan: Plan
  input: StartupInput | null
  taskId: string | null
  orderId: string | null
  setToken: (t: string | null) => void
  setPlan: (p: Plan) => void
  setInput: (i: StartupInput) => void
  setTaskId: (id: string | null) => void
  setOrderId: (id: string | null) => void
  logout: () => void
}

export const useAppStore = create<AppState>((set) => ({
  token: Taro.getStorageSync('bf_token') || null,
  plan: (Taro.getStorageSync('bf_plan') as Plan) || 'none',
  input: null,
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
  setInput: (i) => set({ input: i }),
  setTaskId: (id) => set({ taskId: id }),
  setOrderId: (id) => set({ orderId: id }),
  logout: () => {
    Taro.removeStorageSync('bf_token')
    set({ token: null, plan: 'none', taskId: null, orderId: null })
  }
}))

export default useAppStore
