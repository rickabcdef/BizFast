<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { adminLoginStep1, adminLoginStep2 } from '@/api/adminApi'
import { useAuthStore } from '@/store/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const step = ref<1 | 2>(1)
const username = ref('')
const password = ref('')
const totp = ref('')
const totpHint = ref('')
const loading = ref(false)

const ACCOUNT_TIPS = [
  'admin / admin123 · 管理员',
  'operator / op123 · 运营',
  'support / sup123 · 客服',
  'finance / fin123 · 财务'
]

const doStep1 = async () => {
  if (!username.value.trim() || !password.value.trim()) {
    ElMessage.warning('请输入账号与密码')
    return
  }
  loading.value = true
  try {
    const r = await adminLoginStep1(username.value, password.value)
    totpHint.value = r.totpHint
    step.value = 2
    ElMessage.success('账号验证通过，请输入二次验证码')
  } catch (e: any) {
    ElMessage.error(e?.message || '登录失败')
  } finally {
    loading.value = false
  }
}

const doStep2 = async () => {
  if (!totp.value.trim()) {
    ElMessage.warning('请输入验证码')
    return
  }
  loading.value = true
  try {
    const session = await adminLoginStep2(username.value, totp.value, totpHint.value)
    auth.setSession(session)
    ElMessage.success(`欢迎回来，${session.name}`)
    router.replace((route.query.redirect as string) || '/dashboard')
  } catch (e: any) {
    ElMessage.error(e?.message || '验证失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="bf-login">
    <div class="bf-login__card">
      <div class="bf-login__title bf-grad-text">生意快启 · 运营后台</div>
      <div class="bf-login__sub">独立 Web 管理后台（Vue3 + Element Plus）· 强制二次验证登录</div>

      <template v-if="step === 1">
        <el-form label-position="top" @submit.prevent="doStep1">
          <el-form-item label="账号">
            <el-input v-model="username" placeholder="请输入后台账号" size="large" />
          </el-form-item>
          <el-form-item label="密码">
            <el-input v-model="password" type="password" show-password placeholder="请输入密码" size="large" @keyup.enter="doStep1" />
          </el-form-item>
          <el-button type="primary" size="large" class="bf-login__btn" :loading="loading" @click="doStep1">
            下一步：二次验证
          </el-button>
        </el-form>
        <div class="bf-login__tip">
          演示账号（四角色）：<br />
          <span v-for="t in ACCOUNT_TIPS" :key="t">{{ t }}<br /></span>
        </div>
      </template>

      <template v-else>
        <el-form label-position="top" @submit.prevent="doStep2">
          <el-form-item label="动态验证码（TOTP / 短信）">
            <el-input v-model="totp" placeholder="6 位验证码" maxlength="6" size="large" @keyup.enter="doStep2" />
          </el-form-item>
          <div class="bf-login__tip">模拟环境验证码：<b class="bf-grad-text">{{ totpHint }}</b>（真实环境由 TOTP / 短信下发）</div>
          <el-button type="primary" size="large" class="bf-login__btn" :loading="loading" @click="doStep2">
            验证并登录
          </el-button>
          <el-button text class="bf-login__btn" @click="step = 1">返回上一步</el-button>
        </el-form>
      </template>
    </div>
  </div>
</template>

<style scoped>
.bf-login__btn {
  width: 100%;
  margin-top: 4px;
}
</style>
