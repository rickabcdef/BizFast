import { useCallback, useEffect, useState } from 'react'
import { View, Text, Picker, Switch } from '@tarojs/components'
import Taro from '@tarojs/taro'
import ErrorTip from '@/components/ErrorTip'
import Loading from '@/components/Loading'
import { getPlatform } from '@/utils/platform'
import {
  getMessages,
  getNotifySettings,
  getSubscribe,
  markRead,
  updateNotifySettings,
  type MessagePage,
  type NotificationItem,
  type NotifyCategory,
  type NotifySetting,
  type SubscribeInfo
} from '@/services/aApi'
import './index.scss'

// m9_notify 消息与提醒 | 负责人: A | 优先级: P1
// 需求点：M9-01 站内消息中心+未读红点 / M9-02/03/04 端能力如实标注（Web 不支持后台通知）
//        M9-05 商机库更新提醒（会员可关） / M9-06 免打扰时段（营销类不推送，交易类照常）
const TABS: { key: NotifyCategory | 'all'; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'order', label: '订单' },
  { key: 'package', label: '交付' },
  { key: 'refund', label: '退款' },
  { key: 'activity', label: '活动' },
  { key: 'system', label: '系统' }
]

const CATEGORY_ICON: Record<string, string> = {
  order: '💳',
  package: '📦',
  refund: '↩️',
  activity: '🎁',
  system: '🔔'
}

