import { useState } from 'react'
import { View, Text, Slider } from '@tarojs/components'
import Taro from '@tarojs/taro'
import CityPicker from '@/components/CityPicker'
import ErrorTip from '@/components/ErrorTip'
import { getPageParams } from '@/utils/query'
import { startDiagnose } from '@/services/repo'
import type { DiagnoseExtraInput } from '@/services/aApi'
import { useAppStore } from '@/store'
import './index.scss'

// M1 首屏与启动 | 负责人: D | 优先级: P0
// V5.0 UI 切图第 2 页：城市网格 + 启动资金/时间滑块 + 经验选择 + 主按钮（渐变）
// M2-07 补充问答（可选）由 A 在此接入：默认收起，可整体跳过，跳过不影响结果

// 资金滑块：索引 0~3 → 金额档位（与后端 capital 1~4 对应）
const MONEY_LABELS = ['1万以下', '1-5万', '5-20万', '20万以上']
const TIME_LABELS = ['兼职 2h', '半天 4h', '全职 8h+']
const TIME_VALUES = [2, 4, 8] // 对应 dailyHours

// 热门城市网格（V5.0 切图：6 个 + 更多）
const HOT_CITIES = ['上海', '北京', '广州', '深圳', '杭州', '成都']

// 经验选择（V5.0 首屏 2 宫格）
const EXP_OPTIONS: { label: string; value: 'none' | 'some'; emoji: string }[] = [
  { label: '完全没做过', value: 'none', emoji: '🌱' },
  { label: '有过经验', value: 'some', emoji: '👨‍💼' }
]

// M2-07 另外两题补充问答（PRD：接受实体还是线上 / 最在意投入还是回报）
const EXTRA_QUESTIONS: {
  key: keyof DiagnoseExtraInput
  title: string
  options: { label: string; value: string }[]
}[] = [
  {
    key: 'mode',
    title: '你只能做实体还是线上？',
    options: [
      { label: '只能做实体的', value: 'offline' },
      { label: '只能做线上的', value: 'online' },
      { label: '都可以', value: 'both' }
    ]
  },
  {
    key: 'priority',
    title: '你最在意什么？',
    options: [
      { label: '尽量少投入', value: 'cost' },
      { label: '想多赚一点', value: 'profit' },
      { label: '投入回报平衡', value: 'balance' }
    ]
  }
]

