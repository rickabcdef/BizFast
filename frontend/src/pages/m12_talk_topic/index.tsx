import { useEffect, useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { getTalkTopicToday, trackTalkTopic, type TalkTopic } from '@/services/bApi'
import { useAppStore } from '@/store'
import './index.scss'

// V5.0 M5-03 今日谈资卡（P0 传播物）| 对齐 UI 切图 V5.0 第 17 页
// 每天一条「同城/本行业赚钱机会速览」，卡片不带付费引导，只带品牌标识，支持一键转发。
const RULES = [
  ['①', '说「我看到什么」，不说「我赚了多少」'],
  ['②', '必须带来源和更新日期，查不到来源不发'],
  ['③', '必须给听的人一个免费用得上的入口']
]

export default function M12TalkTopic() {
  const [topic, setTopic] = useState<TalkTopic | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [savedTip, setSavedTip] = useState('')
  const city = useAppStore((s) => s.input?.city) || ''

  useEffect(() => {
    let alive = true
    getTalkTopicToday(city || undefined)
      .then((d) => {
        if (alive) setTopic(d)
      })
      .catch((e: any) => {
        if (alive) setError(e?.message || '谈资卡加载失败，请稍后重试')
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [city])

  const copyCard = async (channel: string) => {
    if (!topic) return
    const text = [
      topic.headline,
      `${topic.highlightNum}｜${topic.highlightLabel}`,
      topic.body,
      '——',
      '速览：',
      ...topic.lines.map((l) => `· ${l}`),
      '',
      `${topic.source}｜${topic.brand}`,
      topic.shareUrl || ''
    ]
      .filter(Boolean)
      .join('\n')
    try {
      await Taro.setClipboardData({ data: text })
      setSavedTip(`已复制，去${channel}粘贴就能发`)
      if (topic.id) trackTalkTopic(topic.id, channel).catch(() => {})
    } catch {
      setSavedTip('复制失败，请长按卡片手动选择')
    }
    setTimeout(() => setSavedTip(''), 2400)
  }

  if (loading) {
    return (
      <View className='m12'>
        <View className='m12__loading'>正在生成今日谈资…</View>
      </View>
    )
  }

  if (error || !topic) {
    return (
      <View className='m12'>
        <View className='bf-error'>{error || '今日谈资暂不可用'}</View>
      </View>
    )
  }

  return (
    <View className='m12'>
      <View className='m12__head'>
        <Text className='m12__title'>💬 今日谈资</Text>
        <Text className='m12__sub'>每天一条，饭桌上有话聊、有面子</Text>
      </View>

      <View className='m12__meta'>
        <Text className='m12__date'>{topic.date}</Text>
        <Text className='bf-tag bf-tag--accent'>📍 {topic.city} · {topic.industry}</Text>
      </View>

      {/* 可转发的谈资卡 */}
      <View className='m12__card'>
        <Text className='m12__tag'>{topic.tag}</Text>
        <Text className='m12__headline'>{topic.headline}</Text>
        <Text className='m12__num'>{topic.highlightNum}</Text>
        <Text className='m12__numlabel'>{topic.highlightLabel}</Text>
        <View className='m12__bodywrap'>
          {(topic.body || '').split('\n').filter(Boolean).map((line, i) => (
            <Text key={i} className='m12__body'>{line}</Text>
          ))}
        </View>
        <View className='m12__source'>
          <Text className='m12__srctext'>{topic.source}</Text>
          <Text className='m12__brand'>{topic.brand}</Text>
        </View>
      </View>

      {/* 速览 */}
      {topic.lines.length > 0 && (
        <View className='bf-card m12__slist'>
          <Text className='bf-card__title'>今天的其他机会速览</Text>
          {topic.lines.map((l, i) => (
            <Text key={i} className='m12__sline'>{l}</Text>
          ))}
        </View>
      )}

      {/* 操作 */}
      <View className='m12__actions'>
        <View className='bf-btn' onClick={() => copyCard('微信')}>保存文案，发到群里</View>
        <View className='bf-btn bf-btn--ghost' onClick={() => copyCard('朋友圈')}>
          一键复制转发文案
        </View>
        {savedTip ? <Text className='m12__tip'>{savedTip}</Text> : null}
      </View>

      {/* 三条铁律 */}
      <View className='bf-card m12__rules'>
        <Text className='bf-card__title'>📌 每一条谈资都遵守三条铁律</Text>
        {RULES.map(([n, t]) => (
          <View key={n} className='m12__rule'>
            <Text className='m12__rulenum'>{n}</Text>
            <Text className='m12__ruletext'>{t}</Text>
          </View>
        ))}
      </View>

      {/* 免费入口 */}
      <View className='bf-card m12__entry'>
        <Text className='bf-card__title'>🎁 朋友看到这条，能免费做什么？</Text>
        <Text className='bf-muted m12__entrydesc'>
          谈资卡下方会自动带上一个免费入口，朋友点进来就能做一次商机诊断（不收费、不用注册）。
        </Text>
        <View className='bf-btn bf-btn--ghost' onClick={() => Taro.navigateTo({ url: '/pages/m1_home/index' })}>
          看看朋友点进来会看到什么 →
        </View>
      </View>

      <View className='bf-card m12__compliance'>
        <Text className='bf-muted'>
          ⚠️ 内容合规提示：不生成未经核实的具体收益数字，不使用「内部消息」「稳赚不赔」等表述，
          涉及政策补贴一律标注「以官方最新公布为准」。
        </Text>
      </View>
    </View>
  )
}
