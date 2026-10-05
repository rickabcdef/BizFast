import { defineStore } from 'pinia'
import {
  getAdminSession,
  setAdminSession,
  clearAdminSession,
  type AdminSession
} from '@/api/adminApi'

// 独立会话（与用户端登录态完全隔离，token 存储独立 key）
export const useAuthStore = defineStore('auth', {
  state: () => ({
    session: getAdminSession() as AdminSession | null
  }),
  getters: {
    isLoggedIn: (s) => !!s.session,
    role: (s) => s.session?.role || 'admin'
  },
  actions: {
    setSession(session: AdminSession) {
      this.session = session
      setAdminSession(session)
    },
    logout() {
      this.session = null
      clearAdminSession()
    }
  }
})
