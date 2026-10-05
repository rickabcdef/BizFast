export default {
  logger: {
    quiet: false,
    stats: true
  },
  // Taro 4.0 的 webpack5-prebundle 与 webpack 5.9x 存在
  // `finalInputFileSystem._writeVirtualFile is not a function` 兼容问题，
  // 开发态关闭 prebundle（仅影响本地 watch 编译速度，不影响产物与生产构建）。
  prebundle: { enable: false },
  mini: {},
  h5: {}
}
