import { useState, useEffect, useMemo } from 'react'
import { View, Text } from '@tarojs/components'
import Taro, { useRouter } from '@tarojs/taro'
import ShareCard from '@/components/ShareCard'
import { copyText, downloadDataURL, buildShareCardCanvas, desensitize } from '@/utils/share'
import { getInviteInfo, createShareCard, trackShare } from '@/services/repo'
import type { InviteInfo } from '@/types'
import './index.scss'

// M5 裂变传播 / 成果分享卡片 | 负责人: C | 优先级: P0
// 卡片数据优先取自路由参数（由诊断结果/交付页传入真实内容），无参时用通用品牌兜底，绝不展示假业务数据。

// 通用品牌兜底（不含任何虚构的城市/品类/数字）
const FALLBACK = {
  productName: '生意快启 · 小生意启动助手',
  subtitle: '把你的生意诊断结果分享给好友',
  lines: ['用生意快启，30 秒看清同城机会热度', '生成专属启动包，开店少走弯路', '点击链接，免费领取你的机会热度图'],
  qrText: 'https://bizfast.app'
}

const CHANNELS = ['微信好友', '朋友圈', '抖音', '小红书', '复制链接', '保存图片']

export default function M8Share() {
  const router = useRouter()
  // 由调用方（诊断结果页/交付页）通过 URL 传入真实卡片内容
  const card = useMemo(() => {
    const p = router.params
    const linesRaw = (p.lines as string) || ''
    const lines = linesRaw
      ? linesRaw.split('|').map((s) => s.trim()).filter(Boolean)
      : FALLBACK.lines
    return {
      productName: (p.productName as string) || FALLBACK.productName,
      subtitle: (p.subtitle as string) || FALLBACK.subtitle,
      lines: lines.length ? lines : FALLBACK.lines,
      qrText: (p.qrText as string) || FALLBACK.qrText
    }
  }, [router.params])

  const [invite, setInvite] = useState<InviteInfo | null>(null)
  const [savedTip, setSavedTip] = useState('')
  const [cardId, setCardId] = useState<string | null>(null)
  const [shareUrl, setShareUrl] = useState<string>('')

  useEffect(() => {
    getInviteInfo()
      .then(setInvite)
      .catch(() => {})
    // 生成成果分享卡片（后端落库 + 返回带邀请码的分享链接），内容为真实传入数据
    createShareCard({
      productName: card.productName,
      subtitle: card.subtitle,
      lines: card.lines,
      qrText: card.qrText
    })
      .then((r) => {
        setCardId(r.id)
        setShareUrl(r.shareUrl)
      })
      .catch(() => {})
  }, [card])

  // 分享前脱敏（M5 合规）：去除手机号/订单号等隐私
  const safeLines = card.lines.map(desensitize)

  const onChannel = async (ch: string) => {
    if (ch === '复制链接') {
      await copyText(shareUrl || card.qrText)
      Taro.showToast({ title: '链接已复制', icon: 'none' })
      return
    }
    if (ch === '保存图片') {
      const url = buildShareCardCanvas({ ...card, lines: safeLines })
      if (url) {
        downloadDataURL(url, '生意快启-分享卡片.png')
        setSavedTip('图片已保存')
      } else {
        Taro.showToast({ title: '请在 App/小程序保存', icon: 'none' })
      }
      return
    }
    // 微信/朋友圈/抖音/小红书：网页端无法直接调起对应 App，复制链接并在对应 App 打开；
    // 同时上报分享埋点（M5-04），用于分享率指标与后台回收
    await copyText(shareUrl || card.qrText)
    await trackShare(cardId, ch).catch(() => {})
    Taro.showToast({ title: `已复制链接，请在「${ch}」打开`, icon: 'none' })
  }

  return (
    <View className='page m8-share'>
      <Text className='bf-card__title'>成果卡片</Text>
      <ShareCard
        productName={card.productName}
        subtitle={card.subtitle}
        lines={safeLines}
        qrText={shareUrl || card.qrText}
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
        <Text className='bf-card__title'>邀请有礼（M5-05）</Text>
        {invite && (
          <Text className='bf-muted'>
            你的邀请码 {invite.code}。邀请好友注册即绑定邀请关系，奖励活动将在 V1.1 开放，敬请期待。
          </Text>
        )}
        {/* 合规：不强制转发才能解锁内容，关系绑定即可 */}
      </View>

      <View className='bf-card'>
        <Text className='bf-muted'>
          合规说明：不强制转发才能解锁内容；分享内容已自动脱敏，不含手机号与订单号。
        </Text>
      </View>
    </View>
  )
}
