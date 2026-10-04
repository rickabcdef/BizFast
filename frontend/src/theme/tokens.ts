// 设计令牌（Design Tokens）：科技风 —— 藏蓝背景、蓝紫渐变主色、呼吸光效。
// 各端只做布局适配，不允许覆盖以下色值（PRD 第 5 章 UI 规范）。
export const tokens = {
  color: {
    bg: '#0B1026', // 深邃藏蓝背景
    bgElevated: '#141A3A',
    primary: '#5B6CFF', // 蓝紫渐变起点
    primaryEnd: '#9B5CFF', // 蓝紫渐变终点
    text: '#E8ECFF',
    textMuted: '#8B93B8',
    success: '#39D98A',
    warning: '#FFB454',
    danger: '#FF5C7C'
  },
  gradient: {
    primary: 'linear-gradient(135deg, #5B6CFF 0%, #9B5CFF 100%)'
  },
  radius: {
    sm: '8rpx',
    md: '16rpx',
    lg: '24rpx',
    pill: '999rpx'
  },
  spacing: {
    xs: '8rpx',
    sm: '16rpx',
    md: '24rpx',
    lg: '32rpx',
    xl: '48rpx'
  },
  // 统一导出为 CSS 变量，供 SCSS/内联样式使用
  toCssVars(): Record<string, string> {
    return {
      '--bf-bg': this.color.bg,
      '--bf-bg-elevated': this.color.bgElevated,
      '--bf-primary': this.color.primary,
      '--bf-primary-end': this.color.primaryEnd,
      '--bf-text': this.color.text,
      '--bf-text-muted': this.color.textMuted
    }
  }
}

export default tokens