export default function M9Notify() {
  const [platform] = useState(() => getPlatform())
  const [tab, setTab] = useState<NotifyCategory | 'all'>('all')
  const [page, setPage] = useState<MessagePage | null>(null)
  const [sub, setSub] = useState<SubscribeInfo | null>(null)
  const [setting, setSetting] = useState<NotifySetting | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const loadMessages = useCallback(async (category: NotifyCategory | 'all') => {
    setLoading(true)
    try {
      const data = await getMessages({
        page: 1,
        pageSize: 20,
        category: category === 'all' ? null : category
      })
      setPage(data)
    } catch (e: any) {
      setError(e?.message || '服务开小差了，请重试')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadMessages('all')
    getSubscribe(platform)
      .then(setSub)
      .catch(() => setSub(null))
    getNotifySettings()
      .then(setSetting)
      .catch(() => setSetting(null))
  }, [platform, loadMessages])

  const switchTab = (t: NotifyCategory | 'all') => {
    setTab(t)
    setError('')
    loadMessages(t)
  }

  const openItem = async (item: NotificationItem) => {
    if (!item.isRead) {
      try {
        await markRead(item.id)
      } catch {
        /* 标记已读失败不阻断阅读 */
      }
    }
    await loadMessages(tab)
    if (item.link) Taro.navigateTo({ url: item.link })
  }

  const readAll = async () => {
    try {
      const r = await markRead()
      Taro.showToast({ title: `已全部标记已读（${r.updated} 条）`, icon: 'none' })
      await loadMessages(tab)
    } catch (e: any) {
      setError(e?.message || '操作失败，请重试')
    }
  }

  const patchSetting = async (patch: Partial<NotifySetting>) => {
    if (!setting) return
    const next = { ...setting, ...patch }
    setSetting(next)
    try {
      const saved = await updateNotifySettings(patch)
      setSetting(saved)
    } catch (e: any) {
      setError(e?.message || '保存失败，请重试')
      getNotifySettings().then(setSetting).catch(() => undefined)
    }
  }

  return (
    <View className='page m9-notify'>
      <View className='bf-row m9-head'>
        <View>
          <Text className='m9-head__title'>消息中心</Text>
          <Text className='bf-muted m9-head__sub'>
            未读 {page?.unread ?? 0} 条 · 共 {page?.total ?? 0} 条
          </Text>
        </View>
        <View className='bf-btn bf-btn--sm bf-btn--ghost' onClick={readAll}>
          全部已读
        </View>
      </View>

      {error && <ErrorTip message={error} onRetry={() => loadMessages(tab)} />}

      {/* M9-01：分类筛选 */}
      <View className='m9-tabs'>
        {TABS.map((t) => (
          <View
            key={t.key}
            className={`m9-tab ${tab === t.key ? 'is-active' : ''}`}
            onClick={() => switchTab(t.key)}
          >
            {t.label}
          </View>
        ))}
      </View>

      {loading && !page && <Loading text='正在加载消息…' />}

      <View className='m9-list'>
        {(page?.items || []).map((item) => (
          <View
            key={item.id}
            className={`bf-card m9-item ${item.isRead ? 'is-read' : ''}`}
            onClick={() => openItem(item)}
          >
            <View className='bf-row'>
              <View className='m9-item__titlebox'>
                <Text className='m9-item__icon'>{CATEGORY_ICON[item.category] || '🔔'}</Text>
                <Text className='m9-item__title'>{item.title}</Text>
              </View>
              {!item.isRead && <Text className='m9-item__dot' />}
            </View>
            {item.content ? <Text className='bf-muted m9-item__content'>{item.content}</Text> : null}
            <View className='bf-row m9-item__foot'>
              <Text className='bf-tag'>{item.categoryLabel}</Text>
              <Text className='bf-muted m9-item__time'>{formatTime(item.createdAt)}</Text>
            </View>
          </View>
        ))}
        {page && page.items.length === 0 && (
          <View className='bf-card'>
            <Text className='bf-muted'>这里还没有消息。支付、生成完成、退款到账都会在这里通知你。</Text>
          </View>
        )}
      </View>

      {/* M9-02/03/04：端能力如实标注 */}
      {sub && (
        <View className='bf-card'>
          <Text className='bf-card__title'>通知方式</Text>
          <Text className='bf-muted m9-note'>{sub.notice}</Text>
          <View className='m9-sub'>
            {sub.items.map((s) => (
              <View key={s.key} className={`m9-sub__row ${s.supported ? '' : 'is-disabled'}`}>
                <View className='m9-sub__body'>
                  <Text className='m9-sub__label'>
                    {s.label}
                    {!s.supported && <Text className='m9-sub__badge'>当前端不可用</Text>}
                  </Text>
                  <Text className='bf-muted m9-sub__desc'>{s.description}</Text>
                  <Text className='bf-muted m9-sub__note'>{s.platformNote}</Text>
                </View>
                <Switch
                  checked={s.supported && s.enabled}
                  disabled={!s.supported}
                  color='#5B6CFF'
                  onChange={() => {
                    Taro.showToast({
                      title: s.supported ? '该开关由系统通道控制' : `${s.platformNote}`,
                      icon: 'none'
                    })
                  }}
                />
              </View>
            ))}
          </View>
        </View>
      )}

      {/* M9-05 / M9-06：提醒与免打扰 */}
      {setting && (
        <View className='bf-card'>
          <Text className='bf-card__title'>提醒与免打扰</Text>

          <View className='m9-set'>
            <View className='m9-set__row'>
              <View className='m9-set__body'>
                <Text className='m9-set__label'>商机库更新提醒</Text>
                <Text className='bf-muted m9-set__desc'>有与你条件匹配的新商机时提醒你</Text>
              </View>
              <Switch
                checked={setting.marketReminder}
                color='#5B6CFF'
                onChange={(e) => patchSetting({ marketReminder: e.detail.value })}
              />
            </View>

            <View className='m9-set__row'>
              <View className='m9-set__body'>
                <Text className='m9-set__label'>免打扰时段</Text>
                <Text className='bf-muted m9-set__desc'>
                  时段内不推送营销类消息；支付、退款、交付等交易类消息照常送达
                </Text>
              </View>
              <Switch
                checked={setting.dndEnabled}
                color='#5B6CFF'
                onChange={(e) => patchSetting({ dndEnabled: e.detail.value })}
              />
            </View>

            {setting.dndEnabled && (
              <View className='m9-dnd'>
                <View className='m9-dnd__cell'>
                  <Text className='bf-muted m9-dnd__label'>开始</Text>
                  <Picker
                    mode='time'
                    value={setting.dndStart}
                    onChange={(e) => patchSetting({ dndStart: String(e.detail.value) })}
                  >
                    <View className='m9-dnd__value'>{setting.dndStart}</View>
                  </Picker>
                </View>
                <Text className='bf-muted m9-dnd__sep'>至</Text>
                <View className='m9-dnd__cell'>
                  <Text className='bf-muted m9-dnd__label'>结束</Text>
                  <Picker
                    mode='time'
                    value={setting.dndEnd}
                    onChange={(e) => patchSetting({ dndEnd: String(e.detail.value) })}
                  >
                    <View className='m9-dnd__value'>{setting.dndEnd}</View>
                  </Picker>
                </View>
              </View>
            )}
          </View>
        </View>
      )}

      <Text className='bf-muted m9-foot'>
        网页版受浏览器限制不支持后台通知，离开页面后无法收到提醒；生成完成会通过短信 / 邮件提醒你。
      </Text>
    </View>
  )
}

function formatTime(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
