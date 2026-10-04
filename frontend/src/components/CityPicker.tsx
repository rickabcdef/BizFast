import { useState } from 'react'
import { View, Input, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { filterCities, autoDetectCity } from '@/constants/cities'

interface Props {
  value: string
  onChange: (c: string) => void
}

// 城市选择（M1-05）：支持定位降级 + 关键字搜索，覆盖 300+ 地级市
export default function CityPicker({ value, onChange }: Props) {
  const [kw, setKw] = useState('')
  const [open, setOpen] = useState(false)
  const list = filterCities(kw, 30)

  const locate = async () => {
    await autoDetectCity()
    // 定位成功仍需城市名（真实解析在后端），此处降级为手动选择，不阻断流程
    Taro.showToast({ title: '请手动选择城市', icon: 'none' })
    setOpen(true)
  }

  const pick = (c: string) => {
    onChange(c)
    setOpen(false)
    setKw('')
  }

  return (
    <View className='bf-city'>
      <View className='bf-row'>
        <View className='bf-input bf-city__value' onClick={() => setOpen(!open)}>
          {value || '点击选择城市'}
        </View>
        <View className='bf-btn bf-btn--sm' onClick={locate}>
          定位
        </View>
      </View>
      {open && (
        <View className='bf-card bf-city__panel'>
          <Input
            className='bf-input'
            placeholder='搜索城市，如：杭州'
            value={kw}
            onInput={(e) => setKw(e.detail.value)}
          />
          <View className='bf-city__list'>
            {list.map((c) => (
              <View key={c} className='bf-city__item' onClick={() => pick(c)}>
                {c}
              </View>
            ))}
            {list.length === 0 && <Text className='bf-muted'>无匹配城市</Text>}
          </View>
        </View>
      )}
    </View>
  )
}
