export default {
  mini: {},
  h5: {
    /**
     * 生产环境 H5 由 nginx 反向代理 /api 到后端（见 infra/nginx.conf）。
     *
     * webpackChain：关闭「作用域提升」(ModuleConcatenationPlugin / concatenateModules)。
     *
     * 背景：Taro 4.0 + webpack 5 的 H5 生产构建在开启作用域提升时，页面 chunk 里
     * 对 react/jsx-runtime 的引用会被提升/内联成 undefined，运行时报
     *   TypeError: Cannot read properties of undefined (reading 'jsxs')
     * 整页白屏（开发模式与关闭提升后均不复现，已实测）。
     * 关闭它只牺牲一点运行性能，压缩（Terser）仍开启，产物体积基本不变。
     */
    webpackChain(chain) {
      chain.optimization.concatenateModules(false)
    }
  }
}
