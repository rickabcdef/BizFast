import { useState, useEffect } from 'react'
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import ShareCard from '@/components/ShareCard'
import { copyText, downloadDataURL, buildShareCardCanvas, desensitize } from '@/utils/share'
import { getInviteInfo, createShareCard, trackShare } from '@/services/repo'
import type { InviteInfo } from '@/types'
import './index.scss'

// M8 分享与增长 | 负责人: D | 优先级: P1
// 示例成果数据（真实数据来自后端诊断/生成结果，分享前已脱敏）
const SAMPLE = {
  productName: '生意快启 · 你的生意启动包',
  subtitle: '社区团购 · 杭州 · 启动资金 1–5 万',
  lines: [
    '机会热度：高（同城需求旺盛）',
    '推荐商机：社区团购团长',
    '回本周期：约 6 周',
    '交付物：评分卡 / 回本表 / 获客清单…',
    '风险提示：供应链稳定性'
  ],
  qrText: 'https://bizfast.app/s/mock-task-001'
}

const CHANNELS = ['微信好友', '朋友圈', '抖音', '小红书', '复制链接', '保存图片']

export default function M8Share() {
  const [invite, setInvite] = useState<InviteInfo | null>(null)
  const [savedTip, setSavedTip] = useState('')
  const [cardId, setCardId] = useState<string | null>(null)
  const [shareUrl, setShareUrl] = useState<string>('')

  useEffect(() => {
    getInviteInfo()
      .then(setInvite)
      .catch(() => {})
    // M8-01 生成成果分享卡片（后端落库 + 返回带邀请码的分享链接）；Mock 下返回本地占位
    createShareCard({
      productName: SAMPLE.productName,
      subtitle: SAMPLE.subtitle,
      lines: SAMPLE.lines,
      qrText: SAMPLE.qrText
    })
      .then((r) => {
        setCardId(r.id)
        setShareUrl(r.shareUrl)
      })
      .catch(() => {})
  }, [])

  // 分享前脱敏（M8-06）：去除手机号/订单号等隐私
  const safeLines = SAMPLE.lines.map(desensitize)

  const onChannel = async (ch: string) => {
    if (ch === '复制链接') {
      await copyText(shareUrl || SAMPLE.qrText)
      Taro.showToast({ title: '链接已复制', icon: 'none' })
      return
    }
    if (ch === '保存图片') {
      const url = buildShareCardCanvas({ ...SAMPLE, lines: safeLines })
      if (url) {
        downloadDataURL(url, '生意快启-分享卡片.png')
        setSavedTip('图片已保存')
      } else {
        Taro.showToast({ title: '请在 App/小程序保存', icon: 'none' })
      }
      return
    }
    // 微信/朋友圈/抖音/小红书：网页端无法直接调起对应 App，复制链接并在对应 App 打开；
    // 同时上报分享埋点（M8-02），用于分享率指标与后台回收
    await copyText(shareUrl || SAMPLE.qrText)
    await trackShare(cardId, ch).catch(() => {})
    Taro.showToast({ title: `已复制链接，请在「${ch}」打开`, icon: 'none' })
  }

  return (
    <View className='page m8-share'>
      <Text className='bf-card__title'>成果卡片</Text>
      <ShareCard
        productName={SAMPLE.productName}
        subtitle={SAMPLE.subtitle}
        lines={safeLines}
        qrText={SAMPLE.qrText}
      />

      <Text className='bf-card__title m8-mt'>分享到</Text>
      <View
        className='bf-seg'
        style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16rpx' }}
      >
        {CHANNELS.map((c) => (
          <View
            key={c}
            className='bf-seg__item bf-seg__item--active'
            onClick={() => onChannel(c)}
          >
            {c}
          </View>
        ))}
      </View>

      {savedTip && <Text className='bf-muted'>{savedTip}</Text>}

      <View className='bf-card m8-mt'>
        <Text className='bf-card__title'>邀请奖励（M8-03）</Text>
        {invite && (
          <Text className='bf-muted'>
            邀请码 {invite.code} · 双方各得 {invite.coupon} / 免费生成 {invite.freeGenerations} 次
          </Text>
        )}
        {/* M8-05 合规：不强制转发才能解锁内容，奖励实时可见即可 */}
      </View>

      <View className='bf-card'>
        <Text className='bf-muted'>
          合规说明：不强制转发才能解锁内容（M8-05）；分享内容已自动脱敏，不含手机号与订单号（M8-06）。
        </Text>
      </View>
    </View>
  )
}
