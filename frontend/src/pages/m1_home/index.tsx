import { useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import Segmented from '@/components/Segmented'
import CityPicker from '@/components/CityPicker'
import ErrorTip from '@/components/ErrorTip'
import { getPageParams } from '@/utils/query'
import { startDiagnose } from '@/services/repo'
import type { DiagnoseExtraInput } from '@/services/aApi'
import { useAppStore } from '@/store'
import './index.scss'

// M1 首屏与启动 | 负责人: D | 优先级: P0
// M2-07 补充问答（可选）由 A 在此接入：默认收起，可整体跳过，跳过不影响结果
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

// M2-07 三个补充问题（PRD：有无相关经验 / 接受实体还是线上 / 最在意投入还是回报）
const EXTRA_QUESTIONS: {
  key: keyof DiagnoseExtraInput
  title: string
  options: { label: string; value: string }[]
}[] = [
  {
    key: 'experience',
    title: '你有相关经验吗？',
    options: [
      { label: '完全没做过', value: 'none' },
      { label: '做过类似的', value: 'some' },
      { label: '做过一样的', value: 'pro' }
    ]
  },
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
  // M3-08：从「重新诊断」回到首页时带 ?redo=1，用上次的条件预填，用户只改想改的那一项
  const isRedo = getPageParams().redo === '1'
  const [capital, setCapital] = useState<number | null>(isRedo ? lastInput?.capital ?? null : null)
  const [dailyHours, setDailyHours] = useState<number | null>(
    isRedo ? lastInput?.dailyHours ?? null : null
  )
  const [city, setCity] = useState(isRedo ? lastInput?.city ?? '' : '')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  // M2-07：补充问答状态。默认收起且不预选，用户不理会即为「跳过」。
  const [extraOpen, setExtraOpen] = useState(false)
  const [extra, setExtra] = useState<DiagnoseExtraInput>(isRedo ? lastInput?.extra || {} : {})
  const setTaskId = useAppStore((s) => s.setTaskId)
  const setInput = useAppStore((s) => s.setInput)

  const ready = capital !== null && dailyHours !== null && city !== ''
  const extraAnswered = EXTRA_QUESTIONS.some((q) => extra[q.key])

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
      // M2-07：没有任何一题作答时明确标记 skipped，后端据此取中性偏好
      const payloadExtra: DiagnoseExtraInput = extraAnswered ? extra : { skipped: true }
      const { taskId } = await startDiagnose({
        capital: capital!,
        dailyHours: dailyHours!,
        city,
        extra: payloadExtra
      })
      setInput({ capital: capital!, dailyHours: dailyHours!, city, extra: payloadExtra })
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

      {isRedo && (
        <View className='m1-redo'>
          <Text className='m1-redo__text'>
            已带入你上次填的条件，改完直接重新诊断即可。重新诊断不会消耗你的免费额度，3 个免费方案照旧。
          </Text>
        </View>
      )}

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

      {/* ---------- M2-07 补充问答（可选，可跳过） ---------- */}
      <View className='bf-card m1-extra'>
        <View className='bf-row' onClick={() => setExtraOpen(!extraOpen)}>
          <View className='m1-extra__head'>
            <Text className='bf-card__title'>补充问答</Text>
            <Text className='bf-tag m1-extra__badge'>可选</Text>
          </View>
          <Text className='bf-muted m1-extra__toggle'>
            {extraOpen ? '收起' : '展开'} {extraOpen ? '︿' : '﹀'}
          </Text>
        </View>

        {!extraOpen && (
          <Text className='bf-muted m1-extra__tip'>
            {extraAnswered
              ? `已填 ${EXTRA_QUESTIONS.filter((q) => extra[q.key]).length} 题，结果会更贴合你`
              : '3 个小问题，填了更准；不填也能直接开始'}
          </Text>
        )}

        {extraOpen && (
          <View className='m1-extra__body'>
            {EXTRA_QUESTIONS.map((q) => (
              <View key={q.key} className='m1-extra__q'>
                <Text className='m1-extra__label'>{q.title}</Text>
                <View className='m1-extra__opts'>
                  {q.options.map((o) => (
                    <Text
                      key={o.value}
                      className={`bf-tag m1-extra__opt ${
                        extra[q.key] === o.value ? 'is-active' : ''
                      }`}
                      onClick={() =>
                        setExtra((prev) => ({
                          ...prev,
                          [q.key]: prev[q.key] === o.value ? null : o.value
                        }))
                      }
                    >
                      {o.label}
                    </Text>
                  ))}
                </View>
              </View>
            ))}
            <View className='bf-row m1-extra__foot'>
              <Text className='bf-muted m1-extra__hint'>不想填？直接点下面的按钮就行，不影响结果。</Text>
              {extraAnswered && (
                <Text className='m1-extra__clear' onClick={() => setExtra({})}>
                  清空
                </Text>
              )}
            </View>
          </View>
        )}
      </View>

      {error && <ErrorTip message={error} onRetry={onSubmit} />}

      <View
        className={`bf-btn m1-submit ${ready && !loading ? '' : 'bf-btn--disabled'}`}
        onClick={() => !loading && onSubmit()}
      >
        {loading ? '正在为你诊断…' : '帮我找生意'}
      </View>

      {/* V5.0 M5-03：今日谈资卡入口（UI 切图第 17 页；免费、可转发，做社交裂变触点） */}
      <View className='bf-card m1-talk' onClick={() => Taro.navigateTo({ url: '/pages/m12_talk_topic/index' })}>
        <View className='bf-row'>
          <Text className='bf-card__title'>💬 今日谈资</Text>
          <Text className='bf-tag bf-tag--accent'>免费</Text>
        </View>
        <Text className='bf-muted m1-talk__sub'>
          每天一条同城赚钱机会速览，饭桌上有话聊、有面子，一键转发给朋友
        </Text>
        <Text className='m1-talk__more'>看看今天的 →</Text>
      </View>
    </View>
  )
}
