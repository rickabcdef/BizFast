import { useState, useEffect } from 'react'
import { View, Text } from '@tarojs/components'
import Loading from '@/components/Loading'
import ErrorTip from '@/components/ErrorTip'
import { getShareStats } from '@/services/repo'
import type { ShareStatsRow } from '@/types'
import './index.scss'

// M11 运营管理后台（D 负责分享转化部分 M8-04）| 负责人: B+D | 优先级: P1
export default function M11Admin() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [rows, setRows] = useState<ShareStatsRow[]>([])

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      setRows(await getShareStats())
    } catch (e: any) {
      setError(e?.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const total = rows.reduce(
    (a, r) => ({
      clicks: a.clicks + r.clicks,
      registers: a.registers + r.registers,
      pays: a.pays + r.pays
    }),
    { clicks: 0, registers: 0, pays: 0 }
  )

  return (
    <View className='page m11-admin'>
      <Text className='bf-card__title'>分享转化概览（M8-04 · 负责人 B+D）</Text>
      {loading && <Loading />}
      {error && <ErrorTip message={error} onRetry={load} />}
      {!loading && !error && (
        <View className='bf-card'>
          <View className='bf-row m11-sum'>
            <Text>点击 {total.clicks}</Text>
            <Text>注册 {total.registers}</Text>
            <Text>付费 {total.pays}</Text>
          </View>
          <View className='bf-list'>
            {rows.map((r) => (
              <View key={r.channel} className='bf-list__item'>
                <Text>{r.channel}</Text>
                <Text className='bf-muted'>
                  点击{r.clicks} · 注册{r.registers} · 付费{r.pays}
                </Text>
              </View>
            ))}
          </View>
        </View>
      )}
      <Text className='bf-muted'>运营后台其余模块（用户 / 订单 / 交付物管理）由研发 B 负责。</Text>
    </View>
  )
}
