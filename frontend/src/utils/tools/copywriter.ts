/**
 * M6-04 文案小助手 · 纯前端本地生成（不调用第三方、不存储用户原文）
 * 基于模板 + 槽位组合，输出朋友圈 / 短视频口播 / 促销活动文案，并统计字数。负责人: C
 * 说明：网页端先行阶段本地生成；后续可平滑替换为后端大模型接口（见 docs/api-contract.md）。
 */
export interface CopyInput {
  category: string // 行业/品类，如「社区奶茶店」
  shopName: string // 店名
  sellingPoint: string // 核心卖点
  audience: string // 目标人群
  tone: 'warm' | 'professional' | 'lively' // 语气
}

export interface CopyOutput {
  moments: string[]
  video: string
  promo: string
  count: number
}

const pick = <T>(arr: T[], i: number) => arr[i % arr.length]

export function generateCopy(input: CopyInput): CopyOutput {
  const { category = '生意', shopName = '我的小店', sellingPoint = '用心做好每一份', audience = '街坊邻里', tone } = input
  const cat = category.trim() || '这门生意'
  const shop = shopName.trim() || '小店'
  const sp = sellingPoint.trim() || '品质过硬、用心经营'
  const aud = audience.trim() || '附近的朋友'

  const emo = tone === 'lively' ? ['🎉', '✨', '🔥', '💯'] : tone === 'professional' ? ['📌', '✅', '💼'] : ['🌿', '☕', '💛']
  const e = (i: number) => pick(emo, i)

  const moments = [
    `${e(0)}${aud}看过来！${shop}做${cat}，主打的就是一个「${sp}」。\n${e(1)}每天现做/现备，不糊弄、不将就，吃过的朋友都说实在。\n${e(2)}来一趟，交个朋友。地址就在你熟悉的老地方，等你～`,
    `${e(1)}做${cat}这行，我最看重两件事：干净、实在。\n${shop}——${sp}，这是我给${aud}的承诺。\n${e(2)}不靠花哨营销，靠的是回头客的一句「下次还来」。`,
    `很多人问我，${cat}那么多，凭什么选${shop}？\n${e(0)}答案就四个字：${sp}。\n${e(2)}${aud}的信任，是我一天天攒出来的。欢迎来坐坐，不好吃/不好用你说我。`
  ]

  const video =
    `${e(0)}如果你也在找靠谱的${cat}，这条别划走！\n` +
    `我是${shop}的老板，做这行就认一个理：${sp}。\n` +
    `${aud}常来常往，靠的不是套路，是实在。\n` +
    `${e(2)}点赞收藏，下次需要的时候，一翻就能找到我！`

  const promo =
    `【${shop}·限时活动】\n` +
    `${aud}专属：即日起，到店/下单即可享「${sp}」体验价！\n` +
    `${e(1)}数量有限，先到先得，做完即止。\n` +
    `👉 转发给身边需要的朋友，一起把日子过得更划算。`

  const all = [...moments, video, promo].join('\n')
  return { moments, video, promo, count: countChars(all) }
}

/** 字数统计：中文字符按字计，其余按字符计（不含空白） */
export function countChars(text: string): number {
  const stripped = text.replace(/\s/g, '')
  return Array.from(stripped).length
}

/** 语气改写：在原文基础上做轻度风格化（口语化 / 书面化 / 加emoji），不改变事实 */
export function rewriteTone(text: string, tone: 'warm' | 'professional' | 'lively'): string {
  let out = text.trim()
  if (tone === 'lively') {
    out = out.replace(/。/g, '！').replace(/，/g, '~')
    out = '🎉 ' + out + ' ✨'
  } else if (tone === 'professional') {
    out = out.replace(/[！!~]/g, '。').replace(/🎉|✨|🔥|💯|🌿|☕|💛|📌|✅|💼|👉/g, '').trim()
  } else {
    out = out.replace(/[！!]{2,}/g, '。')
    out = '🌿 ' + out
  }
  return out
}
