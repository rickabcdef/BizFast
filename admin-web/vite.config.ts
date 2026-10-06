import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// 独立运营管理后台（V2.2：独立 Web / 独立域名 / 独立构建产物）
export default defineConfig({
  base: '/admin/',
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port: 8089,
    host: '0.0.0.0',
    // 开发态把 /api 反代到后端（生产由 nginx 反代，见 infra/nginx.conf）。
    // 后端地址可用 VITE_PROXY_TARGET 覆盖，默认本地 8077。
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8077',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1500
  }
})
