import { useCallback, useEffect, useState } from 'react'
import { View, Text, Textarea } from '@tarojs/components'
import Taro from '@tarojs/taro'
import Loading from '@/components/Loading'
import ErrorTip from '@/components/ErrorTip'
import {
  getAdminPrompts,
  saveAdminPrompt,
  testAdminPrompt,
  rollbackAdminPrompt,
  type PromptItem
} from '@/services/bApi'

// M11-04 / V5.0 M4-06 提示词配置：在线配置 AI 提示词与模型路由，
// 修改后无需发版即生效；保留最近 10 个版本可回滚；支持一键测试。
export default function PromptsView() {
  const [items, setItems] = useState<PromptItem[]>([])
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState<PromptItem | null>(null)
  const [content, setContent] = useState('')
  const [model, setModel] = useState('')
  const [busy, setBusy] = useState(false)
  // 版本历史 + 回滚
  const [versionItem, setVersionItem] = useState<PromptItem | null>(null)
  const [versionBusy, setVersionBusy] = useState(false)
  // 一键测试
  const [testing, setTesting] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ key: string; sample: string; latencyMs: number } | null>(null)

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
    setTestResult(null)
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

  // V5.0 M4-06 一键测试：用当前提示词跑一次示例诊断，返回结果摘要（不产生真实费用）
  const doTest = async (p: PromptItem) => {
    if (testing) return
    setTesting(p.key)
    setTestResult(null)
    try {
      const r = await testAdminPrompt(p.key)
      setTestResult({ key: p.key, sample: r.sample, latencyMs: r.latencyMs })
      Taro.showToast({ title: r.ok ? '测试通过' : '测试异常', icon: 'none' })
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '测试失败，请重试', icon: 'none' })
    } finally {
      setTesting(null)
    }
  }

  // V5.0 M4-06 版本回滚
  const doRollback = async (p: PromptItem, ver: number) => {
    if (versionBusy) return
    setVersionBusy(true)
    try {
      const r = await rollbackAdminPrompt(p.key, ver)
      setVersionItem(null)
      Taro.showToast({ title: `已回滚到 v${ver}，即时生效`, icon: 'success' })
      void load()
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '回滚失败，请重试', icon: 'none' })
    } finally {
      setVersionBusy(false)
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
                <Text className='m11-row__title'>
                  {p.name}
                  {(p.versions?.length || 0) > 1 && <Text className='m11-tag-ok'>v{p.versions!.length}</Text>}
                </Text>
                <Text className='bf-muted m11-row__sub'>{p.key} · 模型 {p.model} · 更新 {p.updatedAt}</Text>
                <Text className='bf-muted m11-row__sub m11-row__preview' numberOfLines={2}>
                  {p.content}
                </Text>
              </View>
              <View className='m11-row__right'>
                <View className='m11-row__acts'>
                  <View className={`bf-btn bf-btn--sm bf-btn--ghost ${testing === p.key ? 'bf-btn--disabled' : ''}`} onClick={() => !testing && doTest(p)}>
                    {testing === p.key ? '测试中…' : '一键测试'}
                  </View>
                  <View className='bf-btn bf-btn--sm bf-btn--ghost' onClick={() => setVersionItem(p)}>
                    版本
                  </View>
                  <View className='bf-btn bf-btn--sm' onClick={() => openEdit(p)}>
                    编辑
                  </View>
                </View>
              </View>
              {testResult && testResult.key === p.key && (
                <View className='m11-test-box'>
                  <Text className='m11-test-box__title'>测试结果（{testResult.latencyMs}ms）</Text>
                  <Text className='bf-muted m11-row__preview'>{testResult.sample}</Text>
                </View>
              )}
            </View>
          ))}
        </View>
      )}

      {/* 编辑弹窗 */}
      {editing && (
        <View className='m11-mask' onClick={() => setEditing(null)}>
          <View className='m11-modal m11-modal--wide' onClick={(e) => e.stopPropagation()}>
            <Text className='m11-modal__title'>编辑 · {editing.name}</Text>
            <Text className='bf-muted m11-modal__sub'>{editing.key} · 保存后自动备份上一版本（保留最近 10 个版本可回滚）</Text>
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

      {/* V5.0 M4-06 版本历史 / 回滚弹窗 */}
      {versionItem && (
        <View className='m11-mask' onClick={() => setVersionItem(null)}>
          <View className='m11-modal m11-modal--wide' onClick={(e) => e.stopPropagation()}>
            <Text className='m11-modal__title'>版本历史 · {versionItem.name}</Text>
            <Text className='bf-muted m11-modal__sub'>
              {versionItem.key} · 共 {(versionItem.versions || []).length} 个版本，可回滚到任意历史版本；回滚后当前内容被历史版本覆盖。
            </Text>
            {(versionItem.versions || []).length === 0 && <Text className='bf-muted m11-empty-line'>暂无历史版本</Text>}
            {(versionItem.versions || []).map((v) => (
              <View key={v.version} className='m11-ver-row'>
                <View className='m11-ver-row__main'>
                  <Text className='m11-row__title'>v{v.version} · {v.model}</Text>
                  <Text className='bf-muted m11-row__sub m11-row__preview' numberOfLines={2}>{v.content}</Text>
                  <Text className='bf-muted m11-row__sub'>更新 {v.updatedAt}</Text>
                </View>
                <View
                  className={`bf-btn bf-btn--sm ${versionBusy ? 'bf-btn--disabled' : ''}`}
                  onClick={() => !versionBusy && doRollback(versionItem, v.version)}
                >
                  回滚到此版本
                </View>
              </View>
            ))}
            <View className='bf-btn bf-btn--ghost m11-modal__btn' onClick={() => setVersionItem(null)}>
              关闭
            </View>
          </View>
        </View>
      )}
    </View>
  )
}
