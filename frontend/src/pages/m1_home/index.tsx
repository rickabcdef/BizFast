import { useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import Segmented from '@/components/Segmented'
import CityPicker from '@/components/CityPicker'
import ErrorTip from '@/components/ErrorTip'
import { startDiagnose } from '@/services/repo'
import { useAppStore } from '@/store'
import './index.scss'

// M1 首屏与启动 | 负责人: D | 优先级: P0
const CAPITAL_OPTIONS = [
  { label: '1万以下', value: 1 },
  { label: '1–5万', value: 2 },
  { label: '5–20万', value: 3 },
  { label: '20万以上', value: 4 }
]
const TIME_OPTIONS = [
  { label: '兼职（每天约2小时）', value: 2 },
  { label: '全职（每天8小时以上）', value: 8 }
]

export default function M1Home() {
  const [capital, setCapital] = useState<number | null>(null)
  const [dailyHours, setDailyHours] = useState<number | null>(null)
  const [city, setCity] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const setTaskId = useAppStore((s) => s.setTaskId)
  const setInput = useAppStore((s) => s.setInput)

  const ready = capital !== null && dailyHours !== null && city !== ''

  const missing: string[] = []
  if (capital === null) missing.push('启动资金')
  if (dailyHours === null) missing.push('每日时间')
  if (city === '') missing.push('所在城市')

  const onSubmit = async () => {
    if (!ready) {
      Taro.showToast({ title: `请先选择：${missing.join('、')}`, icon: 'none' })
      return
    }
    setLoading(true)
    setError('')
    try {
      const { taskId } = await startDiagnose({ capital: capital!, dailyHours: dailyHours!, city })
      setInput({ capital: capital!, dailyHours: dailyHours!, city })
      setTaskId(taskId)
      Taro.navigateTo({ url: `/pages/m2_diagnose/index?taskId=${taskId}` })
    } catch (e: any) {
      setError(e?.message || '服务开小差了，请重试')
      setLoading(false)
    }
  }

  return (
    <View className='page m1-home'>
      <View className='m1-hero'>
        <Text className='m1-title'>告诉我三个信息，30 分钟给你能开干的生意方案</Text>
        <View className='m1-guest'>
          <Text className='bf-tag'>游客模式</Text>
          <Text className='bf-muted'>无需登录，三步拿方案</Text>
        </View>
      </View>

      <View className='bf-card'>
        <Text className='bf-card__title'>启动资金</Text>
        <Segmented
          options={CAPITAL_OPTIONS}
          value={capital}
          onChange={(v) => setCapital(v as number)}
          columns={2}
        />
      </View>

      <View className='bf-card'>
        <Text className='bf-card__title'>每天可投入时间</Text>
        <Segmented
          options={TIME_OPTIONS}
          value={dailyHours}
          onChange={(v) => setDailyHours(v as number)}
          columns={2}
        />
      </View>

      <View className='bf-card'>
        <Text className='bf-card__title'>所在城市</Text>
        <CityPicker value={city} onChange={setCity} />
      </View>

      {error && <ErrorTip message={error} onRetry={onSubmit} />}

      <View
        className={`bf-btn m1-submit ${ready && !loading ? '' : 'bf-btn--disabled'}`}
        onClick={() => !loading && onSubmit()}
      >
        {loading ? '正在为你诊断…' : '帮我找生意'}
      </View>
    </View>
  )
}
