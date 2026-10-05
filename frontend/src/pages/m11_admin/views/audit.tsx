import { useCallback, useEffect, useState } from 'react'
import { View, Text, Input } from '@tarojs/components'
import Loading from '@/components/Loading'
import ErrorTip from '@/components/ErrorTip'
import { exportCsv, getAdminAuditLogs, type AuditLogItem } from '@/services/bApi'

// M11-08 审计日志：记录后台所有关键操作，日志保留 ≥ 180 天
export default function AuditView() {
  const [rows, setRows] = useState<AuditLogItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [operator, setOperator] = useState('')
  const [action, setAction] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(
    async (p = page, op = operator, ac = action) => {
      setLoading(true)
      setError('')
      try {
        const d = await getAdminAuditLogs({ page: p, pageSize, operator: op, action: ac })
        setRows(d.items)
        setTotal(d.total)
      } catch (e: any) {
        setError(e?.message || '审计日志加载失败，请重试')
      } finally {
        setLoading(false)
      }
    },
    [page, operator, action, pageSize]
  )

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page])

  const doSearch = () => {
    setPage(1)
    void load(1, operator, action)
  }

  const doExport = () => {
    const ok = exportCsv(
      `生意快启_审计日志_${Date.now()}.csv`,
      ['日志ID', '操作人', '角色', '动作', '对象', '详情', '时间'],
      rows.map((l) => [l.id, l.operator, l.role, l.action, l.target, l.detail, l.createdAt])
    )
    if (!ok) return
  }

  return (
    <View className='m11-audit'>
      <View className='bf-card'>
        <View className='bf-row'>
          <Input
            className='bf-input m11-filter__input'
            placeholder='操作人'
            value={operator}
            onInput={(e) => setOperator(e.detail.value)}
            onConfirm={doSearch}
          />
          <Input
            className='bf-input m11-filter__input'
            placeholder='动作（如 退款 / 审核）'
            value={action}
            onInput={(e) => setAction(e.detail.value)}
            onConfirm={doSearch}
          />
          <View className='bf-btn bf-btn--sm' onClick={doSearch}>
            查询
          </View>
        </View>
        <View className='bf-row m11-filter__foot'>
          <Text className='bf-muted'>共 {total} 条 · 日志保留 ≥ 180 天</Text>
          <View className='bf-btn bf-btn--sm bf-btn--ghost' onClick={doExport}>
            导出
          </View>
        </View>
      </View>

      {loading && <Loading text='正在加载审计日志…' />}
      {error && <ErrorTip message={error} onRetry={() => void load()} />}

      {!loading && !error && (
        <View className='bf-card'>
          {rows.map((l) => (
            <View key={l.id} className='m11-row'>
              <View className='m11-row__main'>
                <Text className='m11-row__title'>{l.action} · {l.target}</Text>
                <Text className='bf-muted m11-row__sub'>{l.detail}</Text>
              </View>
              <View className='m11-row__right'>
                <Text className='bf-tag'>{l.operator}（{l.role}）</Text>
                <Text className='bf-muted m11-row__spend'>{l.createdAt}</Text>
              </View>
            </View>
          ))}
          {rows.length === 0 && <Text className='bf-muted m11-empty-line'>没有符合条件的日志</Text>}
        </View>
      )}

      {total > pageSize && (
        <View className='bf-row m11-pager'>
          <View
            className={`bf-btn bf-btn--sm bf-btn--ghost ${page <= 1 ? 'bf-btn--disabled' : ''}`}
            onClick={() => page > 1 && setPage(page - 1)}
          >
            上一页
          </View>
          <Text className='bf-muted'>{page} / {Math.max(1, Math.ceil(total / pageSize))}</Text>
          <View
            className={`bf-btn bf-btn--sm bf-btn--ghost ${page * pageSize >= total ? 'bf-btn--disabled' : ''}`}
            onClick={() => page * pageSize < total && setPage(page + 1)}
          >
            下一页
          </View>
        </View>
      )}
    </View>
  )
}
