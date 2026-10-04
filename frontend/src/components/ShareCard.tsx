import { View, Text, Image } from '@tarojs/components'
import { placeholderQR } from '@/utils/share'

interface Props {
  productName: string
  subtitle: string
  lines: string[]
  qrText: string
}

// 成果卡片展示（M8-01）：产品名 + 摘要 + 二维码，分享前数据已脱敏
export default function ShareCard({ productName, subtitle, lines, qrText }: Props) {
  const qr = placeholderQR(qrText, 120)
  return (
    <View className='bf-sharecard'>
      <Text className='bf-sharecard__title'>{productName}</Text>
      <Text className='bf-sharecard__sub'>{subtitle}</Text>
      <View className='bf-sharecard__body'>
        {lines.slice(0, 8).map((l, i) => (
          <Text key={i} className='bf-sharecard__line'>
            • {l}
          </Text>
        ))}
      </View>
      <View className='bf-sharecard__foot'>
        {qr ? <Image src={qr} className='bf-sharecard__qr' /> : null}
        <Text className='bf-muted'>长按识别 · 生意快启</Text>
      </View>
    </View>
  )
}
