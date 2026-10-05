import { useCallback, useEffect, useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import Loading from '@/components/Loading'
import ErrorTip from '@/components/ErrorTip'
import { getAdminRoles, saveAdminRole, type RoleItem } from '@/services/bApi'

// M11-07 权限管理：角色与权限分级（管理员 / 运营 / 客服），操作均记录操作人
export default function RolesView() {
  const [items, setItems] = useState<RoleItem[]>([])
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState<RoleItem | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const d = await getAdminRoles()
      setItems(d.items)
      setNotice(d.notice)
    } catch (e: any) {
      setError(e?.message || '权限列表加载失败，请重试')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const toggle = (permKey: string) => {
    if (!editing) return
    // 管理员角色的核心权限不可关闭（防锁死）
    if (editing.role === 'admin' && (permKey === 'roles' || permKey === 'audit')) {
      Taro.showToast({ title: '管理员基础权限不可关闭', icon: 'none' })
      return
    }
    setEditing({
      ...editing,
      perms: editing.perms.map((p) => (p.key === permKey ? { ...p, enabled: !p.enabled } : p))
    })
  }

  const doSave = async () => {
    if (!editing || busy) return
    setBusy(true)
    try {
      await saveAdminRole(editing.role, editing.perms)
      setEditing(null)
      Taro.showToast({ title: '权限已保存（操作人已记录）', icon: 'success' })
      void load()
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '保存失败，请重试', icon: 'none' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <View className='m11-roles'>
      {notice && <Text className='m11-tip m11-tip--ok'>{notice}</Text>}
      {loading && <Loading text='正在加载角色权限…' />}
      {error && <ErrorTip message={error} onRetry={load} />}

      {!loading && !error && (
        <View className='bf-card'>
          {items.map((r) => (
            <View key={r.role} className='m11-role'>
              <View className='bf-row'>
                <Text className='m11-row__title'>{r.name}</Text>
                <View className='bf-btn bf-btn--sm bf-btn--ghost' onClick={() => setEditing({ ...r, perms: r.perms.map((p) => ({ ...p })) })}>
                  编辑权限
                </View>
              </View>
              <Text className='bf-muted m11-row__sub'>{r.description}</Text>
              <View className='m11-role__perms'>
                {r.perms.filter((p) => p.enabled).map((p) => (
                  <Text key={p.key} className='bf-tag'>{p.label}</Text>
                ))}
              </View>
            </View>
          ))}
        </View>
      )}

      {/* 权限编辑弹窗 */}
      {editing && (
        <View className='m11-mask' onClick={() => setEditing(null)}>
          <View className='m11-modal' onClick={(e) => e.stopPropagation()}>
            <Text className='m11-modal__title'>编辑 · {editing.name} 权限</Text>
            <Text className='bf-muted m11-modal__sub'>保存后立即生效，操作会写入审计日志（M11-08）</Text>
            <View className='m11-perms'>
              {editing.perms.map((p) => (
                <View key={p.key} className='m11-perm' onClick={() => toggle(p.key)}>
                  <View className={`m11-switch ${p.enabled ? 'is-on' : ''}`}>
                    <View className='m11-switch__dot' />
                  </View>
                  <Text className='m11-perm__label'>{p.label}</Text>
                </View>
              ))}
            </View>
            <View className={`bf-btn m11-modal__btn ${busy ? 'bf-btn--disabled' : ''}`} onClick={() => !busy && doSave()}>
              {busy ? '保存中…' : '保存权限'}
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
