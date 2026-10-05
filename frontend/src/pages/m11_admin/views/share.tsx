import { useEffect, useState } from 'react'
import { View, Text } from '@tarojs/components'
import Loading from '@/components/Loading'
import ErrorTip from '@/components/ErrorTip'
import { getShareStats } from '@/services/repo'
import type { ShareStats } from '@/types'

// M8-04 分享数据回收（按渠道转化）| 负责人: D | 在运营后台呈现
export default function ShareView() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [stats, setStats] = useState<ShareStats | null>(null)

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      setStats(await getShareStats())
    } catch (e: any) {
      setError(e?.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const summary = stats?.summary
  const rows = stats?.rows || []

  return (
    <View>
      <Text className='m11-modal__h'>分享转化概览（M8-04 · 负责人 D）</Text>
      {loading && <Loading />}
      {error && <ErrorTip message={error} onRetry={load} />}
      {!loading && !error && (
        <View className='bf-card'>
          <View className='bf-row m11-sum'>
            <Text>分享 {summary?.shares ?? 0}</Text>
            <Text>注册 {summary?.registers ?? 0}</Text>
            <Text>付费 {summary?.pays ?? 0}</Text>
            <Text>分享率 {Math.round((summary?.shareRate ?? 0) * 100)}%</Text>
          </View>
          <View className='bf-list'>
            {rows.map((r) => (
              <View key={r.channel} className='bf-list__item'>
                <Text>{r.channel}</Text>
                <Text className='bf-muted'>点击 {r.clicks}</Text>
              </View>
            ))}
          </View>
        </View>
      )}
    </View>
  )
}
