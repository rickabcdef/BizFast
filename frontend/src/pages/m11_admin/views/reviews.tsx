import { useCallback, useEffect, useState } from 'react'
import { View, Text, Input } from '@tarojs/components'
import Taro from '@tarojs/taro'
import Loading from '@/components/Loading'
import ErrorTip from '@/components/ErrorTip'
import { getAdminReviews, reviewAction, type ReviewItem } from '@/services/bApi'

// M11-06 内容审核：对生成内容做敏感词与合规审核（违规拦截率 ≥ 99%）
const STATUS_FILTERS = [
  { value: '', label: '全部' },
  { value: 'pending', label: '待审核' },
  { value: 'passed', label: '已通过' },
  { value: 'rejected', label: '已拦截' }
]

export default function ReviewsView() {
  const [rows, setRows] = useState<ReviewItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(
    async (p = page, kw = keyword, st = status) => {
      setLoading(true)
      setError('')
      try {
        const d = await getAdminReviews({ page: p, pageSize, keyword: kw, status: st })
        setRows(d.items)
        setTotal(d.total)
      } catch (e: any) {
        setError(e?.message || '审核队列加载失败，请重试')
      } finally {
        setLoading(false)
      }
    },
    [page, keyword, status, pageSize]
  )

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page])

  const doSearch = () => {
    setPage(1)
    void load(1, keyword, status)
  }

  const act = async (item: ReviewItem, action: 'pass' | 'reject') => {
    try {
      const r = await reviewAction(item.id, action)
      Taro.showToast({ title: r.message, icon: 'none' })
      void load()
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '审核操作失败，请重试', icon: 'none' })
    }
  }

  return (
    <View className='m11-reviews'>
      <View className='bf-card'>
        <View className='bf-row'>
          <Input
            className='bf-input m11-filter__input'
            placeholder='搜索内容 / 类型'
            value={keyword}
            onInput={(e) => setKeyword(e.detail.value)}
            onConfirm={doSearch}
          />
          <View className='bf-btn bf-btn--sm' onClick={doSearch}>
            搜索
          </View>
        </View>
        <View className='m11-filter__segs'>
          {STATUS_FILTERS.map((f) => (
            <View
              key={f.value}
              className={`m11-seg ${status === f.value ? 'is-active' : ''}`}
              onClick={() => {
                setStatus(f.value)
                setPage(1)
                void load(1, keyword, f.value)
              }}
            >
              {f.label}
            </View>
          ))}
        </View>
        <Text className='bf-muted m11-filter__foot'>共 {total} 条内容</Text>
      </View>

      {loading && <Loading text='正在加载审核队列…' />}
      {error && <ErrorTip message={error} onRetry={() => void load()} />}

      {!loading && !error && (
        <View className='bf-card'>
          {rows.map((r) => (
            <View key={r.id} className='m11-review'>
              <Text className='m11-row__title'>{r.type}</Text>
              <Text className='m11-review__content'>{r.content}</Text>
              {r.reason && <Text className='m11-tip m11-tip--warn'>命中敏感词：{r.reason}</Text>}
              <View className='bf-row m11-review__foot'>
                <Text className={`bf-tag ${r.status === 'passed' ? 'bf-tag--good' : r.status === 'rejected' ? 'bf-tag--warn' : ''}`}>
                  {r.statusLabel}
                </Text>
                <Text className='bf-muted'>{r.createdAt}</Text>
                {r.status === 'pending' && (
                  <View className='m11-row__acts'>
                    <View className='bf-btn bf-btn--sm' onClick={() => act(r, 'pass')}>
                      通过
                    </View>
                    <View className='bf-btn bf-btn--sm bf-btn--ghost' onClick={() => act(r, 'reject')}>
                      拦截
                    </View>
                  </View>
                )}
              </View>
            </View>
          ))}
          {rows.length === 0 && <Text className='bf-muted m11-empty-line'>审核队列为空</Text>}
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
