import type { UserConfig } from '@tarojs/cli'

export default {
  mini: {},
  h5: {
    /**
     * 生产环境 H5 由 nginx 反代 /api 到后端（见 infra/nginx.conf）。
     */
  }
} as Partial<UserConfig>
