import { View, Text } from '@tarojs/components'

export default function Loading({ text = '加载中…' }: { text?: string }) {
  return (
    <View className='bf-loading'>
      <Text className='bf-muted'>{text}</Text>
    </View>
  )
}