export default function M1Home() {
  const lastInput = useAppStore((s) => s.input)
  // M3-08：从「重新诊断」回到首页时带 ?redo=1，用上次的条件预填
  const isRedo = getPageParams().redo === '1'

  const [moneyIdx, setMoneyIdx] = useState<number>(isRedo ? (lastInput?.capital ?? 2) - 1 : 1)
  const [timeIdx, setTimeIdx] = useState<number>(
    isRedo ? Math.max(0, TIME_VALUES.indexOf(lastInput?.dailyHours ?? 8)) : 2
  )
  const [city, setCity] = useState(isRedo ? lastInput?.city ?? '' : '')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [extraOpen, setExtraOpen] = useState(false)
  const [extra, setExtra] = useState<DiagnoseExtraInput>(isRedo ? lastInput?.extra || {} : {})
  const setTaskId = useAppStore((s) => s.setTaskId)
  const setInput = useAppStore((s) => s.setInput)

  const capital = moneyIdx + 1
  const dailyHours = TIME_VALUES[timeIdx]
  const ready = city !== ''
  const extraAnswered = EXTRA_QUESTIONS.some((q) => extra[q.key])

  const onSubmit = async () => {
    if (!ready) {
      Taro.showToast({ title: '请先选择所在城市', icon: 'none' })
      return
    }
    setLoading(true)
    setError('')
    try {
      const payloadExtra: DiagnoseExtraInput = extraAnswered ? extra : { skipped: true }
      const { taskId } = await startDiagnose({
        capital,
        dailyHours,
        city,
        extra: payloadExtra
      })
      setInput({ capital, dailyHours, city, extra: payloadExtra })
      setTaskId(taskId)
      Taro.navigateTo({ url: `/pages/m2_diagnose/index?taskId=${taskId}` })
    } catch (e: any) {
      setError(e?.message || '服务开小差了，请重试')
      setLoading(false)
    }
  }

  return (
    <View className='m1'>
      <View className='m1__header'>
        <Text className='m1__title'>🔍 商机诊断</Text>
        <Text className='m1__sub'>告诉我你的情况，帮你找到合适的小生意</Text>
      </View>

      <View className='bf-card m1__city'>
        <Text className='bf-card__title'>📍 你在哪个城市？</Text>
        <View className='m1__citygrid'>
          {HOT_CITIES.map((c) => (
            <View
              key={c}
              className={`m1__opt ${city === c ? 'is-active' : ''}`}
              onClick={() => setCity(c)}
            >
              <Text className='m1__emoji'>🏙️</Text>
              <Text className='m1__optlabel'>{c}</Text>
            </View>
          ))}
        </View>
        <CityPicker value={city} onChange={setCity} />
      </View>

      <View className='bf-card'>
        <View className='m1__sliderhead'>
          <Text>💰 你能拿出多少启动资金？</Text>
          <Text className='m1__val'>{MONEY_LABELS[moneyIdx]}</Text>
        </View>
        <Slider
          min={0}
          max={3}
          step={1}
          value={moneyIdx}
          activeColor='#165DFF'
          backgroundColor='rgba(255,255,255,0.15)'
          blockColor='#7B61FF'
          blockSize={22}
          onChange={(e: any) => setMoneyIdx(Number(e.detail.value))}
        />
        <View className='m1__scale'>
          {MONEY_LABELS.map((l) => (
            <Text key={l}>{l}</Text>
          ))}
        </View>
      </View>

      <View className='bf-card'>
        <View className='m1__sliderhead'>
          <Text>⏰ 你每天能投入多少时间？</Text>
          <Text className='m1__val'>{TIME_LABELS[timeIdx]}</Text>
        </View>
        <Slider
          min={0}
          max={2}
          step={1}
          value={timeIdx}
          activeColor='#165DFF'
          backgroundColor='rgba(255,255,255,0.15)'
          blockColor='#7B61FF'
          blockSize={22}
          onChange={(e: any) => setTimeIdx(Number(e.detail.value))}
        />
        <View className='m1__scale'>
          {TIME_LABELS.map((l) => (
            <Text key={l}>{l}</Text>
          ))}
        </View>
      </View>

      <View className='bf-card'>
        <Text className='bf-card__title'>💼 你之前有没有做生意的经验？</Text>
        <View className='m1__expgrid'>
          {EXP_OPTIONS.map((o) => (
            <View
              key={o.value}
              className={`m1__opt ${extra.experience === o.value ? 'is-active' : ''}`}
              onClick={() =>
                setExtra((prev) => ({
                  ...prev,
                  experience: prev.experience === o.value ? null : o.value
                }))
              }
            >
              <Text className='m1__emoji'>{o.emoji}</Text>
              <Text className='m1__optlabel'>{o.label}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* ---------- M2-07 补充问答（可选，可跳过） ---------- */}
      <View className='bf-card m1__extra'>
        <View className='bf-row' onClick={() => setExtraOpen(!extraOpen)}>
          <View className='m1__extra__head'>
            <Text className='bf-card__title'>补充问答</Text>
            <Text className='bf-tag m1__extra__badge'>可选</Text>
          </View>
          <Text className='bf-muted m1__extra__toggle'>
            {extraOpen ? '收起 ︿' : '展开 ﹀'}
          </Text>
        </View>
        {!extraOpen && (
          <Text className='bf-muted m1__extra__tip'>
            {extraAnswered
              ? `已填 ${EXTRA_QUESTIONS.filter((q) => extra[q.key]).length} 题，结果会更贴合你`
              : '2 个小问题，填了更准；不填也能直接开始'}
          </Text>
        )}
        {extraOpen && (
          <View className='m1__extra__body'>
            {EXTRA_QUESTIONS.map((q) => (
              <View key={q.key} className='m1__extra__q'>
                <Text className='m1__extra__label'>{q.title}</Text>
                <View className='m1__extra__opts'>
                  {q.options.map((o) => (
                    <Text
                      key={o.value}
                      className={`bf-tag m1__extra__opt ${
                        extra[q.key] === o.value ? 'is-active' : ''
                      }`}
                      onClick={() =>
                        setExtra((prev) => ({
                          ...prev,
                          [q.key]: prev[q.key] === o.value ? undefined : o.value
                        }))
                      }
                    >
                      {o.label}
                    </Text>
                  ))}
                </View>
              </View>
            ))}
          </View>
        )}
      </View>

      {error && <ErrorTip message={error} onRetry={onSubmit} />}

      <View
        className={`m1__submit ${ready && !loading ? '' : 'm1__submit--disabled'}`}
        onClick={() => !loading && onSubmit()}
      >
        <Text className='m1__submit__txt'>{loading ? '正在为你诊断…' : '🔮 帮我找生意'}</Text>
      </View>
      <Text className='m1__note'>预计 1 分钟内出结果，完全免费</Text>

      {/* V5.0 M5-03：今日谈资卡入口（UI 切图第 17 页；免费、可转发，做社交裂变触点） */}
      <View
        className='bf-card m1__talk'
        onClick={() => Taro.navigateTo({ url: '/pages/m12_talk_topic/index' })}
      >
        <View className='bf-row'>
          <Text className='bf-card__title'>💬 今日谈资</Text>
          <Text className='bf-tag bf-tag--accent'>免费</Text>
        </View>
        <Text className='bf-muted m1__talk__sub'>
          每天一条同城赚钱机会速览，饭桌上有话聊、有面子，一键转发给朋友
        </Text>
        <Text className='m1__talk__more'>看看今天的 →</Text>
      </View>
    </View>
  )
}
