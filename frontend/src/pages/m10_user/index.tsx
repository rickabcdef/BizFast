import { useState, useEffect } from 'react'
import { View, Text, Input } from '@tarojs/components'
import Taro from '@tarojs/taro'
import Loading from '@/components/Loading'
import ErrorTip from '@/components/ErrorTip'
import {
  getMyPackages,
  getOrders,
  getMembership,
  getInviteInfo,
  phoneLogin,
  wechatLogin,
  deleteAccount
} from '@/services/repo'
import { useAppStore } from '@/store'
import type { PackageResult, OrderView, Membership, InviteInfo } from '@/types'
import './index.scss'

// M10 个人中心 | 负责人: D | 优先级: P0
const PLAN_LABEL: Record<string, string> = {
  none: '游客',
  single: '单次付费',
  month: '月度会员',
  year: '年度会员'
}
const ORDER_LABEL: Record<string, string> = {
  pending: '待支付',
  paid: '已支付',
  generating: '生成中',
  delivered: '已交付',
  refunded: '已退款',
  closed: '已关闭'
}

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
    } catch (e: any) {
      setError(e?.message || '加载失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (token) load()
  }, [token])

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
      <View className='bf-card'>
        <View className='bf-row'>
          <Text className='m10-name'>{user?.phone || (user?.isGuest ? '游客' : '我的')}</Text>
          <Text className='bf-tag'>{PLAN_LABEL[user?.plan || 'none']}</Text>
        </View>
        <View className='bf-btn bf-btn--ghost m10-logout' onClick={onLogout}>
          退出登录
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
            onClick={() => Taro.showToast({ title: '已取消自动续费', icon: 'none' })}
          >
            取消自动续费
          </View>
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

      <View className='bf-card'>
        <Text className='bf-card__title'>账号安全</Text>
        <Text className='bf-muted'>注销后 15 日内保留数据用于找回，到期自动清除隐私信息。</Text>
        <View className='bf-btn bf-btn--ghost bf-btn--sm m10-delete' onClick={onDeleteAccount}>
          注销账号
        </View>
      </View>
    </View>
  )
}
