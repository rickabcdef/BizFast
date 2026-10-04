// 跨端适配层：所有平台差异（支付 / 分享 / 存储 / 推送）必须收敛到此处，
// 禁止在页面内写死平台逻辑（ADR-001）。
import Taro from '@tarojs/taro'
import type { Platform } from '@/types'

export function getPlatform(): Platform {
  const sys = Taro.getSystemInfoSync()
  // Taro 在 H5/小程序/App 下通过 env 区分；鸿蒙走 harmony 编译链
  // 具体枚举以 Taro.getEnv() 为准（WEB / WEAPP / RN / HARMONY）
  switch (Taro.getEnv()) {
    case Taro.ENV_TYPE.WEAPP:
      return 'weapp'
    case Taro.ENV_TYPE.RN:
      return 'android' // RN 内部再按 OS 细分
    case Taro.ENV_TYPE.WEB:
    default:
      return 'web'
  }
}

// 支付渠道适配（M5-04）：返回该端可用的支付 channel
export function payChannelFor(platform: Platform): 'wechat' | 'alipay' | 'apple' | 'huawei' {
  switch (platform) {
    case 'weapp':
      return 'wechat' // 微信支付 JSAPI
    case 'ios':
      return 'apple' // Apple IAP（禁止站外支付引导）
    case 'harmony':
      return 'huawei' // 华为支付
    case 'web':
    case 'win':
    case 'mac':
      return 'alipay' // 网页/桌面：支付宝网页或扫码
    case 'android':
    default:
      return 'wechat'
  }
}

// 分享适配（M8）：小程序用 wx 分享卡片，Web 用链接+海报
export function shareCard(opts: { title: string; imageUrl?: string; path?: string }): void {
  const platform = getPlatform()
  if (platform === 'weapp') {
    // 小程序：通过 button open-type=share 触发，此处仅准备数据
    Taro.setStorageSync('bf_share', opts)
  } else {
    // Web/App：复制链接或调起系统分享
    Taro.showShareMenu({ withShareTicket: true })
  }
}

// 文件保存适配：小程序/App 调系统相册或文件，Web 触发下载
export function saveFile(url: string, fileName: string): void {
  const platform = getPlatform()
  if (platform === 'web') {
    const a = document.createElement('a')
    a.href = url
    a.download = fileName
    a.click()
  } else {
    Taro.downloadFile({ url, success: (r) => Taro.saveFile({ tempFilePath: r.tempFilePath }) })
  }
}

// 画布导出图片（M3-06 对比表导出）：入参是 dataURL（后端没有这张图，只能本地生成）。
// Web 直接触发下载；小程序/App 需要先 base64 落盘再存相册，否则 dataURL 无法下载。
export function saveDataUrl(dataUrl: string, fileName: string): boolean {
  if (getPlatform() === 'web') {
    try {
      const a = document.createElement('a')
      a.href = dataUrl
      a.download = fileName
      a.click()
      return true
    } catch {
      return false
    }
  }
  try {
    const base64 = dataUrl.split(',')[1] || ''
    const filePath = `${Taro.env.USER_DATA_PATH}/${fileName}`
    ;(Taro.getFileSystemManager() as any).writeFileSync(filePath, base64, 'base64')
    Taro.saveImageToPhotosAlbum({ filePath })
    return true
  } catch {
    return false
  }
}

// 复制到剪贴板适配（M2-05 分享「复制链接」）。Web 上 clipboard API 需要 https 或
// localhost，失败时回退到 execCommand，保证本地联调也能用。
export async function copyText(text: string): Promise<boolean> {
  const platform = getPlatform()
  if (platform !== 'web') {
    try {
      await Taro.setClipboardData({ data: text })
      return true
    } catch {
      return false
    }
  }
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    /* 继续走回退方案 */
  }
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}

/** 原生分享可用性（Web 端仅部分浏览器支持；不支持时如实降级为复制链接）。 */
export function canNativeShare(): boolean {
  return getPlatform() === 'weapp' || (typeof navigator !== 'undefined' && !!navigator.share)
}

export async function nativeShare(opts: { title: string; text: string; url: string }): Promise<boolean> {
  if (getPlatform() === 'weapp') return false // 小程序由 open-type=share 触发
  if (typeof navigator !== 'undefined' && navigator.share) {
    try {
      await navigator.share(opts)
      return true
    } catch {
      return false
    }
  }
  return false
}
