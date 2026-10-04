import type { UserConfig } from '@tarojs/cli'

export default {
  logger: {
    quiet: false,
    stats: true
  },
  mini: {},
  h5: {}
} as Partial<UserConfig>
