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
    host: '0.0.0.0'
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1500
  }
})
