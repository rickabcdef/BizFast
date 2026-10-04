import { defineConfig } from '@tarojs/cli'
import path from 'path'
import devConfig from './dev'
import prodConfig from './prod'

// Taro 编译配置：网页版(H5) 为代码地基，可编译 微信小程序 / App(RN) / 鸿蒙。
export default defineConfig(async (merge, { command, mode }) => {
  const baseConfig = {
    projectName: 'bizfast-frontend',
    date: '2026-10-04',
    designWidth: 750,
    deviceRatio: {
      640: 2.34 / 2,
      750: 1,
      828: 1.81 / 2
    },
    sourceRoot: 'src',
    outputRoot: 'dist',
    alias: {
      '@': path.resolve(__dirname, '..', 'src')
    },
    plugins: [],
    defineConstants: {
      // 后端 API 基址由各端环境变量注入；默认走 Web 基址
      API_BASE: JSON.stringify(process.env.API_BASE || '/api'),
      // 无后端联调时启用前端 Mock 数据；生产构建请设 USE_MOCK=false
      USE_MOCK: JSON.stringify(process.env.USE_MOCK !== 'false')
    },
    copy: {
      patterns: [],
      options: {}
    },
    framework: 'react',
    compiler: 'webpack5',
    cache: {
      enable: false
    },
    mini: {
      postcss: { autoprefixer: { enable: true }, cssModules: { enable: false } }
    },
    h5: {
      publicPath: '/',
      staticDirectory: 'static',
      postcss: { autoprefixer: { enable: true }, cssModules: { enable: false } },
      esnextModules: ['zustand']
    },
    rn: {
      appName: 'BizFast',
      postcss: { cssModules: { enable: false } }
    }
  }
  if (process.env.NODE_ENV === 'development') {
    return merge({}, baseConfig, devConfig)
  }
  return merge({}, baseConfig, prodConfig)
})
