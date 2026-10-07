import { useEffect, useState } from 'react'
import { View, Text } from '@tarojs/components'
import Loading from '@/components/Loading'
import ErrorTip from '@/components/ErrorTip'
import { getShareStats } from '@/services/repo'
import type { ShareStats } from '@/types'
import './share.scss'

// M5-04 分享转化与裂变（后台呈现）| 负责人: D | 对齐 UI 切图 V5.0 第 19 页
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
  const totalClicks = rows.reduce((n, r) => n + (r.clicks || 0), 0)
  const shareRate = Math.round((summary?.shareRate ?? 0) * 100)

  return (
    <View className='m11-share'>
      <Text className='m11-share__h'>📈 分享转化与裂变</Text>
      <Text className='m11-share__sub'>看转化率，不看打开次数 · 数据延迟 ≤ 5 分钟（M5-04 · 负责人 D）</Text>

      {loading && <Loading />}
      {error && <ErrorTip message={error} onRetry={load} />}

      {!loading && !error && (
        <View>
          {/* 4 个核心 KPI */}
          <View className='m11-share__kpis'>
            <View className='m11-kpi'>
              <Text className='m11-kpi__label'>分享次数</Text>
              <Text className='m11-kpi__val'>{summary?.shares ?? 0}</Text>
            </View>
            <View className='m11-kpi'>
              <Text className='m11-kpi__label'>带来注册</Text>
              <Text className='m11-kpi__val'>{summary?.registers ?? 0}</Text>
            </View>
            <View className='m11-kpi'>
              <Text className='m11-kpi__label'>带来付费</Text>
              <Text className='m11-kpi__val m11-kpi__val--ok'>{summary?.pays ?? 0}</Text>
            </View>
            <View className='m11-kpi'>
              <Text className='m11-kpi__label'>分享率</Text>
              <Text className='m11-kpi__val'>{shareRate}%</Text>
            </View>
          </View>

          {/* 各渠道转发明细 */}
          <View className='m11-card'>
            <Text className='m11-card__h'>各渠道转发明细</Text>
            <View className='m11-table'>
              <View className='m11-tr m11-tr--head'>
                <Text className='m11-th'>渠道</Text>
                <Text className='m11-th m11-th--num'>点击</Text>
                <Text className='m11-th m11-th--num'>占比</Text>
              </View>
              {rows.length === 0 ? (
                <View className='m11-tr'>
                  <Text className='m11-td' style='width:100%'>暂无分享数据</Text>
                </View>
              ) : (
                rows.map((r) => (
                  <View key={r.channel} className='m11-tr'>
                    <Text className='m11-td'>{r.channel}</Text>
                    <Text className='m11-td m11-td--num'>{r.clicks}</Text>
                    <Text className='m11-td m11-td--num'>
                      {totalClicks ? Math.round(((r.clicks || 0) / totalClicks) * 100) : 0}%
                    </Text>
                  </View>
                ))
              )}
            </View>
          </View>
        </View>
      )}
    </View>
  )
}
