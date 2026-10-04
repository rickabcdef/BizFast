import { View } from '@tarojs/components'

export interface SegOption {
  label: string
  value: string | number
}

interface Props {
  options: SegOption[]
  value: string | number | null
  onChange: (v: string | number) => void
  columns?: number
}

// 通用分段选择器（M1 启动资金/每日时间 点选控件）
export default function Segmented({ options, value, onChange, columns = 2 }: Props) {
  return (
    <View
      className='bf-seg'
      style={{ display: 'grid', gridTemplateColumns: `repeat(${columns}, 1fr)`, gap: '16rpx' }}
    >
      {options.map((o) => (
        <View
          key={String(o.value)}
          className={`bf-seg__item ${value === o.value ? 'bf-seg__item--active' : ''}`}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </View>
      ))}
    </View>
  )
}
