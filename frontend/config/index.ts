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
      // 开发态默认开 Mock（没后端也能看页面）；生产态必须显式 USE_MOCK=true 才开。
      // 反过来（生产默认开 Mock）是最危险的配置事故：包发出去全是假数据，
      // 而且页面看起来完全正常，很难被发现，所以这里默认必须是关。
      USE_MOCK: JSON.stringify(
        process.env.USE_MOCK
          ? process.env.USE_MOCK !== 'false'
          : process.env.NODE_ENV === 'development'
      )
    },
    copy: {
      patterns: [],
      options: {}
    },
    framework: 'react',
    compiler: {
      type: 'webpack5',
      // Taro 4.0 的 webpack5-prebundle 与 webpack 5.9x 存在
      // `finalInputFileSystem._writeVirtualFile is not a function` 兼容问题，
      // 关闭 prebundle（不影响产物正确性，仅牺牲一点 watch 首次编译速度）。
      prebundle: { enable: false }
    },
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
