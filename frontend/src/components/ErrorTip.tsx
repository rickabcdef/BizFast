import { View, Text } from '@tarojs/components'

interface Props {
  message: string
  onRetry?: () => void
}

// 统一错误提示（M1-09 / 3.7）：中文提示 + 重试按钮，禁止英文报错
export default function ErrorTip({ message, onRetry }: Props) {
  return (
    <View className='bf-errorbox'>
      <Text className='bf-error'>{message}</Text>
      {onRetry && (
        <View className='bf-btn bf-btn--sm' onClick={onRetry}>
          重试
        </View>
      )}
    </View>
  )
}
