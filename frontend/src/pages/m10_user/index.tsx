import { useState, useEffect } from 'react'
import { View, Text, Input, Image } from '@tarojs/components'
import Taro from '@tarojs/taro'
import Loading from '@/components/Loading'
import ErrorTip from '@/components/ErrorTip'
import { saveFile } from '@/utils/platform'
import {
  getMyPackages,
  getOrders,
  getMembership,
  getInviteInfo,
  phoneLogin,
  wechatLogin,
  deleteAccount
} from '@/services/repo'
import { cancelSubscription, updateUserProfile } from '@/services/aApi'
import { CITIES } from '@/constants/cities'
import {
  getMyReports,
  getTalkTopicHistory,
  getFavoriteOpportunities,
  type ShareReport,
  type TalkTopic,
  type FavoriteOpportunity
} from '@/services/bApi'
import { useAppStore } from '@/store'
import type { PackageResult, OrderView, Membership, InviteInfo } from '@/types'
import './index.scss'

// M10 个人中心 | 负责人: D | 优先级: P0
const PLAN_LABEL: Record<string, string> = {
  none: '游客',
  single: '开业礼包',
  month: 'AI 合伙人月卡',
  year: '创业陪跑年卡'
}
const ORDER_LABEL: Record<string, string> = {
  pending: '待支付',
  paid: '已支付',
  generating: '生成中',
  delivered: '已交付',
  refunded: '已退款',
  closed: '已关闭'
}

// M0-02（V5.0）画像编辑：字段 ≤6 个，全部单选 / 滑块，不用键盘输入。
// 下面的选项文案必须与后端存值逐字一致，否则画像会出现两套说法。
const CAPITAL_BANDS = ['3 万以内', '3–10 万', '10–30 万', '30 万以上']
const HOURS_BANDS = ['2 小时以内', '2–4 小时', '4–8 小时', '8 小时以上']
const EXPERIENCE_OPTS = ['零经验起步', '有相关经验', '做过同样的生意']
// 常用城市置顶，避免每次都在 300+ 项里翻找；「全选城市」展开完整列表
const HOT_CITIES = [
  '北京市',
  '上海市',
  '广州市',
  '深圳市',
  '杭州市',
  '成都市',
  '武汉市',
  '西安市',
  '南京市',
  '重庆市',
  '长沙市',
  '苏州市'
]

