import { PropsWithChildren } from 'react'
import { useLaunch } from '@tarojs/taro'

import './app.scss'

function App({ children }: PropsWithChildren) {
  useLaunch(() => {
    // 冷启动：上报性能、初始化平台适配（见 utils/platform.ts）
    console.log('BizFast App launched.')
  })

  return children
}

export default App
