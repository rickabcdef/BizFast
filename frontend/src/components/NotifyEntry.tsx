import { useEffect, useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { getUnread } from '@/services/aApi'
import './NotifyEntry.scss'

/**
 * 消息中心入口（M9-01）：带未读红点。
 * 无后端 / 未登录时静默降级为 0，不打断主流程。
 */
export default function NotifyEntry({ refreshKey = 0 }: { refreshKey?: number }) {
  const [unread, setUnread] = useState(0)

  useEffect(() => {
    let alive = true
    getUnread()
      .then((d) => {
        if (alive) setUnread(d.unread)
      })
      .catch(() => {
        if (alive) setUnread(0)
      })
    return () => {
      alive = false
    }
  }, [refreshKey])

  return (
    <View
      className='bf-notify'
      onClick={() => Taro.navigateTo({ url: '/pages/m9_notify/index' })}
    >
      <Text className='bf-notify__icon'>🔔</Text>
      <Text className='bf-notify__label'>消息</Text>
      {unread > 0 && (
        <Text className='bf-notify__dot'>{unread > 99 ? '99+' : String(unread)}</Text>
      )}
    </View>
  )
}