export default function M10User() {
  const user = useAppStore((s) => s.user)
  const token = useAppStore((s) => s.token)
  const logout = useAppStore((s) => s.logout)
  const setUser = useAppStore((s) => s.setUser)
  const setToken = useAppStore((s) => s.setToken)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [packages, setPackages] = useState<PackageResult[]>([])
  const [orders, setOrders] = useState<OrderView[]>([])
  const [member, setMember] = useState<Membership | null>(null)
  const [invite, setInvite] = useState<InviteInfo | null>(null)
  // V5.0 M10：我的喜报与素材 / 收藏的商机与谈资
  const [reports, setReports] = useState<ShareReport[]>([])
  const [topics, setTopics] = useState<TalkTopic[]>([])
  const [favorites, setFavorites] = useState<FavoriteOpportunity[]>([])
  // M0-02（V5.0）画像编辑弹层
  const [profileOpen, setProfileOpen] = useState(false)
  const [cityAll, setCityAll] = useState(false)
  const [saving, setSaving] = useState(false)
  const [draft, setDraft] = useState({
    city: '',
    capitalBand: '',
    dailyHoursBand: '',
    experience: ''
  })

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const [pk, od, mb, iv] = await Promise.all([
        getMyPackages(),
        getOrders(),
        getMembership(),
        getInviteInfo()
      ])
      setPackages(pk)
      setOrders(od)
      setMember(mb)
      setInvite(iv)
      // 辅助模块失败不影响主信息展示（各自独立降级为空列表）
      getMyReports()
        .then((r) => setReports(r.items || []))
        .catch(() => {})
      getTalkTopicHistory(7)
        .then((r) => setTopics(r.items || []))
        .catch(() => {})
      getFavoriteOpportunities()
        .then((r) => setFavorites(r.items || []))
        .catch(() => {})
    } catch (e: any) {
      setError(e?.message || '加载失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (token) load()
  }, [token])

  // M0-02（V5.0）：打开画像编辑，把当前值填成草稿（取消不会影响已存数据）
  const openProfileEdit = () => {
    setDraft({
      city: member?.city || '',
      capitalBand: member?.capitalBand || '',
      dailyHoursBand: member?.dailyHoursBand || '',
      experience: member?.experience || ''
    })
    setCityAll(false)
    setProfileOpen(true)
  }

  const saveProfile = async () => {
    setSaving(true)
    try {
      await updateUserProfile({
        city: draft.city || null,
        capitalBand: draft.capitalBand || null,
        dailyHoursBand: draft.dailyHoursBand || null,
        experience: draft.experience || null
      })
      // 画像与额度同源（都在 /api/user/me），保存后重新拉一次保证展示一致
      setMember(await getMembership())
      setProfileOpen(false)
      Taro.showToast({ title: '已保存', icon: 'success' })
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '保存失败，请重试', icon: 'none' })
    } finally {
      setSaving(false)
    }
  }

  const pickDraft = (key: 'capitalBand' | 'dailyHoursBand' | 'experience', v: string) => {
    setDraft((d) => ({ ...d, [key]: d[key] === v ? '' : v }))
  }

  // V5.0 第 11 页：资料头 + 三宫格统计
  const displayName = user?.phone ? '微信用户' : '我的'
  const maskedPhone = (user?.phone || '').replace(/(\d{3})\d{4}(\d{4})/, '$1****$2') || '未绑定手机'
  const generatedCount = packages.reduce((n, p) => n + p.items.length, 0)

  const doPhoneLogin = async () => {
    if (!/^1[3-9]\d{9}$/.test(phone)) {
      Taro.showToast({ title: '请输入正确的手机号', icon: 'none' })
      return
    }
    if (!code) {
      Taro.showToast({ title: '请输入验证码', icon: 'none' })
      return
    }
    setLoading(true)
    try {
      const res = await phoneLogin(phone, code)
      setToken(res.token)
      setUser(res.user)
      Taro.showToast({ title: '登录成功', icon: 'success' })
    } catch (e: any) {
      setError(e?.message || '登录失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  const doWechat = async () => {
    setLoading(true)
    try {
      const res = await wechatLogin()
      setToken(res.token)
      setUser(res.user)
      Taro.showToast({ title: '登录成功', icon: 'success' })
    } catch (e: any) {
      setError(e?.message || '登录失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  const onLogout = () => {
    logout()
    Taro.showToast({ title: '已退出（15日内清除隐私数据）', icon: 'none' })
  }

  /** M5-08：一键取消自动续费（PRD 要求取消入口不超过 3 步）。 */
  const onCancelRenew = async () => {
    try {
      const res = await cancelSubscription()
      setMember((m) => (m ? { ...m, autoRenew: !!res.autoRenew } : m))
      Taro.showToast({ title: '已取消自动续费', icon: 'none' })
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '取消失败，请重试', icon: 'none' })
    }
  }

  /** V5.0 M10-03：保存/分享喜报素材。 */
  const onSaveReport = (r: ShareReport) => {
    if (!r.imageUrl) return
    saveFile(r.imageUrl, `生意快启_开业喜报_${r.templateName || r.template || '喜报'}.png`)
    Taro.showToast({ title: '喜报已保存', icon: 'none' })
  }

  const onDeleteAccount = async () => {
    try {
      await deleteAccount()
      logout()
      Taro.showToast({ title: '已提交注销，15日内清除隐私数据', icon: 'none' })
    } catch (e: any) {
      setError(e?.message || '注销失败，请重试')
    }
  }

  if (!token) {
    return (
      <View className='page m10-user'>
        <View className='bf-card'>
          <Text className='bf-card__title'>账号登录</Text>
          <Text className='bf-muted'>登录后可查看「我的启动包」与订单（游客可先体验首屏与诊断）</Text>
          <View className='m10-login'>
            <Input
              className='bf-input'
              placeholder='手机号'
              value={phone}
              onInput={(e) => setPhone(e.detail.value)}
            />
            <View className='bf-row m10-code'>
              <Input
                className='bf-input'
                placeholder='验证码'
                value={code}
                onInput={(e) => setCode(e.detail.value)}
              />
              <View
                className='bf-btn bf-btn--sm'
                onClick={() => Taro.showToast({ title: '验证码已发送', icon: 'none' })}
              >
                获取
              </View>
            </View>
            <View className='bf-btn' onClick={doPhoneLogin}>
              手机号登录
            </View>
            <View className='bf-btn bf-btn--ghost' onClick={doWechat}>
              微信一键登录
            </View>
            <Text className='bf-muted m10-note'>iOS 端额外支持 Apple ID 登录；网页端暂仅支持手机号登录。</Text>
          </View>
        </View>
      </View>
    )
  }

  return (
    <View className='page m10-user'>
      <View className='m10-profile'>
        <View className='m10-profile__top'>
          <View className='m10-avatar'>👨‍💼</View>
          <View className='m10-profile__info'>
            <Text className='m10-name'>{displayName}</Text>
            <Text className='m10-phone'>{maskedPhone}</Text>
          </View>
          <View className='m10-logout' onClick={onLogout}>
            <Text className='m10-logout__txt'>退出</Text>
          </View>
        </View>
        {member && (
          <View className='m10-vip'>
            👑 {PLAN_LABEL[member.plan]} · 有效期至 {member.expireAt}
          </View>
        )}
      </View>

      <View className='m10-stats'>
        <View className='m10-stat'>
          <Text className='m10-stat__num'>{packages.length}</Text>
          <Text className='m10-stat__label'>我的启动包</Text>
        </View>
        <View className='m10-stat'>
          <Text className='m10-stat__num'>{generatedCount}</Text>
          <Text className='m10-stat__label'>已生成商机</Text>
        </View>
        <View className='m10-stat'>
          <Text className='m10-stat__num'>{favorites.length + topics.length}</Text>
          <Text className='m10-stat__label'>收藏工具</Text>
        </View>
      </View>

      {loading && <Loading />}
      {error && <ErrorTip message={error} onRetry={load} />}

      <View className='bf-card'>
        <View className='bf-row'>
          <Text className='bf-card__title'>我的启动包</Text>
          <Text className='bf-muted'>{packages.length} 个</Text>
        </View>
        {packages.map((p) => (
          <View key={p.orderId} className='m10-pkg'>
            <Text className='bf-muted'>
              订单 {p.orderId} · {p.status === 'delivered' ? '已交付' : '生成中'}
            </Text>
            <View className='bf-list'>
              {p.items.map((it) => (
                <View key={it.code} className='bf-list__item'>
                  <Text>
                    {it.code} · {it.name}
                  </Text>
                  {/* 单件下载/预览统一由 m4 交付页承接（负责人 B：M4-03/04/05） */}
                  <Text
                    className='bf-btn bf-btn--sm'
                    onClick={() =>
                      Taro.navigateTo({
                        url: `/pages/m4_delivery/index?orderId=${p.orderId}`
                      })
                    }
                  >
                    下载
                  </Text>
                </View>
              ))}
            </View>
            {/* 打包下载统一由 m4 交付页承接 */}
            <View
              className='bf-btn bf-btn--sm m10-zip'
              onClick={() =>
                Taro.navigateTo({
                  url: `/pages/m4_delivery/index?orderId=${p.orderId}`
                })
              }
            >
              打包下载
            </View>
          </View>
        ))}
      </View>

      <View className='bf-card'>
        <Text className='bf-card__title'>我的订单</Text>
        <View className='bf-list'>
          {orders.map((o) => (
            <View key={o.orderId} className='bf-list__item'>
              <View>
                <Text>{o.title}</Text>
                <Text className='bf-muted'> {o.createdAt}</Text>
              </View>
              <Text className='bf-tag'>{ORDER_LABEL[o.status]}</Text>
            </View>
          ))}
        </View>
      </View>

      {member && (
        <View className='bf-card'>
          <Text className='bf-card__title'>会员</Text>
          <View className='bf-row'>
            <Text>
              {PLAN_LABEL[member.plan]} · 有效期至 {member.expireAt}
            </Text>
            <Text className='bf-muted'>{member.autoRenew ? '自动续费中' : '已关闭续费'}</Text>
          </View>
          <View
            className='bf-btn bf-btn--ghost bf-btn--sm m10-cancel'
            onClick={onCancelRenew}
          >
            取消自动续费
          </View>
        </View>
      )}

      {/* M0-02 / M0-03（V5.0）：生意画像 + 会员额度（已购次数 / 已用启动包数 / 额度剩余） */}
      {member && (
        <View className='bf-card'>
          <View className='bf-row m10-kvhead'>
            <Text className='bf-card__title'>我的生意画像与额度</Text>
            <Text className='bf-btn bf-btn--ghost bf-btn--sm' onClick={openProfileEdit}>
              编辑画像
            </Text>
          </View>
          <View className='m10-kv'>
            <Text className='bf-muted m10-kv__k'>所在城市</Text>
            <Text className='m10-kv__v'>{member.city || '未填写'}</Text>
          </View>
          <View className='m10-kv'>
            <Text className='bf-muted m10-kv__k'>启动资金</Text>
            <Text className='m10-kv__v'>{member.capitalBand || '未填写'}</Text>
          </View>
          <View className='m10-kv'>
            <Text className='bf-muted m10-kv__k'>每日可投入</Text>
            <Text className='m10-kv__v'>{member.dailyHoursBand || '未填写'}</Text>
          </View>
          <View className='m10-kv'>
            <Text className='bf-muted m10-kv__k'>相关经验</Text>
            <Text className='m10-kv__v'>{member.experience || '未填写'}</Text>
          </View>
          <View className='m10-kv'>
            <Text className='bf-muted m10-kv__k'>已购次数</Text>
            <Text className='m10-kv__v'>{member.purchasedCount ?? 0} 次</Text>
          </View>
          <View className='m10-kv'>
            <Text className='bf-muted m10-kv__k'>已用启动包</Text>
            <Text className='m10-kv__v'>{member.usedPackageCount ?? 0} 个</Text>
          </View>
          <View className='m10-kv'>
            <Text className='bf-muted m10-kv__k'>剩余额度</Text>
            <Text className='m10-kv__v'>
              {member.quotaUnlimited ? '不限次（会员）' : `${member.quotaRemaining ?? 0} 次`}
            </Text>
          </View>
          <Text className='bf-muted m10-quota__note'>
            {member.quotaUnlimited
              ? '会员有效期内可不限次生成启动包。'
              : '单次礼包按「一单一次生成」计额度，退款后可重新购买。'}
          </Text>
        </View>
      )}

      {invite && (
        <View className='bf-card'>
          <Text className='bf-card__title'>邀请奖励</Text>
          <Text className='bf-muted'>
            邀请码 {invite.code} · {invite.coupon} · 免费生成 {invite.freeGenerations} 次
          </Text>
          <View
            className='bf-btn bf-btn--sm m10-invite'
            onClick={() => {
              Taro.setClipboardData({ data: invite.link })
              Taro.showToast({ title: '邀请链接已复制', icon: 'none' })
            }}
          >
            复制邀请链接
          </View>
        </View>
      )}

      <View className='bf-card'>
        <Text className='bf-card__title'>工具与休息</Text>
        <View className='bf-row'>
          <View
            className='bf-btn bf-btn--ghost bf-btn--sm'
            onClick={() => Taro.navigateTo({ url: '/pages/m6_tools/index' })}
          >
            工具箱
          </View>
          <View
            className='bf-btn bf-btn--ghost bf-btn--sm'
            onClick={() => Taro.navigateTo({ url: '/pages/m7_games/index' })}
          >
            休息一下
          </View>
        </View>
      </View>

      {/* V5.0 档位升级入口（UI 切图第 11 页：🚀 选择你的开干方案 → 第 12 页） */}
      <View className='m10-plan-entry'>
        <View
          className='bf-btn m10-plan-entry__btn'
          onClick={() => Taro.navigateTo({ url: '/pages/m5_pay/index?plan=single' })}
        >
          🚀 选择你的开干方案
        </View>
      </View>

      {/* V5.0 M10-03 我的喜报与素材 */}
      <View className='bf-card'>
        <View className='bf-row'>
          <Text className='bf-card__title'>我的喜报与素材</Text>
          <Text className='bf-muted'>{reports.length} 张</Text>
        </View>
        {reports.length === 0 ? (
          <Text className='bf-muted m10-empty'>
            还没有喜报。在交付页点「生成我的开业喜报」就能一键出图。
          </Text>
        ) : (
          <View className='m10-reports'>
            {reports.map((r) => (
              <View key={r.id} className='m10-report'>
                <View
                  className='m10-report__thumb'
                  onClick={() => r.imageUrl && Taro.previewImage({ urls: [r.imageUrl] })}
                >
                  {r.imageUrl ? <Image className='m10-report__img' src={r.imageUrl} mode='aspectFill' /> : null}
                </View>
                <Text className='m10-report__t'>{r.title || `模板 ${r.template}`}</Text>
                <Text className='bf-muted m10-report__s'>{r.templateName || ''}</Text>
                <View className='bf-row m10-report__acts'>
                  <Text
                    className='bf-btn bf-btn--sm'
                    onClick={() => r.imageUrl && Taro.previewImage({ urls: [r.imageUrl] })}
                  >
                    查看
                  </Text>
                  <Text
                    className='bf-btn bf-btn--ghost bf-btn--sm'
                    onClick={() => onSaveReport(r)}
                  >
                    保存
                  </Text>
                </View>
              </View>
            ))}
          </View>
        )}
      </View>

      {/* V5.0 M10-04 收藏的商机与谈资 */}
      <View className='bf-card'>
        <View className='bf-row'>
          <Text className='bf-card__title'>收藏的商机与谈资</Text>
          <Text className='bf-muted'>
            商机 {favorites.length} · 谈资 {topics.length}
          </Text>
        </View>

        <Text className='m10-sub'>📌 我收藏的商机</Text>
        {favorites.length === 0 ? (
          <Text className='bf-muted m10-empty'>还没有收藏。在商机卡片上点「收藏」即可留在这里。</Text>
        ) : (
          <View className='bf-list'>
            {favorites.map((f) => (
              <View key={f.id} className='bf-list__item m10-fav'>
                <View>
                  <Text>
                    {f.icon} {f.title}
                  </Text>
                  <Text className='bf-muted'>
                    {' '}
                    {f.fiveElements
                      ? `${f.fiveElements.capital} · 回本 ${f.fiveElements.payback} · 毛利 ${f.fiveElements.margin}`
                      : `收藏于 ${f.favoritedAt}`}
                  </Text>
                </View>
                <Text className='bf-muted'>{f.favoritedAt}</Text>
              </View>
            ))}
          </View>
        )}

        <Text className='m10-sub'>📖 今日谈资历史（近 7 天）</Text>
        {topics.length === 0 ? (
          <Text className='bf-muted m10-empty'>还没有谈资卡记录。</Text>
        ) : (
          <View className='bf-list'>
            {topics.map((t) => (
              <View
                key={t.id}
                className='bf-list__item'
                onClick={() => Taro.navigateTo({ url: '/pages/m12_talk_topic/index' })}
              >
                <View>
                  <Text>{t.headline || t.title}</Text>
                  <Text className='bf-muted'>
                    {' '}
                    {t.date} · {t.city}
                  </Text>
                </View>
                <Text className='bf-tag'>查看</Text>
              </View>
            ))}
          </View>
        )}
      </View>

      <View className='bf-card'>
        <Text className='bf-card__title'>账号安全</Text>
        {/* V5.0 M10-05 设置：账号与安全 / 隐私设置 / 注销账号（≤3 步可达） */}
        <View
          className='bf-list__item m10-privacy'
          onClick={() => Taro.navigateTo({ url: '/pages/m9_notify/index' })}
        >
          <View>
            <Text>隐私设置</Text>
            <Text className='bf-muted'> 通知方式、免打扰时段、手机号脱敏展示</Text>
          </View>
          <Text className='bf-tag'>设置</Text>
        </View>
        <Text className='bf-muted'>注销后 15 日内保留数据用于找回，到期自动清除隐私信息。</Text>
        <View className='bf-btn bf-btn--ghost bf-btn--sm m10-delete' onClick={onDeleteAccount}>
          注销账号
        </View>
      </View>

      {/* M0-02（V5.0）画像编辑弹层：全部单选 / 点选，无需键盘输入 */}
      {profileOpen && (
        <View className='m10-mask' onClick={() => setProfileOpen(false)}>
          <View className='m10-modal' onClick={(e) => e.stopPropagation()}>
            <Text className='m10-modal__title'>编辑生意画像</Text>
            <Text className='bf-muted m10-modal__sub'>
              画像越准，诊断出的商机越贴合你。全部点选即可，不用打字。
            </Text>

            <Text className='m10-field__label'>所在城市</Text>
            <View className='m10-chips'>
              {(cityAll ? CITIES : HOT_CITIES).map((c) => (
                <Text
                  key={c}
                  className={`m10-chip${draft.city === c ? ' is-on' : ''}`}
                  onClick={() => setDraft((d) => ({ ...d, city: d.city === c ? '' : c }))}
                >
                  {c}
                </Text>
              ))}
            </View>
            <Text className='m10-more' onClick={() => setCityAll((v) => !v)}>
              {cityAll ? '收起城市列表' : `更多城市（共 ${CITIES.length} 个）`}
            </Text>

            <Text className='m10-field__label'>启动资金</Text>
            <View className='m10-chips'>
              {CAPITAL_BANDS.map((b) => (
                <Text
                  key={b}
                  className={`m10-chip${draft.capitalBand === b ? ' is-on' : ''}`}
                  onClick={() => pickDraft('capitalBand', b)}
                >
                  {b}
                </Text>
              ))}
            </View>

            <Text className='m10-field__label'>每日可投入时间</Text>
            <View className='m10-chips'>
              {HOURS_BANDS.map((b) => (
                <Text
                  key={b}
                  className={`m10-chip${draft.dailyHoursBand === b ? ' is-on' : ''}`}
                  onClick={() => pickDraft('dailyHoursBand', b)}
                >
                  {b}
                </Text>
              ))}
            </View>

            <Text className='m10-field__label'>相关经验</Text>
            <View className='m10-chips'>
              {EXPERIENCE_OPTS.map((b) => (
                <Text
                  key={b}
                  className={`m10-chip${draft.experience === b ? ' is-on' : ''}`}
                  onClick={() => pickDraft('experience', b)}
                >
                  {b}
                </Text>
              ))}
            </View>

            <View className='bf-row m10-modal__acts'>
              <View className='bf-btn bf-btn--ghost m10-modal__btn' onClick={() => setProfileOpen(false)}>
                取消
              </View>
              <View
                className={`bf-btn m10-modal__btn${saving ? ' is-disabled' : ''}`}
                onClick={saving ? undefined : saveProfile}
              >
                {saving ? '保存中…' : '保存'}
              </View>
            </View>
          </View>
        </View>
      )}
    </View>
  )
}
