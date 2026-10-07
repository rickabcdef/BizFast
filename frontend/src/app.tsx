import { PropsWithChildren } from 'react'
import { useLaunch } from '@tarojs/taro'

import './app.scss'
import { captureInviterCode } from '@/services/api'

function App({ children }: PropsWithChildren) {
  useLaunch(() => {
    // 冷启动：上报性能、初始化平台适配（见 utils/platform.ts）
    console.log('BizFast App launched.')
    // M0-04：分享链接落地的第一时间把邀请码暂存，登录时自动绑定邀请关系
    captureInviterCode()
  })

  return children
}

export default App
