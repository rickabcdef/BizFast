import Taro from '@tarojs/taro'

/**
 * 读取当前页面 query 参数。
 * H5（hash / history 路由）、小程序、App 三种环境统一处理：
 * 优先取 Taro 路由参数，取不到再从 location 兜底解析。
 */
export function getPageParams(): Record<string, string> {
  const fromRouter = (Taro.getCurrentInstance()?.router?.params ?? {}) as Record<string, string>
  const out: Record<string, string> = { ...fromRouter }

  if (typeof window === 'undefined') return out

  const sources: string[] = []
  if (window.location.hash) {
    const hash = window.location.hash.replace(/^#/, '')
    const idx = hash.indexOf('?')
    if (idx >= 0) sources.push(hash.slice(idx + 1))
  }
  if (window.location.search) sources.push(window.location.search.replace(/^\?/, ''))

  for (const source of sources) {
    new URLSearchParams(source).forEach((value, key) => {
      if (out[key] === undefined) out[key] = value
    })
  }
  return out
}
