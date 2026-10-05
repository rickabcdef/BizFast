import { useCallback, useEffect, useState } from 'react'
import { View, Text, Textarea } from '@tarojs/components'
import Taro from '@tarojs/taro'
import Loading from '@/components/Loading'
import ErrorTip from '@/components/ErrorTip'
import { getAdminPrompts, saveAdminPrompt, type PromptItem } from '@/services/bApi'

// M11-04 提示词配置：在线配置 AI 提示词与模型路由，修改后无需发版即可生效
export default function PromptsView() {
  const [items, setItems] = useState<PromptItem[]>([])
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState<PromptItem | null>(null)
  const [content, setContent] = useState('')
  const [model, setModel] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const d = await getAdminPrompts()
      setItems(d.items)
      setNotice(d.notice)
    } catch (e: any) {
      setError(e?.message || '提示词列表加载失败，请重试')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const openEdit = (p: PromptItem) => {
    setEditing(p)
    setContent(p.content)
    setModel(p.model)
  }

  const doSave = async () => {
    if (!editing || busy) return
    setBusy(true)
    try {
      const r = await saveAdminPrompt(editing.key, { content, model })
      setEditing(null)
      Taro.showToast({ title: '已保存并即时生效', icon: 'success' })
      void load()
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '保存失败，请重试', icon: 'none' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <View className='m11-prompts'>
      {notice && <Text className='m11-tip m11-tip--ok'>{notice}</Text>}
      {loading && <Loading text='正在加载提示词…' />}
      {error && <ErrorTip message={error} onRetry={load} />}

      {!loading && !error && (
        <View className='bf-card'>
          {items.map((p) => (
            <View key={p.key} className='m11-row'>
              <View className='m11-row__main'>
                <Text className='m11-row__title'>{p.name}</Text>
                <Text className='bf-muted m11-row__sub'>{p.key} · 模型 {p.model} · 更新 {p.updatedAt}</Text>
                <Text className='bf-muted m11-row__sub m11-row__preview' numberOfLines={2}>
                  {p.content}
                </Text>
              </View>
              <View className='m11-row__right'>
                <View className='bf-btn bf-btn--sm bf-btn--ghost' onClick={() => openEdit(p)}>
                  编辑
                </View>
              </View>
            </View>
          ))}
        </View>
      )}

      {/* 编辑弹窗 */}
      {editing && (
        <View className='m11-mask' onClick={() => setEditing(null)}>
          <View className='m11-modal m11-modal--wide' onClick={(e) => e.stopPropagation()}>
            <Text className='m11-modal__title'>编辑 · {editing.name}</Text>
            <Text className='bf-muted m11-modal__sub'>{editing.key}</Text>
            <Text className='m11-modal__h'>模型路由</Text>
            <View className='m11-filter__segs'>
              {['doubao-seed-1.6', 'doubao-lite', 'default'].map((m) => (
                <View
                  key={m}
                  className={`m11-seg ${model === m ? 'is-active' : ''}`}
                  onClick={() => setModel(m)}
                >
                  {m}
                </View>
              ))}
            </View>
            <Text className='m11-modal__h'>提示词内容</Text>
            <Textarea
              className='m11-import__area'
              value={content}
              onInput={(e) => setContent(e.detail.value)}
              maxlength={4000}
              placeholder='请输入提示词…'
              placeholderClass='bf-muted'
            />
            <View className={`bf-btn m11-modal__btn ${busy ? 'bf-btn--disabled' : ''}`} onClick={() => !busy && doSave()}>
              {busy ? '保存中…' : '保存（立即生效，无需发版）'}
            </View>
            <View className='bf-btn bf-btn--ghost m11-modal__btn' onClick={() => setEditing(null)}>
              取消
            </View>
          </View>
        </View>
      )}
    </View>
  )
}
