import { useEffect, useRef, useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro, { useDidShow, useRouter } from '@tarojs/taro'
import BubblePopGame, { type BubblePopStats } from '@/canvas-games/bubblePop'
import NumberMergeGame, { type NumberMergeStats } from '@/canvas-games/numberMerge'
import './index.scss'

// M7 解压小游戏 | 负责人: C | 优先级: P1
// M7-01 指尖解压、M7-02 数字合成；纯前端 Canvas，无广告无内购（M7-05）
// H5 端通过容器注入原生 canvas，规避 Taro Canvas ref 限制。
type GameKey = 'bubble' | 'merge'

export default function M7Games() {
  const router = useRouter()
  // 支持深链 ?g=merge / ?g=bubble（来自工具箱/等待页直达指定游戏）
  const initialGame: GameKey = router.params.g === 'merge' ? 'merge' : 'bubble'
  const [game, setGame] = useState<GameKey>(initialGame)
  const [muted, setMuted] = useState(false)
  const [bubbleStats, setBubbleStats] = useState<BubblePopStats>({ popped: 0, total: 30, elapsedSec: 0 })
  const [mergeStats, setMergeStats] = useState<NumberMergeStats>({ score: 0, best: 0, over: false, won: false })
  const [toast, setToast] = useState('')

  const stageRef = useRef<HTMLElement>(null)
  const canvasEl = useRef<HTMLCanvasElement | null>(null)
  const bubbleGame = useRef<BubblePopGame | null>(null)
  const mergeGame = useRef<NumberMergeGame | null>(null)

  useDidShow(() => {
    setTimeout(() => layout(), 30)
  })

  const showToast = (msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(''), 1800)
  }

  /** 在舞台容器内放置一个原生 canvas（H5） */
  const ensureCanvas = (): HTMLCanvasElement | null => {
    const host = stageRef.current
    if (!host) return null
    if (!canvasEl.current) {
      const c = document.createElement('canvas')
      c.style.display = 'block'
      c.style.touchAction = 'none'
      c.style.borderRadius = '20rpx'
      c.style.background = 'rgba(255,255,255,0.04)'
      host.appendChild(c)
      canvasEl.current = c
    }
    return canvasEl.current
  }

  const clearCanvas = () => {
    if (canvasEl.current) {
      canvasEl.current.remove()
      canvasEl.current = null
    }
  }

  const layout = () => {
    const host = stageRef.current
    if (!host) return
    const w = Math.min(host.clientWidth || 360, 460)
    if (game === 'bubble') {
      const canvas = ensureCanvas()
      if (!canvas) return
      if (!bubbleGame.current) {
        bubbleGame.current = new BubblePopGame(canvas, {
          cols: 5,
          rows: 6,
          onStats: (s) => setBubbleStats(s),
          onComplete: (sec) => showToast(`全部捏爆！用时 ${Math.round(sec)} 秒，压力归零~`)
        })
        bubbleGame.current.setMuted(muted)
        bubbleGame.current.start()
      }
      bubbleGame.current.resize(w, Math.round(w * 1.2))
    } else {
      const canvas = ensureCanvas()
      if (!canvas) return
      if (!mergeGame.current) {
        mergeGame.current = new NumberMergeGame(canvas, {
          onStats: (s) => {
            setMergeStats(s)
            if (s.over) showToast('没有可移动的步骤了，再来一局？')
            if (s.won) showToast('恭喜达成里程碑！可以继续挑战更高数字')
          }
        })
        mergeGame.current.start()
      }
      mergeGame.current.resize(Math.min(w, 420))
    }
  }

  useEffect(() => {
    const onResize = () => layout()
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      bubbleGame.current?.destroy()
      mergeGame.current?.destroy()
      bubbleGame.current = null
      mergeGame.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 切换游戏：销毁旧引擎与画布，重建
  useEffect(() => {
    bubbleGame.current?.destroy()
    mergeGame.current?.destroy()
    bubbleGame.current = null
    mergeGame.current = null
    clearCanvas()
    setTimeout(() => layout(), 30)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game])

  useEffect(() => {
    bubbleGame.current?.setMuted(muted)
  }, [muted])

  const onReset = () => {
    if (game === 'bubble') bubbleGame.current?.reset()
    else mergeGame.current?.newGame()
  }

  const games: { key: GameKey; icon: string; label: string }[] = [
    { key: 'bubble', icon: '🫧', label: '指尖解压' },
    { key: 'merge', icon: '🔢', label: '数字合成' }
  ]

  return (
    <View className='page m7-games'>
      <View className='m7-head'>
        <Text className='m7-title'>😌 休息一下</Text>
        <Text className='m7-sub'>10~60 秒放松，不计排行、无广告、永久免费</Text>
      </View>

      <View className='m7-switch'>
        {games.map((g) => (
          <View
            key={g.key}
            className={`m7-switch__item ${game === g.key ? 'is-active' : ''}`}
            onClick={() => setGame(g.key)}
          >
            <Text className='m7-switch__icon'>{g.icon}</Text>
            <Text className='m7-switch__label'>{g.label}</Text>
          </View>
        ))}
      </View>

      {game === 'bubble' ? (
        <View className='m7-stats'>
          <View className='m7-stat'>
            <Text className='m7-stat__num'>{bubbleStats.popped}</Text>
            <Text className='m7-stat__label'>已捏爆</Text>
          </View>
          <View className='m7-stat'>
            <Text className='m7-stat__num'>{Math.max(0, bubbleStats.total - bubbleStats.popped)}</Text>
            <Text className='m7-stat__label'>剩余</Text>
          </View>
          <View className='m7-stat'>
            <Text className='m7-stat__num'>{bubbleStats.elapsedSec}</Text>
            <Text className='m7-stat__label'>用时(秒)</Text>
          </View>
        </View>
      ) : (
        <View className='m7-stats'>
          <View className='m7-stat'>
            <Text className='m7-stat__num'>{mergeStats.score}</Text>
            <Text className='m7-stat__label'>分数</Text>
          </View>
          <View className='m7-stat'>
            <Text className='m7-stat__num'>{mergeStats.best}</Text>
            <Text className='m7-stat__label'>最高</Text>
          </View>
          <View className='m7-stat'>
            <Text className='m7-stat__num'>{mergeStats.over ? '结束' : '进行'}</Text>
            <Text className='m7-stat__label'>状态</Text>
          </View>
        </View>
      )}

      <View className='m7-stage' ref={stageRef as any}>
        {toast && <View className='m7-toast'><Text>{toast}</Text></View>}
      </View>

      <View className='m7-actions'>
        <View className='bf-btn m7-btn' onClick={onReset}>
          {game === 'bubble' ? '🔄 重新开始' : '🔄 新游戏'}
        </View>
        {game === 'bubble' && (
          <View
            className={`bf-btn bf-btn--ghost m7-btn ${muted ? '' : 'm7-btn--sound-on'}`}
            onClick={() => setMuted((m) => !m)}
          >
            {muted ? '🔇 音效关' : '🔊 音效开'}
          </View>
        )}
      </View>

      <View className='bf-card'>
        <Text className='bf-muted m7-tip'>
          {game === 'bubble'
            ? '💡 点击/触摸泡泡把它捏爆，配合深呼吸把压力捏碎。捏完这一版，启动包也差不多生成好了。'
            : '💡 用方向键 ↑↓←→ 或在棋盘上滑动，相同数字相撞会合并。随时可以离开，最高分本地保存。'}
        </Text>
      </View>

      <View className='m7-back'>
        <Text className='bf-btn bf-btn--sm bf-btn--ghost' onClick={() => Taro.navigateBack()}>
          ← 返回上一页
        </Text>
      </View>
    </View>
  )
}
