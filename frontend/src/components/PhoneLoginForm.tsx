import { useEffect, useRef, useState } from 'react'
import { View, Text, Input } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { phoneLogin, sendSmsCode, wechatLogin } from '@/services/repo'
import type { AuthResult } from '@/types'

interface Props {
  /** 登录成功回调（由父组件负责写入 token / user） */
  onSuccess: (res: AuthResult) => void
  /** 成功提示文案（付费闸门场景可换成「登录成功，继续支付」） */
  successText?: string
  /** 是否展示「微信一键登录」（网页端为占位授权） */
  showWechat?: boolean
  /** 顶部说明文案 */
  tip?: string
}

/**
 * M0-01（V5.0）手机号 / 微信登录表单。
 *
 * 抽成公共组件的原因：付费页（m5_pay，付费前强制登录）与个人中心（m10）都要用，
 * 各自实现一遍必然出现「有一个页面的验证码按钮是假的」这类问题（此前确实如此）。
 *
 * 关键点：
 * - 「获取验证码」**真实调用** POST /api/auth/sms/send，并带 60 秒倒计时防连点
 * - 验证码为 6 位数字，手机号做前端格式校验（后端仍会再校验一次）
 */
export default function PhoneLoginForm({
  onSuccess,
  successText = '登录成功',
  showWechat = true,
  tip = '登录后可查看「我的启动包」与订单（游客可先体验首屏与诊断）'
}: Props) {
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [countdown, setCountdown] = useState(0)
  const [busy, setBusy] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    return () => {
      if (timer.current) clearInterval(timer.current)
    }
  }, [])

  const validPhone = /^1[3-9]\d{9}$/.test(phone)

  const startCountdown = () => {
    setCountdown(60)
    if (timer.current) clearInterval(timer.current)
    timer.current = setInterval(() => {
      setCountdown((n) => {
        if (n <= 1) {
          if (timer.current) clearInterval(timer.current)
          timer.current = null
          return 0
        }
        return n - 1
      })
    }, 1000)
  }

  /** M0-01：真实发送验证码（此前只弹一个假 toast，手机号登录永远收不到码） */
  const onSendCode = async () => {
    if (busy || sending || countdown > 0) return
    if (!validPhone) {
      Taro.showToast({ title: '请输入正确的手机号', icon: 'none' })
      return
    }
    setSending(true)
    setError('')
    try {
      const res = await sendSmsCode(phone)
      // 开发环境后端会把验证码回传（生产不回传），联调时直接显示出来省事
      const extra = res?.code ? `（验证码 ${res.code}）` : ''
      Taro.showToast({ title: `验证码已发送${extra}`, icon: 'none', duration: 2500 })
      startCountdown()
    } catch (e: any) {
      setError(e?.message || '验证码发送失败，请重试')
    } finally {
      setSending(false)
    }
  }

  const afterLogin = (res: AuthResult) => {
    setError('')
    Taro.showToast({ title: successText, icon: 'success' })
    onSuccess(res)
  }

  const onPhoneLogin = async () => {
    if (!validPhone) {
      Taro.showToast({ title: '请输入正确的手机号', icon: 'none' })
      return
    }
    if (!code) {
      Taro.showToast({ title: '请输入验证码', icon: 'none' })
      return
    }
    setBusy(true)
    setError('')
    try {
      afterLogin(await phoneLogin(phone, code))
    } catch (e: any) {
      setError(e?.message || '登录失败，请重试')
    } finally {
      setBusy(false)
    }
  }

  const onWechatLogin = async () => {
    setBusy(true)
    setError('')
    try {
      afterLogin(await wechatLogin())
    } catch (e: any) {
      setError(e?.message || '登录失败，请重试')
    } finally {
      setBusy(false)
    }
  }

  return (
    <View className='m10-login'>
      {tip ? <Text className='bf-muted'>{tip}</Text> : null}
      <Input
        className='bf-input'
        type='number'
        maxlength={11}
        placeholder='手机号'
        value={phone}
        onInput={(e) => setPhone(e.detail.value)}
      />
      <View className='bf-row m10-code'>
        <Input
          className='bf-input'
          type='number'
          maxlength={6}
          placeholder='验证码'
          value={code}
          onInput={(e) => setCode(e.detail.value)}
        />
        <View
          className={`bf-btn bf-btn--sm ${!validPhone || countdown > 0 ? 'is-disabled' : ''}`}
          onClick={onSendCode}
        >
          {countdown > 0 ? `${countdown}s` : '获取验证码'}
        </View>
      </View>
      {error ? <Text className='bf-muted m10-login__err'>{error}</Text> : null}
      <View className={`bf-btn ${busy ? 'is-disabled' : ''}`} onClick={onPhoneLogin}>
        手机号登录
      </View>
      {showWechat && (
        <View className={`bf-btn bf-btn--ghost ${busy ? 'is-disabled' : ''}`} onClick={onWechatLogin}>
          微信一键登录
        </View>
      )}
      <Text className='bf-muted m10-note'>
        iOS 端额外支持 Apple ID 登录；网页端暂仅支持手机号登录。
      </Text>
    </View>
  )
}
